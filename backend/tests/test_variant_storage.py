"""Authored M2 identity, archive, race and interruption cases; entirely offline."""

import hashlib
import io
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from threading import Barrier
from typing import Any

import pytest
from test_variants import snapshot

from neurofold.adapters.biological.storage import FilesystemStore
from neurofold.adapters.variant_storage import FilesystemVariants
from neurofold.application.variants import VariantService
from neurofold.core.biological import ReferenceRepository, ReferenceSnapshot
from neurofold.core.canonical import CanonicalObject, canonical_json, sha256_bytes
from neurofold.core.errors import (
    ArchiveConflict,
    ArchiveIntegrityError,
    ArchivePublicationError,
)
from neurofold.core.lookup import PinReceipt
from neurofold.core.provenance import Metadata, MetadataState
from neurofold.core.variants import (
    VariantDefinition,
    VariantError,
    VariantErrorCode,
    VariantPublication,
    VariantRepository,
    define_variant,
    parse_substitution,
    variant_identity_document,
)

REFERENCE_HASH = "c88582ee0f845de56779787b8447097ae3330a816d1656b2808e0d439206226e"
IDENTITY_BYTES = (
    b'{"reference_id":"synthetic-variant-reference","reference_sequence_sha256":"'
    b'c88582ee0f845de56779787b8447097ae3330a816d1656b2808e0d439206226e",'
    b'"schema_version":"neurofold-variant/1","substitution":{"alternate_aa":"V",'
    b'"notation_version":"nf-substitution/1","position":4,"reference_aa":"A"}}'
)
VARIANT_ID = "variant-4f0a7366f1a3a152596ba4337b0f2050b7b06e70640cc77ef54aafa84143f165"


def retain(store: FilesystemStore, reference: ReferenceSnapshot) -> None:
    """Publish synthetic sequence bytes and their unchanged M1 provenance chain."""
    receipt = reference.protein.source_receipt
    store.publish_artifact(
        io.BytesIO(reference.protein.sequence.encode("ascii")),
        descriptor=receipt.raw_artifact,
    )
    store.publish_receipt(receipt)
    store.publish_pin_receipt(
        PinReceipt(
            reference_id=reference.reference_id,
            source_receipt_id=receipt.receipt_id,
            checked_at=reference.captured_at,
            response_status=200,
            response_headers=CanonicalObject.from_value({}),
            adapter_version="synthetic-m2/1",
        )
    )
    store.publish(reference)


def setup(
    root: Path, reference: ReferenceSnapshot | None = None
) -> tuple[FilesystemStore, FilesystemVariants, VariantService]:
    store = FilesystemStore(root / "data")
    retain(store, reference if reference is not None else snapshot())
    variants = FilesystemVariants(store, store)
    return store, variants, VariantService(store, variants)


def create(service: VariantService) -> VariantPublication:
    return service.create("synthetic-variant-reference", REFERENCE_HASH, "A4V")


def rewrite(store: FilesystemStore, variant_id: str, record: object) -> None:
    # Deliberately self-consistent bundle checksum: derivation must still fail.
    store._path("variant", variant_id).write_bytes(
        canonical_json(
            {"record": record, "sha256": sha256_bytes(canonical_json(record))}
        )
    )


def test_golden_creation_round_trip_offline_restart_and_originals(
    tmp_path: Path,
) -> None:
    store, variants, service = setup(tmp_path)
    original_bytes = {path.name: path.read_bytes() for path in store.root.iterdir()}
    publication = create(service)
    definition = publication.definition
    assert publication.created
    assert definition.variant_id == VARIANT_ID
    assert definition.identity_document.data == IDENTITY_BYTES
    assert hashlib.sha256(IDENTITY_BYTES).hexdigest() == VARIANT_ID.removeprefix(
        "variant-"
    )
    assert definition.sequence == "MACVG"
    assert definition.sequence_length == 5
    assert definition.sequence_hash.sha256 == hashlib.sha256(b"MACVG").hexdigest()
    assert definition.notation == "A4V"
    assert definition.substitution.notation_version == "nf-substitution/1"
    assert definition.interpretation_kind == "hypothesis"
    assert definition.reference_content_hash == snapshot().content_hash
    assert definition.reference_accession == snapshot().protein.summary.accession
    assert definition.reference_taxon_id == snapshot().protein.summary.taxon_id.value
    assert definition.differences[0].position == 4
    assert VariantDefinition.from_json(definition.to_json()) == definition
    assert VariantDefinition.from_dict(definition.to_dict()) == definition
    with pytest.raises(FrozenInstanceError):
        definition.sequence = "MACAG"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        publication.created = False  # type: ignore[misc]
    assert create(service) == VariantPublication(definition=definition, created=False)
    restarted = FilesystemStore(store.root)
    reopened = VariantService(restarted, FilesystemVariants(restarted, restarted))
    assert reopened.get(VARIANT_ID) == definition
    assert not create(reopened).created
    for name, raw in original_bytes.items():
        assert (store.root / name).read_bytes() == raw
    assert restarted.get(snapshot().reference_id) == snapshot()
    assert variants.get(VARIANT_ID) == definition
    assert set(definition.to_dict()).isdisjoint({"created_at", "receipt", "timestamp"})
    # Separate canonical definition/bundle identities, not the variant identity.
    assert sha256_bytes(definition.to_json()) != VARIANT_ID.removeprefix("variant-")
    assert sha256_bytes(store._path("variant", VARIANT_ID).read_bytes()) != (
        VARIANT_ID.removeprefix("variant-")
    )
    # Public implementations satisfy the narrow injected protocols under strict mypy.
    reference_repository: ReferenceRepository = store
    variant_repository: VariantRepository = variants
    assert VariantService(reference_repository, variant_repository).get(VARIANT_ID)


def test_reference_aware_identity_and_timestamp_policy(tmp_path: Path) -> None:
    reference = snapshot()
    a = define_variant(reference, parse_substitution("A4V"))
    b = define_variant(replace(reference, reference_id="other-pin"), a.substitution)
    assert a.sequence_hash == b.sequence_hash
    assert a.reference_sequence_sha256 == b.reference_sequence_sha256
    assert a.variant_id != b.variant_id
    assert (
        define_variant(reference, parse_substitution("A4W")).variant_id != a.variant_id
    )
    assert define_variant(snapshot("MACAA"), a.substitution).variant_id != a.variant_id
    # Snapshot capture time remains pinned reference metadata, outside variant ID.
    # These are separate synthetic repositories, not mutation of one retained pin.
    later = replace(reference, captured_at="2026-11-11T00:00:00Z")
    c = define_variant(later, a.substitution)
    assert c.variant_id == a.variant_id
    assert c.reference_content_hash != a.reference_content_hash
    for index, ref in enumerate((reference, later)):
        _, _, service = setup(tmp_path / str(index), ref)
        assert create(service).definition.variant_id == VARIANT_ID
    assert "created_at" not in a.to_dict()


@pytest.mark.parametrize(
    "bad_hash",
    ["", "0" * 63, "G" * 64, "A" * 64, None, 1, True, b"0" * 64, " " + REFERENCE_HASH],
)
def test_malformed_hash_before_resolution_or_notation(
    tmp_path: Path, bad_hash: Any
) -> None:
    store, _, service = setup(tmp_path)
    with pytest.raises(VariantError) as failure:
        service.create("absent", bad_hash, "invalid")
    assert failure.value.code is VariantErrorCode.INVALID_EXPECTED_REFERENCE_HASH
    assert not list(store.root.glob("variant-*"))


@pytest.mark.parametrize("reference_id", [None, True, 1, "", "  ", "\ud800"])
def test_invalid_reference_id_first(tmp_path: Path, reference_id: Any) -> None:
    store, _, service = setup(tmp_path)
    with pytest.raises(VariantError) as failure:
        service.create(reference_id, "bad", "bad")
    assert failure.value.code is VariantErrorCode.INVALID_VARIANT_INPUT
    assert not list(store.root.glob("variant-*"))


def test_resolution_precedence_and_unambiguous_hash_details(tmp_path: Path) -> None:
    store, _, service = setup(tmp_path)
    cases = [
        ("absent", REFERENCE_HASH, "bad", VariantErrorCode.INVALID_NOTATION),
        ("absent", "0" * 64, "A4V", VariantErrorCode.REFERENCE_NOT_FOUND),
        (
            snapshot().reference_id,
            "0" * 64,
            "C4C",
            VariantErrorCode.REFERENCE_HASH_MISMATCH,
        ),
    ]
    for reference_id, expected, notation, code in cases:
        with pytest.raises(VariantError) as failure:
            service.create(reference_id, expected, notation)
        assert failure.value.code is code
    assert failure.value.details == {
        "expected_reference_sha256": "0" * 64,
        "actual_reference_sha256": REFERENCE_HASH,
    }
    assert not list(store.root.glob("variant-*"))


@pytest.mark.parametrize(
    ("sequence", "notation", "code"),
    [
        ("MACAG", "A99A", VariantErrorCode.POSITION_OUT_OF_RANGE),
        ("MACAG", "C4C", VariantErrorCode.REFERENCE_MISMATCH),
        ("MACAG", "A4A", VariantErrorCode.NO_OP_SUBSTITUTION),
        ("MXCAG", "A99A", VariantErrorCode.UNSUPPORTED_REFERENCE_ALPHABET),
    ],
)
def test_m1_errors_propagate_without_publication(
    tmp_path: Path, sequence: str, notation: str, code: VariantErrorCode
) -> None:
    reference = snapshot(sequence)
    store, _, service = setup(tmp_path, reference)
    with pytest.raises(VariantError) as failure:
        service.create(
            reference.reference_id, reference.protein.sequence_hash.sha256, notation
        )
    assert failure.value.code is code
    if code is VariantErrorCode.REFERENCE_MISMATCH:
        assert failure.value.details == {
            "position": 4,
            "requested_reference_aa": "C",
            "actual_reference_aa": "A",
        }
    assert not list(store.root.glob("variant-*"))


def test_unknown_variant_and_wrong_repository_reference(tmp_path: Path) -> None:
    store, variants, service = setup(tmp_path)
    with pytest.raises(KeyError):
        service.get(VARIANT_ID)

    class WrongReferences:
        def get(self, reference_id: str) -> ReferenceSnapshot:
            return replace(snapshot(), reference_id="different")

        def publish(self, reference: ReferenceSnapshot) -> None:
            raise AssertionError("No reference writes allowed")

    with pytest.raises(ArchiveIntegrityError, match="different ID"):
        create(VariantService(WrongReferences(), variants))
    assert not list(store.root.glob("variant-*"))


def test_concurrent_thread_duplicates_reach_atomic_link_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, _, _ = setup(tmp_path)
    barrier = Barrier(4, timeout=10)
    original_link = os.link

    def linked(*args: Any, **kwargs: Any) -> None:
        barrier.wait()
        original_link(*args, **kwargs)

    monkeypatch.setattr(os, "link", linked)

    def worker(_: int) -> VariantPublication:
        reopened = FilesystemStore(store.root)
        return create(VariantService(reopened, FilesystemVariants(reopened, reopened)))

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(worker, range(4)))
    assert sum(result.created for result in results) == 1
    assert all(result.definition == results[0].definition for result in results)
    assert len(list(store.root.glob("variant-*"))) == 1
    assert not list(store.root.glob("tmp*"))


def test_independent_processes_converge_and_reopen_without_site_packages(
    tmp_path: Path,
) -> None:
    store, _, _ = setup(tmp_path)
    source = Path(__file__).parents[1] / "src"
    # Each child pauses at the link, after fsync and absence checks. Both must
    # report staged before either can proceed; no timing-based race assertion.
    script = f"""
import sys, socket, os
sys.path.insert(0, {str(source)!r})
def deny(*args, **kwargs):
    raise RuntimeError("network forbidden in M2 subprocess")
socket.socket = deny
for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
    setattr(socket, name, deny)
from pathlib import Path
from neurofold.adapters.biological.storage import FilesystemStore
from neurofold.adapters.variant_storage import FilesystemVariants
from neurofold.application.variants import VariantService
store = FilesystemStore(Path({str(store.root)!r}))
service = VariantService(store, FilesystemVariants(store, store))
link = os.link
def gated_link(*args, **kwargs):
    print("staged", flush=True)
    assert sys.stdin.readline() == "release\\n"
    link(*args, **kwargs)
os.link = gated_link
result = service.create("synthetic-variant-reference", {REFERENCE_HASH!r}, "A4V")
assert service.get(result.definition.variant_id) == result.definition
print(int(result.created), result.definition.variant_id, flush=True)
"""
    children = [
        subprocess.Popen(
            [sys.executable, "-I", "-S", "-c", script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    try:
        for child in children:
            assert child.stdout is not None
            assert child.stdout.readline().strip() == "staged"
        for child in children:
            assert child.stdin is not None
            child.stdin.write("release\n")
            child.stdin.flush()
        results = []
        for child in children:
            out, err = child.communicate(timeout=15)
            assert child.returncode == 0, err
            created, variant_id = out.strip().split()
            results.append(int(created))
            assert variant_id == VARIANT_ID
        assert sum(results) == 1
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=5)
    assert FilesystemVariants(store, store).get(VARIANT_ID).sequence == "MACVG"


@pytest.mark.parametrize(
    "phase", ["stage_write", "file_fsync", "link", "directory_fsync"]
)
def test_publication_failure_and_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    store, _, service = setup(tmp_path)
    fsync = os.fsync
    calls = 0

    def failed(*args: object, **kwargs: object) -> None:
        raise OSError("authored interruption")

    def failing_fsync(fd: int) -> None:
        nonlocal calls
        calls += 1
        if calls == (2 if phase == "directory_fsync" else 1):
            failed()
        fsync(fd)

    with monkeypatch.context() as patch:
        if phase == "link":
            patch.setattr(os, "link", failed)
        elif phase == "stage_write":
            patch.setattr("tempfile.NamedTemporaryFile", failed)
        else:
            patch.setattr(os, "fsync", failing_fsync)
        with pytest.raises(ArchivePublicationError, match="I/O"):
            create(service)
    restarted = FilesystemStore(store.root)
    reopened = VariantService(restarted, FilesystemVariants(restarted, restarted))
    if phase == "directory_fsync":
        assert reopened.get(VARIANT_ID).sequence == "MACVG"
        assert not create(reopened).created
    else:
        with pytest.raises(KeyError):
            reopened.get(VARIANT_ID)
        assert create(reopened).created
    assert not list(store.root.glob("tmp*"))


def test_abandoned_stages_are_never_published_variants(tmp_path: Path) -> None:
    store, variants, service = setup(tmp_path)
    stage = store.root / "tmp-abandoned"
    stage.write_bytes(b'{"record":')
    with pytest.raises(KeyError):
        variants.get(VARIANT_ID)
    assert create(service).created
    assert stage.read_bytes() == b'{"record":'


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"{",
        b"\xff",
        b"[]",
        b"{}",
        b'{"record":{},"sha256":"wrong"}',
        b'{"record":{},"record":{},"sha256":"x"}',
    ],
)
def test_corrupt_archive_and_duplicate_fail_without_repair(
    tmp_path: Path, raw: bytes
) -> None:
    store, variants, service = setup(tmp_path)
    path = store._path("variant", VARIANT_ID)
    path.write_bytes(raw)
    for operation in (lambda: variants.get(VARIANT_ID), lambda: create(service)):
        with pytest.raises(ArchiveIntegrityError):
            operation()
        assert path.read_bytes() == raw


# Each mutation gets a newly correct envelope checksum, proving it is not enough.
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "neurofold-variant/2"),
        ("schema_version", "neurofold-variant/1.1"),
        ("sequence_length", True),
        ("sequence_length", 4),
        ("sequence_length", "5"),
        ("variant_id", "variant-" + "0" * 64),
        ("reference_id", "absent-pin"),
        ("reference_sequence_sha256", "0" * 64),
        (
            "reference_content_hash",
            {"sha256": "0" * 64, "encoding": "neurofold-json/1", "algorithm": "sha256"},
        ),
        ("reference_accession", "P00002"),
        ("reference_taxon_id", 999),
        (
            "reference_sequence_version",
            Metadata(state=MetadataState.PRESENT, value=999, reason=None).to_dict(),
        ),
        (
            "reference_entry_version",
            Metadata(state=MetadataState.PRESENT, value=999, reason=None).to_dict(),
        ),
        ("notation", "A4W"),
        ("notation", " A4V"),
        ("sequence", "VACVG"),
        ("sequence", "MACAG"),
        (
            "sequence_hash",
            {"sha256": "0" * 64, "encoding": "sequence-ascii/1", "algorithm": "sha256"},
        ),
        ("interpretation_kind", "predicted"),
        ("interpretation_kind", "experimental"),
        ("differences", []),
        (
            "substitution",
            {
                "reference_aa": "A",
                "position": True,
                "alternate_aa": "V",
                "notation_version": "nf-substitution/1",
            },
        ),
        (
            "substitution",
            {
                "reference_aa": "A",
                "position": 4,
                "alternate_aa": "V",
                "notation_version": "nf-substitution/2",
            },
        ),
    ],
)
def test_self_consistent_checksum_tampering_is_rejected(
    tmp_path: Path, field: str, value: object
) -> None:
    store, variants, service = setup(tmp_path)
    definition = create(service).definition
    record = definition.to_dict()
    record[field] = value
    rewrite(store, VARIANT_ID, record)
    damaged = store._path("variant", VARIANT_ID).read_bytes()
    for operation in (lambda: variants.get(VARIANT_ID), lambda: create(service)):
        with pytest.raises(ArchiveIntegrityError):
            operation()
        assert store._path("variant", VARIANT_ID).read_bytes() == damaged


def test_exact_derivation_not_just_sequence_checksum(tmp_path: Path) -> None:
    store, variants, service = setup(tmp_path)
    definition = create(service).definition
    record = definition.to_dict()
    record["sequence"] = "VACVG"  # Two differences, all stored hashes recomputed.
    record["sequence_hash"] = {
        "sha256": hashlib.sha256(b"VACVG").hexdigest(),
        "encoding": "sequence-ascii/1",
        "algorithm": "sha256",
    }
    # Standalone codec cannot resolve the reference. Repository must do so.
    assert VariantDefinition.from_dict(record).sequence == "VACVG"
    rewrite(store, VARIANT_ID, record)
    with pytest.raises(ArchiveIntegrityError, match="exact derivation"):
        variants.get(VARIANT_ID)


def test_reference_resolution_after_self_consistent_identity_tamper(
    tmp_path: Path,
) -> None:
    store, variants, service = setup(tmp_path)
    definition = create(service).definition
    other = define_variant(
        replace(snapshot(), reference_id="missing-pin"), definition.substitution
    )
    rewrite(store, other.variant_id, other.to_dict())
    with pytest.raises(ArchiveIntegrityError, match="dependency missing"):
        variants.get(other.variant_id)
    # A valid record under the wrong requested ID cannot pass either.
    rewrite(store, VARIANT_ID, other.to_dict())
    with pytest.raises(ArchiveIntegrityError, match="Requested variant identity"):
        variants.get(VARIANT_ID)


@pytest.mark.parametrize(
    "field", list(define_variant(snapshot(), parse_substitution("A4V")).to_dict())
)
def test_missing_contract_fields(tmp_path: Path, field: str) -> None:
    store, variants, service = setup(tmp_path)
    record = create(service).definition.to_dict()
    del record[field]
    rewrite(store, VARIANT_ID, record)
    with pytest.raises(ArchiveIntegrityError):
        variants.get(VARIANT_ID)


def test_unknown_fields_in_contract_and_envelope(tmp_path: Path) -> None:
    store, variants, service = setup(tmp_path)
    record = create(service).definition.to_dict()
    record["created_at"] = "2026-11-10T00:00:00Z"
    rewrite(store, VARIANT_ID, record)
    with pytest.raises(ArchiveIntegrityError):
        variants.get(VARIANT_ID)
    store._path("variant", VARIANT_ID).write_bytes(
        canonical_json({"record": {}, "sha256": "0" * 64, "extra": True})
    )
    with pytest.raises(ArchiveIntegrityError):
        variants.get(VARIANT_ID)


@pytest.mark.parametrize("dependency", ["reference", "pin", "receipt", "artifact"])
@pytest.mark.parametrize("damage", ["missing", "corrupt", "directory"])
def test_missing_or_corrupt_reference_dependency_is_never_not_found(
    tmp_path: Path, dependency: str, damage: str
) -> None:
    store, variants, service = setup(tmp_path)
    create(service)
    reference = snapshot()
    receipt = reference.protein.source_receipt
    identity = {
        "reference": reference.reference_id,
        "pin": reference.reference_id,
        "receipt": receipt.receipt_id,
        "artifact": receipt.raw_artifact.artifact_id,
    }[dependency]
    path = store._path(dependency, identity)
    if damage == "missing":
        path.unlink()
    elif damage == "directory":
        path.unlink()
        path.mkdir()
    else:
        path.write_bytes(b"{")
    with pytest.raises(ArchiveIntegrityError):
        variants.get(VARIANT_ID)
    # Missing top-level reference is REFERENCE_NOT_FOUND at creation; damage to
    # known retained reference dependencies stays ArchiveIntegrityError.
    if dependency != "reference" or damage != "missing":
        with pytest.raises(ArchiveIntegrityError):
            create(service)


def test_known_directory_symlink_and_oversized_archive_fail_integrity(
    tmp_path: Path,
) -> None:
    from neurofold.adapters.biological.storage import MAX_STORED_BYTES

    store, variants, _ = setup(tmp_path)
    path = store._path("variant", VARIANT_ID)
    path.mkdir()
    with pytest.raises(ArchiveIntegrityError):
        variants.get(VARIANT_ID)
    path.rmdir()
    path.symlink_to(store.root / "nonexistent")
    with pytest.raises(ArchiveIntegrityError):
        variants.get(VARIANT_ID)
    path.unlink()
    path.write_bytes(b"x" * (MAX_STORED_BYTES + 1))
    with pytest.raises(ArchiveIntegrityError):
        variants.get(VARIANT_ID)


def test_valid_conflicting_content_never_overwrites_even_on_identity_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, variants, service = setup(tmp_path)
    # Model an identity collision to exercise the otherwise unreachable valid
    # conflict: both complete definitions derive correctly from the same pin.
    monkeypatch.setattr("neurofold.core.variants.sha256_bytes", lambda _: "0" * 64)
    first = create(service).definition
    before = store._path("variant", first.variant_id).read_bytes()
    other = define_variant(snapshot(), parse_substitution("A4W"))
    with pytest.raises(ArchiveConflict):
        variants.publish(other)
    assert store._path("variant", first.variant_id).read_bytes() == before
    assert variants.get(first.variant_id) == first


@pytest.mark.parametrize("corrupt", [False, True])
def test_conflicting_race_is_verified_before_classification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, corrupt: bool
) -> None:
    store, variants, service = setup(tmp_path)
    monkeypatch.setattr("neurofold.core.variants.sha256_bytes", lambda _: "0" * 64)
    other = define_variant(snapshot(), parse_substitution("A4W"))
    publish = store._publish

    def raced(kind: str, identity: str, data: bytes) -> bool:
        if corrupt:
            store._path(kind, identity).write_bytes(b"{")
        else:
            rewrite(store, identity, other.to_dict())
        return publish(kind, identity, data)

    monkeypatch.setattr(store, "_publish", raced)
    with pytest.raises(ArchiveIntegrityError if corrupt else ArchiveConflict):
        create(service)
    if not corrupt:
        assert variants.get(other.variant_id) == other


def test_application_propagates_repository_outcomes(tmp_path: Path) -> None:
    store, _, _ = setup(tmp_path)

    class FailedRepository:
        def get(self, variant_id: str) -> VariantDefinition:
            raise ArchiveIntegrityError("known damage")

        def publish(self, definition: VariantDefinition) -> VariantPublication:
            raise ArchiveConflict("known conflict")

    service = VariantService(store, FailedRepository())
    with pytest.raises(ArchiveConflict):
        create(service)
    with pytest.raises(ArchiveIntegrityError):
        service.get(VARIANT_ID)


@pytest.mark.parametrize(
    "field", ["sequence_length", "notation", "variant_id", "interpretation_kind"]
)
def test_direct_definition_constructor_invariants(field: str) -> None:
    definition = define_variant(snapshot(), parse_substitution("A4V"))
    changes: dict[str, Any] = {
        "sequence_length": True,
        "notation": "A4W",
        "variant_id": "bad",
        "interpretation_kind": "predicted",
    }
    with pytest.raises(VariantError):
        replace(definition, **{field: changes[field]})


def test_identity_requires_exact_domain_fields() -> None:
    fields: dict[str, Any] = {
        "reference_id": snapshot().reference_id,
        "reference_sequence_sha256": REFERENCE_HASH,
        "substitution": parse_substitution("A4V"),
    }
    changes: dict[str, Any]
    for changes in (
        {"reference_id": 5},
        {"substitution": {}},
        {"reference_sequence_sha256": "bad"},
    ):
        with pytest.raises(ValueError):
            variant_identity_document(**(fields | changes))


@pytest.mark.parametrize("after_link", [False, True])
def test_abrupt_process_exit_leaves_only_complete_or_unpublished_records(
    tmp_path: Path, after_link: bool
) -> None:
    store, variants, service = setup(tmp_path)
    source = Path(__file__).parents[1] / "src"
    script = f"""
import sys, os, socket
sys.path.insert(0, {str(source)!r})
def deny(*args, **kwargs):
    raise RuntimeError("network forbidden in interruption subprocess")
socket.socket = deny
for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
    setattr(socket, name, deny)
from pathlib import Path
from neurofold.adapters.biological.storage import FilesystemStore
from neurofold.adapters.variant_storage import FilesystemVariants
from neurofold.application.variants import VariantService
store = FilesystemStore(Path({str(store.root)!r}))
link = os.link
def interrupted(*args, **kwargs):
    if {after_link!r}:
        link(*args, **kwargs)
    os._exit(71)
os.link = interrupted
VariantService(store, FilesystemVariants(store, store)).create(
    "synthetic-variant-reference", {REFERENCE_HASH!r}, "A4V")
"""
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-c", script],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 71, result.stderr
    stages = list(store.root.glob("tmp*"))
    assert len(stages) == 1  # No Python finally/cleanup ran in the child.
    before = stages[0].read_bytes()
    if after_link:
        assert variants.get(VARIANT_ID).sequence == "MACVG"
    else:
        with pytest.raises(KeyError):
            variants.get(VARIANT_ID)
    assert create(service).created is not after_link
    assert stages[0].read_bytes() == before


def test_partial_stage_write_failure_never_exposes_final_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tempfile

    store, variants, service = setup(tmp_path)
    original = tempfile.NamedTemporaryFile

    def partial_stage(*args: Any, **kwargs: Any) -> Any:
        stage: Any = original(*args, **kwargs)
        write = stage.write

        def interrupted(data: bytes) -> int:
            write(data[:10])
            stage.flush()
            raise OSError("injected partial stage write")

        stage.write = interrupted
        return stage

    with monkeypatch.context() as patch:
        patch.setattr(tempfile, "NamedTemporaryFile", partial_stage)
        with pytest.raises(ArchivePublicationError):
            create(service)
    assert not list(store.root.glob("tmp*"))
    with pytest.raises(KeyError):
        variants.get(VARIANT_ID)
    assert create(service).created


def test_self_consistent_substitution_identity_still_checks_m1_against_reference(
    tmp_path: Path,
) -> None:
    store, variants, service = setup(tmp_path)
    record = create(service).definition.to_dict()
    substitution = parse_substitution("C4V")  # Actual reference residue is A.
    record["substitution"] = substitution.to_dict()
    record["notation"] = "C4V"
    record["differences"] = [{"position": 4, "reference_aa": "C", "alternate_aa": "V"}]
    identity = {
        "schema_version": "neurofold-variant/1",
        "reference_id": snapshot().reference_id,
        "reference_sequence_sha256": REFERENCE_HASH,
        "substitution": substitution.to_dict(),
    }
    variant_id = "variant-" + hashlib.sha256(canonical_json(identity)).hexdigest()
    record["variant_id"] = variant_id
    assert VariantDefinition.from_dict(record).notation == "C4V"
    rewrite(store, variant_id, record)
    with pytest.raises(ArchiveIntegrityError, match="Requested reference residue"):
        variants.get(variant_id)

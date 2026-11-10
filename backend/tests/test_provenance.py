"""Frozen contracts, strict wire compatibility, and absence/evidence semantics."""

import copy
import json
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from neurofold.core._contracts import Contract
from neurofold.core.canonical import CanonicalObject, canonical_json, sha256_bytes
from neurofold.core.provenance import (
    ArtifactDescriptor,
    ContentHash,
    ContentReference,
    EvidenceKind,
    HashEncoding,
    Metadata,
    MetadataState,
    ProvenanceRecord,
    RecordStatus,
    RedistributionStatus,
    ReferenceCollection,
    ScientificInput,
    SourceReceipt,
)

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLES: list[dict[str, Any]] = json.loads(
    (FIXTURES / "contracts-v1.json").read_text()
)
READERS: tuple[type[Contract], ...] = (
    ScientificInput,
    ArtifactDescriptor,
    SourceReceipt,
    ProvenanceRecord,
)
SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs/schemas/neurofold-research-1.schema.json"
)
SCHEMA: dict[str, Any] = json.loads(SCHEMA_PATH.read_text())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


@pytest.fixture
def artifact() -> ArtifactDescriptor:
    return ArtifactDescriptor.from_dict(EXAMPLES[1])


@pytest.fixture
def receipt() -> SourceReceipt:
    return SourceReceipt.from_dict(EXAMPLES[2])


@pytest.fixture
def record() -> ProvenanceRecord:
    return ProvenanceRecord.from_dict(EXAMPLES[3])


def test_checked_in_schema_is_valid() -> None:
    Draft202012Validator.check_schema(SCHEMA)


@pytest.mark.parametrize(
    "payload",
    [
        {"A": None, "_": [True, 1, "é"], "a": {"child": -1}},
        {},
    ],
)
def test_schema_accepts_canonical_unicode_values_and_ascii_keys(
    payload: object,
) -> None:
    value = ScientificInput(
        input_schema="fixture/1", payload=CanonicalObject.from_value(payload)
    )
    VALIDATOR.validate(value.to_dict())


@pytest.mark.parametrize("payload", [{"é": 1}, {"x": 9007199254740992}])
def test_schema_rejects_nonascii_keys_and_unsafe_integers(payload: object) -> None:
    changed = copy.deepcopy(EXAMPLES[0])
    changed["payload"] = payload
    with pytest.raises(ValueError):
        ScientificInput.from_dict(changed)
    with pytest.raises(ValidationError):
        VALIDATOR.validate(changed)


@pytest.mark.parametrize("reader,example", list(zip(READERS, EXAMPLES, strict=True)))
def test_v1_fixtures_remain_readable_and_match_schema(
    reader: type[Contract], example: dict[str, Any]
) -> None:
    VALIDATOR.validate(example)
    decoded = reader.from_json(json.dumps(example).encode())
    assert decoded.to_dict() == example
    assert decoded.to_json() == canonical_json(example)
    assert reader.from_json(decoded.to_json()) == decoded
    # Constructor defaults are explicitly written, never injected by a reader.
    assert set(SCHEMA["$defs"][reader.__name__]["required"]) == {
        field.name
        for field in fields(decoded)  # type: ignore[arg-type]
    }


@pytest.mark.parametrize("reader,example", list(zip(READERS, EXAMPLES, strict=True)))
def test_missing_unknown_and_changed_version_fields_are_not_silently_accepted(
    reader: type[Contract], example: dict[str, Any]
) -> None:
    variants = [
        {key: value for key, value in example.items() if key != omitted}
        for omitted in example
    ]
    variants += [dict(example, undocumented_optional=True)]
    variants += [
        dict(example, schema_version=version)
        for version in (
            "neurofold-research/2",
            "neurofold-research/1.1",
            "neurofold-research/0",
            1,
        )
    ]
    for malformed in variants:
        with pytest.raises(ValueError):
            reader.from_dict(malformed)
        with pytest.raises(ValidationError):
            VALIDATOR.validate(malformed)


@pytest.mark.parametrize("reader", READERS)
def test_records_require_object_roots(reader: type[Contract]) -> None:
    value: object
    for value in (None, [], "text", 0):
        with pytest.raises(ValueError):
            reader.from_dict(value)


def test_nested_unknown_fields_and_versions_are_rejected() -> None:
    for path, key, value in [
        (("raw_artifact",), "schema_version", "neurofold-research/2"),
        (("raw_artifact", "content_hash"), "algorithm", "md5"),
        (("raw_artifact", "rights", "license"), "invented", True),
    ]:
        changed = copy.deepcopy(EXAMPLES[2])
        target = changed
        for part in path:
            target = target[part]
        target[key] = value
        with pytest.raises(ValueError):
            SourceReceipt.from_dict(changed)
        with pytest.raises(ValidationError):
            VALIDATOR.validate(changed)


def test_serialized_readers_reject_duplicate_keys_and_floats() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        SourceReceipt.from_json(b'{"receipt_id":"one","receipt_id":"two"}')
    changed = copy.deepcopy(EXAMPLES[1])
    changed["byte_size"] = 21.0
    with pytest.raises(ValueError):
        ArtifactDescriptor.from_json(json.dumps(changed).encode())


def test_content_identity_captures_defaults_schema_and_order_without_receipt_data() -> (
    None
):
    one = ScientificInput.from_dict(EXAMPLES[0])
    reordered = ScientificInput(
        input_schema=one.input_schema,
        payload=CanonicalObject.from_value(
            {
                "seed": 0,
                "parameters": {"temperature": "0.5", "samples": 1},
                "sequence": "ACDX",
            }
        ),
    )
    assert one.content_hash == reordered.content_hash
    assert one.content_hash.sha256 == sha256_bytes(canonical_json(EXAMPLES[0]))
    assert one.content_hash.encoding is HashEncoding.CANONICAL_JSON
    for content in ({"seed": 0}, {"seed": 1}, {"seed": 0, "samples": 1}):
        assert (
            replace(one, payload=CanonicalObject.from_value(content)).content_hash
            != one.content_hash
        )
    assert (
        replace(one, input_schema="synthetic-example/2").content_hash
        != one.content_hash
    )
    ordered = replace(one, payload=CanonicalObject.from_value({"pairs": [1, 2]}))
    assert (
        replace(
            ordered, payload=CanonicalObject.from_value({"pairs": [2, 1]})
        ).content_hash
        != ordered.content_hash
    )


def test_retrieval_history_is_separate_from_byte_identity(
    receipt: SourceReceipt,
) -> None:
    later = replace(
        receipt, receipt_id="another-event", retrieved_at="2026-11-11T00:00:00Z"
    )
    assert later.to_json() != receipt.to_json()
    assert later.raw_artifact.content_hash == receipt.raw_artifact.content_hash


def test_metadata_distinguishes_zero_false_and_absence() -> None:
    for value in (
        0,
        False,
        "",
        CanonicalObject.from_value({"metric": "0", "units": "angstrom"}),
    ):
        present = Metadata(state=MetadataState.PRESENT, value=value, reason=None)
        assert Metadata.from_json(present.to_json()) == present
    absent = Metadata(
        state=MetadataState.UNAVAILABLE, value=None, reason="Not reported"
    )
    inapplicable = replace(absent, state=MetadataState.NOT_APPLICABLE)
    assert absent.to_json() != inapplicable.to_json()


@pytest.mark.parametrize(
    "state,value,reason",
    [
        ("present", None, None),
        ("present", 0, "missing"),
        ("unavailable", 0, "missing"),
        ("not_applicable", False, "missing"),
        ("unavailable", None, None),
        ("not_applicable", None, "  "),
        ("unknown", None, "missing"),
    ],
)
def test_invalid_metadata_envelopes_fail_both_validators(
    state: str, value: object, reason: object
) -> None:
    malformed = {"state": state, "value": value, "reason": reason}
    with pytest.raises(ValueError):
        Metadata.from_dict(malformed)
    schema = {"$ref": "#/$defs/Metadata", "$defs": SCHEMA["$defs"]}
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(malformed)


def test_no_mutable_or_coerced_domain_fields(artifact: ArtifactDescriptor) -> None:
    with pytest.raises(FrozenInstanceError):
        artifact.artifact_id = "changed"  # type: ignore[misc]  # Frozen runtime guard.
    for key, value in [("byte_size", True), ("parents", []), ("evidence", "synthetic")]:
        changes: dict[str, Any] = {key: value}
        with pytest.raises(ValueError):
            replace(artifact, **changes)
    for value in (True, "1", 1.0):
        changed = copy.deepcopy(EXAMPLES[1])
        changed["byte_size"] = value
        with pytest.raises(ValueError):
            ArtifactDescriptor.from_dict(changed)
    changed["content_hash"] = "not a hash object"
    with pytest.raises(ValueError):
        ArtifactDescriptor.from_dict(changed)


@pytest.mark.parametrize("digest", ["", "A" * 64, "g" * 64, "a" * 63, "a" * 65])
def test_hash_format_is_strict(digest: str) -> None:
    with pytest.raises(ValueError):
        ContentHash(sha256=digest, encoding=HashEncoding.RAW)


def test_hash_domains_are_explicit(artifact: ArtifactDescriptor) -> None:
    with pytest.raises(ValueError, match="raw bytes"):
        replace(
            artifact,
            content_hash=replace(artifact.content_hash, encoding=HashEncoding.SEQUENCE),
        )
    assert artifact.content_hash != replace(
        artifact.content_hash, encoding=HashEncoding.SEQUENCE
    )


def test_artifact_validation_and_derivative_lineage(
    artifact: ArtifactDescriptor,
) -> None:
    for changes in (
        {"byte_size": -1},
        {"media_type": "plain"},
        {"media_type": "text/plain; charset=utf-8"},
        {"artifact_id": " "},
    ):
        with pytest.raises(ValueError):
            replace(artifact, **changes)
    parent = ContentHash(sha256="0" * 64, encoding=HashEncoding.RAW)
    transform = Metadata(
        state=MetadataState.PRESENT,
        value=CanonicalObject.from_value(
            {
                "method": "synthetic-transform/1",
                "steps": ["first", "second"],
                "units": "angstrom",
            }
        ),
        reason=None,
    )
    derived = replace(artifact, parents=(parent,), transformation=transform)
    assert ArtifactDescriptor.from_json(derived.to_json()) == derived
    for parents, transformation in [
        ((parent,), artifact.transformation),
        ((parent, parent), transform),
        ((artifact.content_hash,), transform),
        ((artifact.content_hash, parent), transform),
        ((), transform),
    ]:
        with pytest.raises(ValueError):
            replace(artifact, parents=parents, transformation=transformation)


def test_rights_do_not_assume_redistribution_permission(
    artifact: ArtifactDescriptor,
) -> None:
    unknown = Metadata(
        state=MetadataState.UNAVAILABLE, value=None, reason="Unreviewed license"
    )
    with pytest.raises(ValueError, match="license"):
        replace(artifact.rights, license=unknown)
    assert replace(
        artifact.rights, license=unknown, redistribution=RedistributionStatus.UNKNOWN
    )
    with pytest.raises(ValueError):
        replace(artifact.rights, basis="")


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-11-10",
        "2026-11-10T00:00:00",
        "2026-11-10T01:00:00+01:00",
        "2026-02-30T00:00:00Z",
        "2026-11-10T00:00:60Z",
        "2026-11-10T00:00:00.1234567Z",
    ],
)
def test_timestamps_are_valid_explicit_utc(
    receipt: SourceReceipt, timestamp: str
) -> None:
    with pytest.raises(ValueError):
        replace(receipt, retrieved_at=timestamp)


def test_source_unordered_ids_require_sorted_unique_values(
    receipt: SourceReceipt,
) -> None:
    for values in (("z", "a"), ("a", "a"), ("",)):
        with pytest.raises(ValueError):
            ReferenceCollection(state=MetadataState.PRESENT, values=values, reason=None)
    references = ReferenceCollection(
        state=MetadataState.PRESENT, values=("a", "z"), reason=None
    )
    assert replace(receipt, citation_references=references)


@pytest.mark.parametrize(
    "state,values,reason",
    [
        (MetadataState.PRESENT, (), None),
        (MetadataState.PRESENT, ("citation:1",), "absent"),
        (MetadataState.UNAVAILABLE, ("citation:1",), "absent"),
        (MetadataState.UNAVAILABLE, (), None),
        (MetadataState.NOT_APPLICABLE, (), " "),
    ],
)
def test_reference_inventory_absence_is_explicit(
    state: MetadataState, values: tuple[str, ...], reason: str | None
) -> None:
    with pytest.raises(ValueError):
        ReferenceCollection(state=state, values=values, reason=reason)
    schema = {"$ref": "#/$defs/ReferenceCollection", "$defs": SCHEMA["$defs"]}
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(
            {"state": state.value, "values": list(values), "reason": reason}
        )


def test_source_fields_do_not_accept_invented_types(receipt: SourceReceipt) -> None:
    def present(value: str | int | bool) -> Metadata:
        return Metadata(state=MetadataState.PRESENT, value=value, reason=None)

    assert replace(
        receipt,
        accession=present("SYNTHETIC"),
        taxon_id=present(1),
        entry_version=present(1),
        sequence_version=present("v1"),
    )
    invalid_fields: list[tuple[str, str | int | bool]] = [
        ("accession", 1),
        ("entry_version", True),
        ("entry_version", " "),
        ("taxon_id", 0),
        ("taxon_id", True),
        ("taxon_id", "1"),
    ]
    for name, value in invalid_fields:
        changes: dict[str, Any] = {name: present(value)}
        with pytest.raises(ValueError):
            replace(receipt, **changes)


def test_license_references_are_textual(artifact: ArtifactDescriptor) -> None:
    for value in (1, " "):
        with pytest.raises(ValueError):
            replace(
                artifact.rights,
                license=Metadata(state=MetadataState.PRESENT, value=value, reason=None),
            )


def test_wrong_metadata_union_and_array_wire_types_are_rejected() -> None:
    with pytest.raises(ValueError):
        Metadata.from_dict({"state": "present", "value": [1, 2], "reason": None})
    changed = copy.deepcopy(EXAMPLES[1])
    changed["parents"] = {}
    with pytest.raises(ValueError):
        ArtifactDescriptor.from_dict(changed)


def test_prediction_skeletons_never_certify_a_success(record: ProvenanceRecord) -> None:
    assert record.status is RecordStatus.FAILED
    assert record.sections.execution.state is MetadataState.PRESENT
    assert replace(record, status=RecordStatus.CANCELLED)
    assert replace(record, status=RecordStatus.INCOMPLETE)
    for evidence in EvidenceKind:
        with pytest.raises(ValueError, match="successful prediction"):
            replace(
                record, evidence=evidence, artifacts=(), status=RecordStatus.RECORDED
            )
    changed = record.to_dict()
    changed["status"] = "succeeded"
    with pytest.raises(ValueError):
        ProvenanceRecord.from_dict(changed)
    with pytest.raises(ValidationError):
        VALIDATOR.validate(changed)


def test_evidence_categories_are_explicit_and_hypotheses_stay_separate(
    record: ProvenanceRecord,
) -> None:
    assert {kind.value for kind in EvidenceKind} == {
        "experimental",
        "predicted",
        "synthetic",
    }
    for evidence in EvidenceKind:
        changed = replace(record, evidence=evidence, artifacts=())
        assert ProvenanceRecord.from_json(changed.to_json()).evidence is evidence
    with pytest.raises(ValueError, match="Synthetic"):
        replace(
            record,
            artifacts=(replace(record.artifacts[0], evidence=EvidenceKind.PREDICTED),),
        )
    invalid_evidence: object
    for invalid_evidence in ("hypothesis", "fake", True, {}, None):
        changed_dict = record.to_dict()
        changed_dict["evidence"] = invalid_evidence
        with pytest.raises(ValueError):
            ProvenanceRecord.from_dict(changed_dict)


def test_manifest_rejects_ambiguous_inventory(record: ProvenanceRecord) -> None:
    for changes in (
        {"artifacts": record.artifacts * 2},
        {"inputs": record.inputs * 2},
        {"source_receipt_ids": ("z", "a")},
        {"warnings": (" ",)},
        {"record_id": ""},
        {"producer_version": " "},
    ):
        with pytest.raises(ValueError):
            replace(record, **changes)
    with pytest.raises(ValueError):
        ContentReference(record_id=" ", content_hash=record.inputs[0].content_hash)
    with pytest.raises(ValueError):
        ScientificInput(input_schema=" ", payload=CanonicalObject.from_value({}))

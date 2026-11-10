"""Authored offline M3 events/maps; no real structures or biological claims."""

import gzip
import json
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest
from test_uniprot import Fake, Time, catalog, entry, response

from neurofold.adapters.biological.alignment import PolymerMapper
from neurofold.adapters.biological.mmcif import (
    MmcifParser,
    ParseLimits,
    metadata,
    operations,
)
from neurofold.adapters.biological.policy import BoundedCache, RetryPolicy
from neurofold.adapters.biological.rcsb import (
    DATA,
    RcsbCatalog,
)
from neurofold.adapters.biological.storage import FilesystemStore
from neurofold.adapters.biological.structure_storage import FilesystemStructures
from neurofold.adapters.biological.transport import (
    MAX_DOWNLOAD,
    MAX_EXPANDED,
    MAX_HEADERS,
    Response,
    TransportFailure,
)
from neurofold.adapters.biological.uniprot import absent, present
from neurofold.application.references import ReferenceService
from neurofold.application.structures import StructureService
from neurofold.core.biological import (
    Availability,
    MappingCoverage,
    MappingStatus,
    ReferenceSnapshot,
    ResidueMap,
    StructureSelection,
)
from neurofold.core.canonical import CanonicalObject, sequence_sha256, sha256_bytes
from neurofold.core.lookup import CursorError, ProviderError, ProviderValidationError
from neurofold.core.provenance import ContentReference, EvidenceKind, MetadataState
from neurofold.core.structures import (
    ParsedStructure,
    PolymerResidue,
    RevisionUnavailable,
    StructureImport,
    StructureSourceChanged,
    UnsupportedStructure,
)

CIF = Path(__file__).parent / "fixtures/structure-synthetic-v1.cif"
REVISION = "1.0@2026-11-10"


def entry_data(identity: str = "1SYN", /, **changes: object) -> dict[str, object]:
    return {
        "rcsb_id": identity,
        "rcsb_entry_info": {
            "structure_determination_methodology": "experimental",
            "resolution_combined": [2.0],
        },
        "exptl": [{"method": "X-RAY DIFFRACTION"}],
        "rcsb_accession_info": {
            "major_revision": 1,
            "minor_revision": 0,
            "revision_date": "2026-11-10",
        },
        "rcsb_entry_container_identifiers": {"assembly_ids": ["1"]},
        "rcsb_primary_citation": {"pdbx_database_id_DOI": "synthetic:authored"},
        **changes,
    }


def instance_data(
    identity: str = "1SYN", /, chain: str = "A", **changes: object
) -> dict[str, object]:
    return {
        "rcsb_id": identity + "." + chain,
        "rcsb_polymer_entity_instance_container_identifiers": {
            "entry_id": identity,
            "asym_id": chain,
            "auth_asym_id": "X",
            "entity_id": "1",
        },
        **changes,
    }


def entity_data(
    identity: str = "1SYN", /, sequence: str = "ACDEFG", **changes: object
) -> dict[str, object]:
    return {
        "rcsb_id": identity + "_1",
        "rcsb_polymer_entity_container_identifiers": {
            "entry_id": identity,
            "entity_id": "1",
            "asym_ids": ["A", "B"],
            "reference_sequence_identifiers": [
                {"database_name": "UniProt", "database_accession": "P00001"}
            ],
        },
        "rcsb_entity_source_organism": [{"ncbi_taxonomy_id": 1}],
        "entity_poly": {
            "type": "polypeptide(L)",
            "pdbx_seq_one_letter_code_can": sequence,
        },
        **changes,
    }


def metadata_events(
    identity: str = "1SYN", /, sequence: str = "ACDEFG", **changes: object
) -> list[Response]:
    return [
        response(entry_data(identity, **changes), etag='"entry"'),
        response(instance_data(identity), etag='"instance"'),
        response(entity_data(identity, sequence), etag='"entity"'),
    ]


def coordinate_response(raw: bytes | None = None, **headers: str) -> Response:
    return Response(
        200,
        {"content-type": "chemical/x-mmcif", "etag": '"cif"', **headers},
        CIF.read_bytes() if raw is None else raw,
    )


def selection(**changes: object) -> StructureSelection:
    value = {
        "entity_id": "1",
        "label_asym_id": "A",
        "auth_asym_id": present("X"),
        "model_id": "1",
        "assembly_id": absent("Asymmetric unit", na=True),
        "operator_id": absent("No operator", na=True),
    }
    return StructureSelection.from_dict(
        {
            k: v.to_dict() if hasattr(v, "to_dict") else v
            for k, v in (value | changes).items()
        }
    )


def setup(
    tmp_path: Path, events: Sequence[Response | Exception], sequence: str = "ACDEFG"
) -> tuple[RcsbCatalog, FilesystemStore, ReferenceSnapshot, Fake, Time]:
    uniprot, store, time = catalog(
        tmp_path,
        Fake(response(entry(sequence={"value": sequence, "length": len(sequence)}))),
    )
    reference = ReferenceService(uniprot, store, store, new_id=lambda: "reference").pin(
        "P00001", sequence_sha256(sequence)
    )
    fake = Fake(*events)
    client = RcsbCatalog(
        fake,
        store.artifact_store,
        store,
        clock=time.clock,
        retry=RetryPolicy(jitter=lambda: 0.0),
        evidence=EvidenceKind.SYNTHETIC,
    )
    return client, store, reference, fake, time


def service(client: RcsbCatalog, store: FilesystemStore) -> StructureService:
    return StructureService(
        client,
        store,
        MmcifParser(),
        PolymerMapper(),
        FilesystemStructures(store),
        new_id=lambda: "structure",
    )


def imported(
    tmp_path: Path,
    *,
    raw: bytes | None = None,
    selected: StructureSelection | None = None,
) -> tuple[StructureImport, FilesystemStore, RcsbCatalog, Fake, Time]:
    client, store, reference, fake, time = setup(
        tmp_path, metadata_events() + [coordinate_response(raw), response(None, 304)]
    )
    record = service(client, store).import_selected(
        reference.reference_id, "1SYN", selected or selection(), present(REVISION)
    )
    return record, store, client, fake, time


def test_import_numbering_missing_coordinates_altloc_models_assembly_and_restart(
    tmp_path: Path,
) -> None:
    original = CIF.read_bytes()
    record, store, client, fake, _ = imported(
        tmp_path,
        selected=selection(
            model_id="2", assembly_id=present("1"), operator_id=present("2")
        ),
    )
    assert not fake.events
    assert len(fake.calls) == 5
    assert fake.calls[-1][1]["if-none-match"] == '"entry"'
    assert record.checks[-1].response_status == 304
    assert record.checks[-1].source_receipt_id == record.checks[0].source_receipt_id
    rows = record.mapping.rows
    assert [
        (
            r.reference_position.value,
            r.label_seq_id.value,
            r.auth_seq_id.value,
            r.coordinate_present,
            r.status,
        )
        for r in rows
    ] == [
        (1, 1, "-2", True, MappingStatus.EXACT),
        (2, 2, "0", True, MappingStatus.EXACT),
        (3, 3, "1", False, MappingStatus.UNOBSERVED),
        (4, 4, "2", True, MappingStatus.EXACT),
        (5, 5, None, False, MappingStatus.UNOBSERVED),
        (6, 6, "4", True, MappingStatus.EXACT),
    ]
    assert rows[3].insertion_code.value == "B"
    assert rows[4].auth_seq_id.state is MetadataState.UNAVAILABLE
    assert record.alignment.to_dict()["reference_coverage"] == {
        "numerator": 6,
        "denominator": 6,
    }
    assert record.alignment.to_dict()["coordinate_reference_coverage"] == {
        "numerator": 4,
        "denominator": 6,
    }
    details = record.parsing.to_dict()
    assert details["models"] == ["1", "2"]
    assert details["transform_applied"] is False
    assert details["coordinate_unit"] == "angstrom"
    assert "10" in json.dumps(record.parsing.to_dict())
    assert '"alt_id"' in json.dumps(record.parsing.to_dict())
    assert record.descriptor.raw_artifact.content_hash.sha256 == sha256_bytes(original)
    with store.open(record.descriptor.raw_artifact.artifact_id) as stream:
        assert stream.read() == original
    client.cache = BoundedCache()
    reopened = FilesystemStructures(FilesystemStore(store.root))
    assert reopened.get_import("structure") == record
    assert reopened.get_mapping("structure:map") == record.mapping
    assert reopened.get("structure") == record.descriptor
    assert service(client, store).get("structure") == record
    assert StructureImport.from_json(record.to_json()) == record


def test_metadata_absence_and_citations_and_actual_bytes(tmp_path: Path) -> None:
    events = metadata_events(
        rcsb_accession_info={},
        rcsb_primary_citation={},
        rcsb_entry_container_identifiers={},
        rcsb_entry_info={"structure_determination_methodology": "experimental"},
    )
    client, store, ref, _, _ = setup(tmp_path, events)
    source = client.inspect(ref, "1SYN", "A", fresh=True)
    assert source.summary.source_revision.state is MetadataState.UNAVAILABLE
    assert source.summary.resolutions[0].value.state is MetadataState.UNAVAILABLE
    assert source.summary.citations.state is MetadataState.UNAVAILABLE
    assert source.summary.assembly_ids.state is MetadataState.UNAVAILABLE
    assert (
        store.get_receipt(source.summary.source_receipt.receipt_id)
        == source.summary.source_receipt
    )


@pytest.mark.parametrize(
    "stage",
    [
        "expected_missing",
        "actual_missing",
        "before_changed",
        "cif_changed",
        "cif_missing",
        "final_changed",
        "final_missing",
    ],
)
def test_revisions_fail_closed_without_visible_import(
    tmp_path: Path, stage: str
) -> None:
    changes: dict[str, object] = {}
    if stage == "actual_missing":
        changes["rcsb_accession_info"] = {}
    if stage == "before_changed":
        changes["rcsb_accession_info"] = {
            "major_revision": 2,
            "minor_revision": 0,
            "revision_date": "2026-11-10",
        }
    raw = (
        CIF.read_bytes().replace(b"1 1 0 2026-11-10", b"1 2 0 2026-11-10")
        if stage == "cif_changed"
        else None
    )
    if stage == "cif_missing":
        raw = CIF.read_bytes().replace(b"1 1 0 2026-11-10", b"1 ? 0 2026-11-10")
    final = response(
        entry_data(
            rcsb_accession_info={}
            if stage == "final_missing"
            else {
                "major_revision": 2,
                "minor_revision": 0,
                "revision_date": "2026-11-10",
            }
        )
    )
    client, store, ref, _, _ = setup(
        tmp_path,
        metadata_events("1SYN", sequence="ACDEFG", **changes)
        + [coordinate_response(raw), final],
    )
    expected = (
        absent("No inspected revision")
        if stage == "expected_missing"
        else present(REVISION)
    )
    error = RevisionUnavailable if "missing" in stage else StructureSourceChanged
    with pytest.raises(error) as captured:
        service(client, store).import_selected(
            ref.reference_id, "1SYN", selection(), expected
        )
    if isinstance(captured.value, StructureSourceChanged):
        assert captured.value.expected == REVISION
        assert "2.0@" in captured.value.actual
    with pytest.raises(KeyError):
        FilesystemStructures(store).get("structure")


def test_fresh_304_all_resources_preserves_original_receipts(tmp_path: Path) -> None:
    events = (
        metadata_events()
        + [coordinate_response(), response(None, 304)]
        + [response(None, 304, etag='"checked"')] * 5
    )
    client, store, ref, fake, time = setup(tmp_path, events)
    first = service(client, store).import_selected(
        ref.reference_id, "1SYN", selection(), present(REVISION)
    )
    time.seconds += 10
    second = StructureService(
        client,
        store,
        MmcifParser(),
        PolymerMapper(),
        FilesystemStructures(store),
        new_id=lambda: "second",
    ).import_selected(ref.reference_id, "1SYN", selection(), present(REVISION))
    assert second.descriptor.raw_artifact == first.descriptor.raw_artifact
    assert (
        second.descriptor.source.source_receipt
        == first.descriptor.source.source_receipt
    )
    assert all(c.response_status == 304 for c in second.checks)
    assert second.checks[0].checked_at != first.checks[0].checked_at
    assert second.checks[0].response_headers.to_dict() == {
        "content-type": "application/json",
        "etag": '"checked"',
    }
    assert not fake.events


@pytest.mark.parametrize(
    "status,body", [(304, b""), (301, b""), (302, b""), (307, b""), (308, b"")]
)
def test_unsolicited_304_and_all_redirects_rejected(
    tmp_path: Path, status: int, body: bytes
) -> None:
    client, _, ref, fake, _ = setup(
        tmp_path,
        [
            Response(
                status, {"location": "https://files.rcsb.org/download/1SYN.cif"}, body
            )
        ],
    )
    with pytest.raises(ProviderValidationError):
        client.inspect(ref, "1SYN", "A", fresh=True)
    assert len(fake.calls) == 1


def test_body_bearing_304_rejected(tmp_path: Path) -> None:
    client, _, ref, _, _ = setup(
        tmp_path, metadata_events() + [Response(304, {}, b"bad")]
    )
    client.inspect(ref, "1SYN", "A", fresh=True)
    with pytest.raises(ProviderValidationError):
        client.revalidate("1SYN", REVISION)


@pytest.mark.parametrize(
    "mutant",
    [
        {"rcsb_id": "2BAD"},
        {"rcsb_entry_info": {"structure_determination_methodology": "computational"}},
        {"rcsb_entry_info": {}},
        {"exptl": []},
        {"exptl": [{"method": "THEORETICAL MODEL"}]},
        {"exptl": [{"method": "X-RAY DIFFRACTION"}] * 2},
        {
            "rcsb_accession_info": {
                "major_revision": 0,
                "minor_revision": 0,
                "revision_date": "2026-11-10",
            }
        },
        {
            "rcsb_accession_info": {
                "major_revision": 1,
                "minor_revision": -1,
                "revision_date": "2026-11-10",
            }
        },
        {
            "rcsb_accession_info": {
                "major_revision": 1,
                "minor_revision": 0,
                "revision_date": "bad",
            }
        },
        {"rcsb_primary_citation": []},
    ],
)
def test_invalid_entry_metadata(tmp_path: Path, mutant: dict[str, object]) -> None:
    client, _, ref, _, _ = setup(
        tmp_path, [response(entry_data("1SYN", **mutant))] + metadata_events()[1:]
    )
    with pytest.raises(ProviderValidationError):
        client.inspect(ref, "1SYN", "A", fresh=True)


@pytest.mark.parametrize(
    "kind,mutant",
    [
        ("instance", {"rcsb_id": "1SYN.B"}),
        (
            "instance",
            {
                "rcsb_polymer_entity_instance_container_identifiers": {
                    "entry_id": "2BAD",
                    "asym_id": "A",
                    "entity_id": "1",
                }
            },
        ),
        ("entity", {"rcsb_id": "1SYN_2"}),
        ("entity", {"rcsb_entity_source_organism": []}),
        ("entity", {"rcsb_entity_source_organism": [{"ncbi_taxonomy_id": 2}]}),
        (
            "entity",
            {
                "rcsb_polymer_entity_container_identifiers": {
                    "entry_id": "1SYN",
                    "entity_id": "1",
                    "asym_ids": ["A"],
                    "reference_sequence_identifiers": [],
                }
            },
        ),
        (
            "entity",
            {
                "entity_poly": {
                    "type": "polydeoxyribonucleotide",
                    "pdbx_seq_one_letter_code_can": "AC",
                }
            },
        ),
        (
            "entity",
            {
                "entity_poly": {
                    "type": "polypeptide(L)",
                    "pdbx_seq_one_letter_code_can": "A" * 10001,
                }
            },
        ),
    ],
)
def test_invalid_instance_entity_and_origin(
    tmp_path: Path, kind: str, mutant: dict[str, object]
) -> None:
    events = [
        response(entry_data()),
        response(
            instance_data("1SYN", chain="A", **mutant)
            if kind == "instance"
            else instance_data()
        ),
        response(
            entity_data("1SYN", sequence="ACDEFG", **mutant)
            if kind == "entity"
            else entity_data()
        ),
    ]
    client, _, ref, _, _ = setup(tmp_path, events)
    with pytest.raises((ProviderValidationError, UnsupportedStructure)):
        client.inspect(ref, "1SYN", "A", fresh=True)


def search_response(ids: list[str], total: int | None = None) -> Response:
    return response(
        {
            "total_count": len(ids) if total is None else total,
            "result_set": [{"identifier": identity} for identity in ids],
        }
    )


def test_discovery_multiple_pages_binding_cache_and_empty(tmp_path: Path) -> None:
    events = (
        [search_response(["1SYN.A"], 2)]
        + metadata_events()
        + [search_response(["2SYN.A"], 2)]
        + metadata_events("2SYN")
    )
    client, _, ref, fake, time = setup(tmp_path, events)
    first = client.discover(ref, limit=1)
    assert [i.entry_id for i in first.items] == ["1SYN"]
    cursor = str(first.next_cursor.value)
    query = json.loads(parse_qs(urlsplit(fake.calls[0][0]).query)["json"][0])
    assert query["request_options"]["results_content_type"] == ["experimental"]
    assert query["return_type"] == "polymer_instance"
    assert query["query"]["parameters"]["value"] == "P00001"
    assert (
        client.discover(ref, limit=1).items == first.items
    )  # warm cache, no new network
    with pytest.raises(CursorError):
        client.discover(ref, cursor=cursor, limit=2)
    second = client.discover(ref, cursor=cursor, limit=1)
    assert [i.entry_id for i in second.items] == ["2SYN"]
    assert second.next_cursor.state is MetadataState.NOT_APPLICABLE
    assert not fake.events
    time.seconds += 3601
    with pytest.raises(CursorError):
        client.discover(ref, cursor=cursor, limit=1)
    fake.events = [response(None, 204)]
    assert client.discover(ref).availability is Availability.COMPLETE


def test_discovery_partial_computed_rejection_and_unavailable(tmp_path: Path) -> None:
    events = (
        [search_response(["1SYN.A", "2SYN.A"])]
        + metadata_events()
        + [
            response(
                entry_data(
                    "2SYN",
                    rcsb_entry_info={
                        "structure_determination_methodology": "computational"
                    },
                )
            )
        ]
    )
    client, _, ref, _, _ = setup(tmp_path, events)
    result = client.discover(ref)
    assert result.availability is Availability.PARTIAL
    assert [i.entry_id for i in result.items] == ["1SYN"]
    assert "2SYN.A" in result.warnings[0]
    client.transport = Fake(
        response(None, 503), response(None, 503), response(None, 503)
    )
    unavailable = client.discover(ref, limit=10)
    assert unavailable.availability is Availability.UNAVAILABLE
    assert unavailable.items == ()


@pytest.mark.parametrize(
    "provider",
    [
        search_response(["AF_TEST.A"]),
        search_response(["2SYN.A", "1SYN.A"]),
        search_response(["1SYN.A"] * 2),
        search_response([], 1),
        search_response(["1SYN.A"], 0),
        Response(
            200,
            {"content-type": "application/json"},
            b'{"total_count":1,"total_count":2}',
        ),
        response({}, 204),
    ],
)
def test_discovery_invalid_is_not_empty_complete(
    tmp_path: Path, provider: Response
) -> None:
    client, _, ref, _, _ = setup(tmp_path, [provider])
    assert client.discover(ref).availability is Availability.UNAVAILABLE


def test_discovery_session_bound_and_invalid_cursors(tmp_path: Path) -> None:
    client, _, ref, fake, time = setup(tmp_path, [])
    with pytest.raises(ValueError):
        client.discover(ref, limit=0)
    with pytest.raises(CursorError):
        client.discover(ref, cursor="unknown")
    for i in range(1, 21):
        identity = str(1000 + i)
        fake.events.extend(
            [search_response([identity + ".A"], 21)] + metadata_events(identity)
        )
    cursor = None
    for _ in range(20):
        page = client.discover(ref, cursor=cursor, limit=1)
        cursor = str(page.next_cursor.value)
    assert page.availability is Availability.PARTIAL
    assert page.next_cursor.state is MetadataState.NOT_APPLICABLE
    assert time.seconds == 0


@pytest.mark.parametrize(
    "value", ["https://evil.test/a", "../1SYN", "AF_TEST", "1syn", "PDB_00001SYN"]
)
def test_unsupported_identifiers_never_reach_transport(
    tmp_path: Path, value: str
) -> None:
    client, _, ref, fake, _ = setup(tmp_path, [])
    with pytest.raises(UnsupportedStructure):
        client.inspect(ref, value, "A", fresh=True)
    assert not fake.calls


@pytest.mark.parametrize(
    "events",
    [
        [TransportFailure("offline"), response(entry_data())],
        [response(None, 429, **{"retry-after": "500"}), response(entry_data())],
        [response(None, 502), response(None, 504), response(entry_data())],
    ],
)
def test_retries_and_shared_deadline(
    tmp_path: Path, events: Sequence[Response | Exception]
) -> None:
    client, _, ref, fake, time = setup(tmp_path, [*events, *metadata_events()[1:]])
    assert client.inspect(ref, "1SYN", "A", fresh=True).summary.entry_id == "1SYN"
    assert all(0 < call[2] <= 15 for call in fake.calls)
    assert time.sleeps and max(time.sleeps) <= 5
    assert fake.calls[-1][2] < 15


def test_negative_cache_fresh_bypass_and_transient_not_negative(tmp_path: Path) -> None:
    client, _, _, fake, _ = setup(
        tmp_path, [response(None, 404), coordinate_response()]
    )
    url = "https://files.rcsb.org/download/1SYN.cif"
    with pytest.raises(KeyError):
        client._fetch(url, 15)
    with pytest.raises(KeyError):
        client._fetch(url, 15)
    assert len(fake.calls) == 1
    client.download("1SYN", REVISION)
    assert len(fake.calls) == 2
    client.transport = Fake(response(None, 500))
    with pytest.raises(ProviderError):
        client._fetch(DATA + "entry/2SYN", 15)
    assert client.cache.get("missing") is None


@pytest.mark.parametrize(
    "provider",
    [
        Response(200, {"content-type": "text/html"}, b"html"),
        Response(
            200, {"content-type": "chemical/x-mmcif", "content-length": "100"}, b"short"
        ),
        Response(
            200, {"content-type": "chemical/x-mmcif", "content-encoding": "br"}, b"x"
        ),
        Response(200, {"content-type": "chemical/x-mmcif"}, b"x" * (MAX_DOWNLOAD + 1)),
        Response(200, {"X": "x" * (MAX_HEADERS + 1)}, b""),
        Response(
            200,
            {"content-type": "chemical/x-mmcif", "content-encoding": "gzip"},
            gzip.compress(b"x" * (MAX_EXPANDED + 1)),
        ),
        Response(
            200,
            {"content-type": "chemical/x-mmcif", "content-encoding": "gzip"},
            gzip.compress(b"x")[:-1],
        ),
        Response(
            200,
            {"content-type": "chemical/x-mmcif", "content-encoding": "gzip"},
            gzip.compress(b"x") + gzip.compress(b"y"),
        ),
    ],
)
def test_download_bounds_and_invalid_content(
    tmp_path: Path, provider: Response
) -> None:
    client, _, _, _, _ = setup(tmp_path, [provider])
    with pytest.raises(ProviderValidationError):
        client.download("1SYN", REVISION)


def test_gzip_preserves_original_and_separate_parse_description(tmp_path: Path) -> None:
    original = gzip.compress(CIF.read_bytes(), mtime=0)
    client, store, ref, _, _ = setup(
        tmp_path,
        metadata_events()
        + [
            coordinate_response(original, **{"content-encoding": "gzip"}),
            response(None, 304),
        ],
    )
    record = service(client, store).import_selected(
        ref.reference_id, "1SYN", selection(), present(REVISION)
    )
    with store.open(record.descriptor.raw_artifact.artifact_id) as stream:
        assert stream.read() == original
    assert record.descriptor.raw_artifact.media_type == "application/gzip"
    assert record.descriptor.raw_artifact.parents == ()
    assert record.mapping.rows[0].coordinate_present


@pytest.mark.parametrize(
    "before,after",
    [
        (b"data_1SYN", b"data_1SYN\n_bad 'unterminated"),
        (b"data_1SYN", b"data_1SYN\n_entry.id 2BAD"),
        (b"_entry.id 1SYN", b"_entry.id 2BAD"),
        (b"'X-RAY DIFFRACTION'", b"'THEORETICAL MODEL'"),
        (b"_entry.id 1SYN", b"_entry.id 1SYN\n_ma_model_list.model_id 1"),
        (b"1 1 ALA\n", b"1 2 ALA\n"),
        (b"1 2 CYS\n", b"1 1 CYS\n"),
        (b"1 2 CYS\n", b"1 2 TYR\n"),
        (b"A 1\n", b"A 2\n"),
        (b"polypeptide(L)", b"polydeoxyribonucleotide"),
        (b"A 1 1 ALA -2 -2 X .", b"A 1 1 GLY -2 -2 X ."),
        (b"A 1 1 ALA -2 -2 X .", b"A 2 1 ALA -2 -2 X ."),
        (b"A 1 1 ALA -2 -2 X .", b"A 1 1 ALA -2 -2 Z ."),
        (
            b"1 1 A X 1 -2 . ALA CA . 1 1.0 1.0 0.0 1.0",
            b"1 1 A X 1 -2 . ALA CA . 1 nan 1.0 0.0 1.0",
        ),
        (
            b"1 1 A X 1 -2 . ALA CA . 1 1.0 1.0 0.0 1.0",
            b"1 1 A X 1 -2 . ALA CA . 1 1e8 1.0 0.0 1.0",
        ),
        (
            b"1 1 A X 1 -2 . ALA CA . 1 1.0 1.0 0.0 1.0",
            b"1 1 A X 1 -2 . ALA CA . 1 bad 1.0 0.0 1.0",
        ),
        (
            b"1 1 A X 1 -2 . ALA CA . 1 1.0 1.0 0.0 1.0",
            b"1 1 A X 1 -2 . ALA CA . 1 1.0 1.0 0.0 2.0",
        ),
        (b"1 1 A X 1 -2 . ALA CA . 1", b"1 1 A X 1 -2 . ALA CA . 0"),
        (b"1 1 A X 1 -2 . ALA CA . 1", b"1 1 A Z 1 -2 . ALA CA . 1"),
        (b"1 1 A X 1 -2 . ALA CA . 1", b"1 2 A X 1 -2 . ALA CA . 1"),
        (b"1 1 A X 1 -2 . ALA CA . 1", b"1 1 A X ? -2 . ALA CA . 1"),
        (b"1 1 A X 1 -2 . ALA CA . 1", b"1 1 A X 7 -2 . ALA CA . 1"),
        (b"1 1 A X 1 -2 . ALA CA . 1", b"1 1 A X 1 -2 . GLY CA . 1"),
        (b"1 1 A X 1 -2 . ALA CA . 1", b"1 1 A X 1 -3 . ALA CA . 1"),
        (
            b"_pdbx_struct_assembly_gen.assembly_id 1",
            b"_pdbx_struct_assembly_gen.assembly_id 2",
        ),
        (b"'(1-2)'", b"'(1-3)'"),
        (b"asym_id_list A,B", b"asym_id_list A,Z"),
        (b"asym_id_list A,B", b"asym_id_list A,A"),
        (b"2 1 0 0 0 1 0 0 0 1 10 0 0", b"2 1 0 0 0 1 0 0 0 1 inf 0 0"),
    ],
)
def test_malformed_or_inconsistent_cif_rejected(
    tmp_path: Path, before: bytes, after: bytes
) -> None:
    client, _, ref, _, _ = setup(tmp_path, metadata_events())
    summary = client.inspect(ref, "1SYN", "A", fresh=True).summary
    raw = CIF.read_bytes()
    assert before in raw
    with pytest.raises((ProviderValidationError, UnsupportedStructure)):
        MmcifParser().parse(raw.replace(before, after), summary, selection())


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"data_a\nloop_\n_x.a\n_x.b\n1",
        b"data_a\nsave_s\n_x.a 1\nsave_\n",
        b"data_a\n_x.a 1\ndata_b\n_x.a 2\n",
        b"\xff",
        b"x" * (MAX_EXPANDED + 1),
    ],
)
def test_invalid_cif_syntax_truncation_frames_blocks_and_bytes(
    tmp_path: Path, raw: bytes
) -> None:
    client, _, ref, _, _ = setup(tmp_path, metadata_events())
    summary = client.inspect(ref, "1SYN", "A", fresh=True).summary
    with pytest.raises((ProviderValidationError, UnsupportedStructure)):
        MmcifParser().parse(raw, summary, selection())


@pytest.mark.parametrize(
    "limits",
    [
        ParseLimits(cells=10),
        ParseLimits(token=5),
        ParseLimits(atoms=19),
        ParseLimits(residues=5),
        ParseLimits(chains=1),
        ParseLimits(models=1),
        ParseLimits(operators=1),
        ParseLimits(copies=3),
        ParseLimits(expanded_atoms=39),
    ],
)
def test_parser_resource_limits(tmp_path: Path, limits: ParseLimits) -> None:
    client, _, ref, _, _ = setup(tmp_path, metadata_events())
    summary = client.inspect(ref, "1SYN", "A", fresh=True).summary
    with pytest.raises(UnsupportedStructure):
        MmcifParser(limits).parse(CIF.read_bytes(), summary, selection())


def test_parser_boundaries_and_limit_configuration(tmp_path: Path) -> None:
    client, _, ref, _, _ = setup(tmp_path, metadata_events())
    summary = client.inspect(ref, "1SYN", "A", fresh=True).summary
    parsed = MmcifParser(
        ParseLimits(
            atoms=20,
            residues=6,
            chains=2,
            models=2,
            assemblies=1,
            operators=2,
            copies=4,
            expanded_atoms=40,
        )
    ).parse(CIF.read_bytes(), summary, selection())
    assert len(parsed.residues) == 6
    with pytest.raises(ValueError):
        ParseLimits(atoms=50001)
    with pytest.raises(ValueError):
        ParseLimits(atoms=0)
    with pytest.raises(ValueError):
        PolymerMapper(max_paths=257)
    with pytest.raises(ValueError):
        PolymerMapper(max_cells=0)


@pytest.mark.parametrize(
    "selected",
    [
        selection(model_id="3"),
        selection(entity_id="2"),
        selection(assembly_id=present("1"), operator_id=present("3")),
        selection(assembly_id=absent("Unknown")),
        selection(auth_asym_id=present("Z")),
    ],
)
def test_unsupported_selected_instances(
    tmp_path: Path, selected: StructureSelection
) -> None:
    client, store, ref, _, _ = setup(
        tmp_path, metadata_events() + [coordinate_response()]
    )
    with pytest.raises(UnsupportedStructure):
        service(client, store).import_selected(
            ref.reference_id, "1SYN", selected, present(REVISION)
        )


@pytest.mark.parametrize(
    "expression,expected",
    [
        ("1", (("1",),)),
        ("(1-2)(3,4)", (("1", "3"), ("1", "4"), ("2", "3"), ("2", "4"))),
        ("X0,2", (("X0",), ("2",))),
    ],
)
def test_operator_expression_preserves_product_order(
    expression: str, expected: tuple[tuple[str, ...], ...]
) -> None:
    assert operations(expression, 256) == expected


@pytest.mark.parametrize(
    "expression",
    [
        "(1-256)(1-2)",
        "1-999999999",
        "3-1",
        "1,1",
        "(1)x(2)",
        "",
        "?",
        "1/2",
        "x" * 4097,
    ],
)
def test_operator_expression_bounds_and_unsupported_syntax(expression: str) -> None:
    with pytest.raises(UnsupportedStructure):
        operations(expression, 256)


def test_modified_residue_parent_and_unknown_chemistry_are_explicit(
    tmp_path: Path,
) -> None:
    raw = (
        CIF.read_bytes().replace(b"PHE", b"MSE")
        + b"\n_chem_comp.id MSE\n_chem_comp.mon_nstd_parent_comp_id MET\n"
    )
    client, store, ref, _, _ = setup(
        tmp_path,
        metadata_events(sequence="ACDEMG")
        + [coordinate_response(raw), response(None, 304)],
    )
    record = service(client, store).import_selected(
        ref.reference_id, "1SYN", selection(), present(REVISION)
    )
    row = record.mapping.rows[4]
    assert row.status is MappingStatus.MISMATCH
    assert row.observed_residue.value == "M"
    assert not row.coordinate_present
    assert record.parsing.to_dict()["modified_residues"] == [
        {"label_seq_id": 5, "component": "MSE", "parent": "MET", "normalized": "M"}
    ]
    unknown_raw = raw.replace(b"parent_comp_id MET", b"parent_comp_id 'MET,ALA'")
    other = tmp_path / "other"
    client, store, ref, _, _ = setup(
        other,
        metadata_events(sequence="ACDEXG")
        + [coordinate_response(unknown_raw), response(None, 304)],
    )
    record = service(client, store).import_selected(
        ref.reference_id, "1SYN", selection(), present(REVISION)
    )
    assert record.mapping.rows[4].status is MappingStatus.AMBIGUOUS
    assert record.mapping.rows[4].candidate_reference_positions == (5,)
    assert record.mapping.rows[-1].reference_position.value == 5


def test_no_scheme_does_not_invent_missing_author_numbers(tmp_path: Path) -> None:
    raw = CIF.read_bytes()
    start, end = (
        raw.index(b"loop_\n_pdbx_poly_seq_scheme"),
        raw.index(b"loop_\n_atom_site"),
    )
    raw = raw[:start] + raw[end:]
    record, _, _, _, _ = imported(tmp_path, raw=raw)
    assert record.mapping.rows[0].auth_seq_id.value == "-2"
    assert record.mapping.rows[2].auth_seq_id.state is MetadataState.UNAVAILABLE
    assert record.mapping.rows[2].insertion_code.state is MetadataState.UNAVAILABLE
    assert metadata("?", "x").state is MetadataState.UNAVAILABLE
    assert metadata(".", "x").state is MetadataState.NOT_APPLICABLE


def test_zero_occupancy_is_not_observed(tmp_path: Path) -> None:
    raw = CIF.read_bytes().replace(
        b"1 1 A X 1 -2 . ALA CA . 1 1.0 1.0 0.0 1.0",
        b"1 1 A X 1 -2 . ALA CA . 1 1.0 1.0 0.0 0.0",
    )
    record, _, _, _, _ = imported(tmp_path, raw=raw)
    assert record.mapping.rows[0].status is MappingStatus.UNOBSERVED


def mapped(
    tmp_path: Path,
    reference_sequence: str,
    polymer: str,
    mapper: PolymerMapper | None = None,
) -> tuple[ResidueMap, CanonicalObject]:
    client, _, ref, _, _ = setup(
        tmp_path, [coordinate_response()], sequence=reference_sequence
    )
    download = client.download("1SYN", REVISION)
    parsed = ParsedStructure(
        polymer,
        tuple(
            PolymerResidue(
                i, code, present(str(i - 3)), absent("No insertion", na=True), True
            )
            for i, code in enumerate(polymer, 1)
        ),
        CanonicalObject.from_value({}),
    )
    return (mapper or PolymerMapper()).map(ref, "mapped", download, selection(), parsed)


@pytest.mark.parametrize(
    "reference,polymer,expected",
    [
        (
            "ACDEFG",
            "CDE",
            [
                (1, 2, "exact"),
                (2, 3, "exact"),
                (3, 4, "exact"),
                (None, 1, "unmapped"),
                (None, 5, "unmapped"),
                (None, 6, "unmapped"),
            ],
        ),
        (
            "ACDEFG",
            "ACNEFG",
            [
                (1, 1, "exact"),
                (2, 2, "exact"),
                (3, 3, "mismatch"),
                (4, 4, "exact"),
                (5, 5, "exact"),
                (6, 6, "exact"),
            ],
        ),
        (
            "ACDEFG",
            "HHACDEFG",
            [
                (1, None, "unmapped"),
                (2, None, "unmapped"),
                (3, 1, "exact"),
                (4, 2, "exact"),
                (5, 3, "exact"),
                (6, 4, "exact"),
                (7, 5, "exact"),
                (8, 6, "exact"),
            ],
        ),
    ],
)
def test_independent_unique_fragment_substitution_and_tag_maps(
    tmp_path: Path,
    reference: str,
    polymer: str,
    expected: list[tuple[int | None, int | None, str]],
) -> None:
    mapping, audit = mapped(tmp_path, reference, polymer)
    assert [
        (row.label_seq_id.value, row.reference_position.value, row.status.value)
        for row in mapping.rows
    ] == expected
    assert audit.to_dict()["optimal_path_count"] == 1
    assert audit.to_dict()["polymer_coverage"] == {
        "numerator": sum(
            row.status
            in (MappingStatus.EXACT, MappingStatus.MISMATCH, MappingStatus.UNOBSERVED)
            for row in mapping.rows
        ),
        "denominator": len(polymer),
    }


def test_repeated_domain_alignment_is_ambiguous_not_first_path(tmp_path: Path) -> None:
    mapping, audit = mapped(tmp_path, "ACDACD", "ACD")
    assert audit.to_dict()["optimal_path_count"] == 2
    assert [row.candidate_reference_positions for row in mapping.rows[:3]] == [
        (1, 4),
        (2, 5),
        (3, 6),
    ]
    assert all(row.status is MappingStatus.AMBIGUOUS for row in mapping.rows[:3])
    assert [row.reference_position.value for row in mapping.rows[3:]] == [
        1,
        2,
        3,
        4,
        5,
        6,
    ]
    assert audit.to_dict()["reference_coverage"] == {"numerator": 0, "denominator": 6}
    with pytest.raises(UnsupportedStructure, match="optimal alignments"):
        mapped(tmp_path / "overflow", "ACDACD", "ACD", PolymerMapper(max_paths=1))
    with pytest.raises(UnsupportedStructure, match="cell limit"):
        mapped(tmp_path / "cells", "ACDEFG", "ACDEFG", PolymerMapper(max_cells=35))


def test_internal_reference_gap_is_not_a_missing_coordinate(tmp_path: Path) -> None:
    # Long flanks make the scored internal deletion preferable to substitutions.
    mapping, _ = mapped(tmp_path, "ACDEFGHIKLMNPQRSTVWY", "ACDEFGHILMNPQRSTVWY")
    gap = [row for row in mapping.rows if row.label_seq_id.value is None]
    assert len(gap) == 1
    assert gap[0].reference_position.value == 9
    assert gap[0].reference_residue.value == "K"
    assert gap[0].status is MappingStatus.UNMAPPED


def test_immutable_conflict_atomic_interruption_and_integrity(tmp_path: Path) -> None:
    record, store, _, _, _ = imported(tmp_path)
    repo = FilesystemStructures(store)
    repo.publish_import(record)
    repo.publish(record.descriptor, record.mapping)
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(repo.publish_import, [record] * 6))
    different = replace(
        record, alignment=CanonicalObject.from_value({"different": True})
    )
    with pytest.raises(ValueError, match="Conflicting"):
        repo.publish_import(different)
    with pytest.raises(ValueError, match="Conflicting"):
        repo.publish(
            replace(record.descriptor, format="mmcif", mapping=absent("missing")),
            record.mapping,
        )
    with pytest.raises(KeyError):
        repo.get_mapping("unknown")
    new = replace(record.descriptor, structure_id="other", mapping=absent("missing"))
    with pytest.raises(ValueError, match="complete import audit"):
        repo.publish(new, record.mapping)
    target = store._path("structure", "structure")
    target.unlink()
    with patch(
        "neurofold.adapters.biological.storage.os.link",
        side_effect=OSError("interrupted"),
    ):
        with pytest.raises(OSError):
            repo.publish_import(record)
    with pytest.raises(KeyError):
        repo.get("structure")
    assert not [p for p in store.root.iterdir() if p.name.startswith("tmp")]
    repo.publish_import(record)
    raw_path = store._path("artifact", record.descriptor.raw_artifact.artifact_id)
    raw_path.write_bytes(raw_path.read_bytes().replace(b"Q", b"R", 1))
    with pytest.raises(ValueError):
        FilesystemStructures(FilesystemStore(store.root)).get("structure")


def test_missing_dependency_and_wrong_map_reference_fail(tmp_path: Path) -> None:
    record, store, _, _, _ = imported(tmp_path)
    ref = store.get(record.reference.record_id)
    wrong = replace(
        record.mapping.rows[0],
        reference_residue=present("G"),
        status=MappingStatus.MISMATCH,
        reason="bad",
    )
    wrong_map = replace(record.mapping, rows=(wrong,) + record.mapping.rows[1:])
    wrong_descriptor = replace(
        record.descriptor,
        mapping=ContentReference(
            record_id=wrong_map.mapping_id, content_hash=wrong_map.content_hash
        ),
    )
    bad = replace(record, descriptor=wrong_descriptor, mapping=wrong_map)
    with pytest.raises(ValueError, match="actual pinned reference"):
        bad.validate_reference(ref)
    with pytest.raises(ValueError, match="hash mismatch"):
        replace(record, mapping=wrong_map)
    with pytest.raises(ValueError, match="validation checks"):
        replace(record, checks=())
    store._path("receipt", record.checks[1].source_receipt_id).unlink()
    with pytest.raises(ValueError, match="dependency missing"):
        FilesystemStructures(store).get_import("structure")


def test_gap_alternatives_and_unknown_components_never_force_assignment(
    tmp_path: Path,
) -> None:
    mapping, audit = mapped(tmp_path, "AAA", "AAAA")
    assert audit.to_dict()["optimal_path_count"] == 4
    assert all(row.status is MappingStatus.AMBIGUOUS for row in mapping.rows[:4])
    assert any("gap alternative" in str(row.reason) for row in mapping.rows[:4])
    assert mapping.rows[0].candidate_reference_positions == (1,)
    assert mapping.rows[3].candidate_reference_positions == (3,)


def test_discovery_204_and_empty_200_are_cached_with_receipts(tmp_path: Path) -> None:
    client, store, ref, fake, _ = setup(tmp_path, [response(None, 204)])
    first = client.discover(ref)
    assert first.items == () and first.availability is Availability.COMPLETE
    assert client.discover(ref) == first
    assert len(fake.calls) == 1
    client, _, ref, fake, _ = setup(tmp_path / "empty", [search_response([])])
    page = client.discover(ref)
    assert page.items == () and page.availability is Availability.COMPLETE
    assert page.source_receipts


def test_real_schema_citation_types_and_date_time_revisions(tmp_path: Path) -> None:
    client, store, ref, _, _ = setup(
        tmp_path,
        metadata_events(
            rcsb_primary_citation={
                "pdbx_database_id_PubMed": 1,
                "pdbx_database_id_DOI": "synthetic:authored",
            },
            rcsb_accession_info={
                "major_revision": 1,
                "minor_revision": 0,
                "revision_date": "2026-11-10T00:00:00+0000",
            },
        )
        + [coordinate_response(), response(None, 304)],
    )
    record = service(client, store).import_selected(
        ref.reference_id, "1SYN", selection(), present("1.0@2026-11-10T00:00:00+0000")
    )
    assert record.descriptor.source.citations.values == (
        "doi:synthetic:authored",
        "pubmed:1",
    )
    assert (
        record.descriptor.source.source_receipt.citation_references.values
        == record.descriptor.source.citations.values
    )


def test_call_budgets_and_provider_capacity_and_configuration(tmp_path: Path) -> None:
    client, store, ref, fake, time = setup(tmp_path, [response(None, 503)])
    client.retry = RetryPolicy(budget=0.1, jitter=lambda: 0)
    with pytest.raises(ProviderError):
        client.inspect(ref, "1SYN", "A", fresh=True)
    assert not time.sleeps
    with pytest.raises(ProviderError):
        client._request(DATA + "entry/1SYN", {}, time.seconds - 1)
    with pytest.raises(ProviderValidationError):
        client._request("https://evil.test/1SYN", {}, 15)
    with pytest.raises(UnsupportedStructure):
        client.inspect(ref, "1SYN", "../A", fresh=True)
    with pytest.raises(ValueError):
        RcsbCatalog(fake, store.artifact_store, store, download_host="evil.test")
    with pytest.raises(ValueError):
        RcsbCatalog(fake, store.artifact_store, store, evidence=EvidenceKind.PREDICTED)
    with patch("neurofold.adapters.biological.rcsb.PROVIDER_SLOTS") as slots:
        slots.acquire.return_value = False
        with pytest.raises(ProviderError, match="concurrency"):
            client._request(DATA + "entry/1SYN", {}, 15)
    with patch.object(client, "lock") as lock:
        lock.acquire.return_value = False
        with pytest.raises(ProviderError, match="catalog budget"):
            client.inspect(ref, "1SYN", "A", fresh=True)


def test_transport_overrun_rejected_and_retries_exhaust(tmp_path: Path) -> None:
    client, _, ref, _, time = setup(tmp_path, [])

    class Slow:
        def request(
            self, url: str, headers: Mapping[str, str], *, timeout: float
        ) -> Response:
            time.seconds += timeout
            return response(entry_data())

    client.transport = Slow()
    with pytest.raises(ProviderError, match="budget"):
        client.inspect(ref, "1SYN", "A", fresh=True)
    client.transport = Fake(*[TransportFailure("offline")] * 3)
    with pytest.raises(ProviderError, match="retry"):
        client.inspect(ref, "1SYN", "A", fresh=True)


@pytest.mark.parametrize(
    "mutation",
    [
        "envelope",
        "checksum",
        "identity",
        "reference",
        "coordinate_receipt",
        "final_revision",
        "final_url",
    ],
)
def test_bundle_and_dependency_integrity_rejections(
    tmp_path: Path, mutation: str
) -> None:
    record, store, _, _, _ = imported(tmp_path)
    repo = FilesystemStructures(store)
    if mutation == "envelope":
        store._path("structure", "structure").write_bytes(b"{}")
    elif mutation == "checksum":
        path = store._path("structure", "structure")
        path.write_bytes(path.read_bytes().replace(b"angstrom", b"nanomete"))
    elif mutation == "identity":
        store._path("structure", "other").write_bytes(
            store._path("structure", "structure").read_bytes()
        )
        with pytest.raises(ValueError, match="identity"):
            repo.get_import("other")
        return
    elif mutation == "reference":
        bad = replace(
            record,
            reference=ContentReference(
                record_id=record.reference.record_id,
                content_hash=record.mapping.content_hash,
            ),
        )
        with pytest.raises(ValueError, match="reference identity"):
            repo.publish_import(bad)
        return
    elif mutation == "coordinate_receipt":
        bad = replace(
            record,
            checks=tuple(
                record.checks[0]
                if store.get_receipt(check.source_receipt_id).raw_artifact
                == record.descriptor.raw_artifact
                else check
                for check in record.checks
            ),
        )
        with pytest.raises(ValueError, match="coordinate receipt"):
            repo.publish_import(bad)
        return
    else:
        receipt = store.get_receipt(record.checks[-1].source_receipt_id)
        bad_receipt = replace(
            receipt,
            receipt_id="bad-final",
            entry_version=present("2.0@2026-11-10")
            if mutation == "final_revision"
            else receipt.entry_version,
            query=DATA + "entry/2BAD" if mutation == "final_url" else receipt.query,
        )
        store.publish_receipt(bad_receipt)
        bad = replace(
            record,
            checks=record.checks[:-1]
            + (replace(record.checks[-1], source_receipt_id="bad-final"),),
        )
        with pytest.raises(
            ValueError,
            match="revision mismatch"
            if mutation == "final_revision"
            else "different entry",
        ):
            repo.publish_import(bad)
        return
    with pytest.raises(ValueError):
        repo.get_import("structure")


def test_unknown_author_chain_stays_unknown(tmp_path: Path) -> None:
    raw = CIF.read_bytes().replace(b" X ", b" ? ")
    events = metadata_events()
    instance = instance_data()
    ids = instance["rcsb_polymer_entity_instance_container_identifiers"]
    assert isinstance(ids, dict)
    ids.pop("auth_asym_id")
    events[1] = response(instance)
    client, store, ref, _, _ = setup(
        tmp_path, [*events, coordinate_response(raw), response(None, 304)]
    )
    record = service(client, store).import_selected(
        ref.reference_id,
        "1SYN",
        selection(auth_asym_id=absent("Author chain not supplied")),
        present(REVISION),
    )
    assert record.descriptor.selection.auth_asym_id.state is MetadataState.UNAVAILABLE
    assert record.mapping.rows[0].auth_seq_id.value == "-2"


def test_assembly_inventory_and_duplicate_generation_rejected(tmp_path: Path) -> None:
    client, _, ref, _, _ = setup(tmp_path, metadata_events())
    source = client.inspect(ref, "1SYN", "A", fresh=True).summary
    raw = CIF.read_bytes()
    with pytest.raises(ProviderValidationError, match="assembly inventory"):
        MmcifParser().parse(
            raw.replace(
                b"_pdbx_struct_assembly.id 1", b"loop_\n_pdbx_struct_assembly.id\n1\n2"
            ),
            source,
            selection(),
        )
    with pytest.raises(UnsupportedStructure, match="Assembly/operator count"):
        MmcifParser(ParseLimits(assemblies=1)).parse(
            raw.replace(
                b"_pdbx_struct_assembly.id 1", b"loop_\n_pdbx_struct_assembly.id\n1\n2"
            ),
            source,
            selection(),
        )
    start = raw.index(b"_pdbx_struct_assembly_gen.assembly_id")
    duplicated = (
        raw[:start] + b"loop_\n_pdbx_struct_assembly_gen.assembly_id\n"
        b"_pdbx_struct_assembly_gen.oper_expression\n"
        b"_pdbx_struct_assembly_gen.asym_id_list\n"
        b"1 '(1-2)' A,B\n1 '(1-2)' A,B\n"
    )
    with pytest.raises(ProviderValidationError, match="Duplicate generated"):
        MmcifParser().parse(duplicated, source, selection())


def test_reference_completeness_and_typed_coverage_validated(tmp_path: Path) -> None:
    record, store, _, _, _ = imported(tmp_path)
    ref = store.get("reference")
    missing = replace(record.mapping, rows=record.mapping.rows[1:])
    descriptor = replace(
        record.descriptor,
        mapping=ContentReference(
            record_id=missing.mapping_id, content_hash=missing.content_hash
        ),
        source=replace(
            record.descriptor.source,
            mapped_coverage=MappingCoverage(mapped_positions=5, reference_length=6),
        ),
    )
    bad = replace(record, descriptor=descriptor, mapping=missing)
    with pytest.raises(ValueError, match="omits reference"):
        bad.validate_reference(ref)
    with pytest.raises(ValueError, match="coverage mismatch"):
        replace(
            record,
            descriptor=replace(
                record.descriptor,
                source=replace(
                    record.descriptor.source, mapped_coverage=absent("unknown")
                ),
            ),
        ).validate_reference(ref)


def test_scheme_author_and_coordinate_numbering_are_distinct(tmp_path: Path) -> None:
    # The dictionary permits author scheme numbers that differ from coordinate IDs.
    raw = CIF.read_bytes().replace(b"A 1 1 ALA -2 -2 X .", b"A 1 1 ALA 900 -2 X .")
    record, _, _, _, _ = imported(tmp_path, raw=raw)
    assert record.mapping.rows[0].auth_seq_id.value == "-2"
    details = record.parsing.to_dict()["selected_residues"]
    assert isinstance(details, list) and isinstance(details[0], dict)
    assert details[0]["scheme_author_number"]["value"] == "900"
    assert details[0]["scheme_pdb_number"]["value"] == "-2"


def test_absent_coordinate_identifier_columns_remain_explicit(tmp_path: Path) -> None:
    # Strip optional author/insertion/alt columns, preserving required labels.
    raw = CIF.read_text()
    start = raw.index("loop_\n_atom_site.id")
    end = raw.index("_pdbx_struct_assembly.id")
    atom_lines = raw[start:end].splitlines()
    remove = {3, 5, 6, 9}
    fields = [line for line in atom_lines if line.startswith("_atom_site.")]
    rows = [line.split() for line in atom_lines if line and line[0].isdigit()]
    # Removing alt IDs from otherwise duplicate alternate atoms is unsupported;
    # retain one authored alt per residue explicitly in this generated input.
    rows = [row for row in rows if row[9] != "B"]
    section = (
        "loop_\n"
        + "\n".join(field for i, field in enumerate(fields) if i not in remove)
        + "\n"
    )
    section += (
        "\n".join(
            " ".join(value for i, value in enumerate(row) if i not in remove)
            for row in rows
        )
        + "\n"
    )
    record, _, _, _, _ = imported(
        tmp_path, raw=(raw[:start] + section + raw[end:]).encode()
    )
    assert record.mapping.rows[0].auth_seq_id.value == "-2"  # retained PDB scheme
    residues = record.parsing.to_dict()["selected_residues"]
    assert isinstance(residues, list) and isinstance(residues[0], dict)
    assert residues[0]["atoms"][0]["auth_seq_id"]["state"] == "unavailable"
    assert "column not supplied" in residues[0]["atoms"][0]["alt_id"]["reason"]


def test_final_authoritative_malformed_response_is_provider_error(
    tmp_path: Path,
) -> None:
    client, store, ref, _, _ = setup(
        tmp_path,
        metadata_events()
        + [
            coordinate_response(),
            Response(200, {"content-type": "application/json"}, b'{"rcsb_id":'),
        ],
    )
    with pytest.raises(ProviderValidationError, match="authoritative"):
        service(client, store).import_selected(
            ref.reference_id, "1SYN", selection(), present(REVISION)
        )
    with pytest.raises(KeyError):
        FilesystemStructures(store).get("structure")

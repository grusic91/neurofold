"""Synthetic NF-02 contracts; no retrieval, parsing or scientific assertions."""

import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any

import pytest

from neurofold.api import biological as http
from neurofold.core import biological as bio
from neurofold.core._contracts import Contract
from neurofold.core.provenance import (
    ContentHash,
    ContentReference,
    EvidenceKind,
    HashEncoding,
    Metadata,
)

FIXTURES = Path(__file__).parent / "fixtures"


def fixture() -> dict[str, Any]:
    return json.loads((FIXTURES / "biological-v1.json").read_bytes())  # type: ignore[no-any-return]


RECORDS: list[tuple[str, type[Contract], type[http.DTO]]] = [
    ("reference", bio.ReferenceSnapshot, http.ReferenceResponse),
    ("protein_page", bio.ProteinPage, http.ProteinPageResponse),
    ("structure_page", bio.StructurePage, http.StructurePageResponse),
]


@pytest.mark.parametrize(("key", "record_type", "dto"), RECORDS)
def test_round_trip(key: str, record_type: type[Contract], dto: type[http.DTO]) -> None:
    data = fixture()[key]
    record = record_type.from_dict(data)
    assert record_type.from_json(record.to_json()) == record
    assert dto.model_validate(data).to_core() == record
    assert dto.from_core(record).model_dump(mode="json") == data


def test_structure_mapping_and_immutable_identity() -> None:
    data = fixture()
    reference = bio.ReferenceSnapshot.from_dict(data["reference"])
    response = http.StructureResponse.model_validate(data["structure"])
    mapping = bio.ResidueMap.from_dict(data["structure"]["mapping"])
    descriptor = bio.StructureDescriptor.from_dict(data["structure"]["descriptor"])
    assert response.mapping.to_core() == mapping
    assert response.descriptor.to_core() == descriptor
    assert mapping.identity.reference.record_id == reference.reference_id
    assert mapping.identity.reference.content_hash == reference.protein.sequence_hash
    assert isinstance(descriptor.mapping, ContentReference)
    assert descriptor.mapping.content_hash == mapping.content_hash
    assert mapping.content_hash.sha256 == hashlib.sha256(mapping.to_json()).hexdigest()
    assert reference.content_hash.encoding is HashEncoding.CANONICAL_JSON
    assert descriptor.evidence is EvidenceKind.SYNTHETIC
    assert {row.status.value for row in mapping.rows} == {
        "exact",
        "mismatch",
        "unobserved",
        "unmapped",
        "ambiguous",
    }
    assert mapping.rows[0].auth_seq_id.value == "-2"
    assert mapping.rows[1].insertion_code.value == "A"
    assert mapping.rows[2].reference_position.value == 3
    assert not mapping.rows[2].coordinate_present
    assert mapping.rows[3].reference_position.value == 4  # reference gap
    assert mapping.rows[4].reference_position.value is None  # construct tag
    assert mapping.rows[5].candidate_reference_positions == (5, 6)
    assert mapping.identity.selection.label_asym_id == "A"
    assert mapping.identity.selection.auth_asym_id.value == "X"
    with pytest.raises(FrozenInstanceError):
        mapping.mapping_id = "changed"  # type: ignore[misc]
    data["reference"]["protein"]["sequence"] = "XXXXXX"
    exported = reference.to_dict()
    exported["protein"] = {}
    assert reference.protein.sequence == "ACDEFG"
    # A different model/assembly/operator is a different identity, even with the
    # same reference and raw artifact bytes. No coordinate transformation occurs.
    selection = replace(mapping.identity.selection, model_id="3")
    assert replace(mapping.identity, selection=selection) != mapping.identity
    assert bio.ResidueMap.from_json(mapping.to_json()) == mapping
    assert bio.StructureDescriptor.from_json(descriptor.to_json()) == descriptor


def test_provider_examples_are_synthetic_and_receipts_hash_actual_bytes() -> None:
    data = fixture()
    protein = data["reference"]["protein"]
    upstream = json.loads((FIXTURES / "uniprot-synthetic-v1.json").read_bytes())
    assert upstream["sequence"]["value"] == protein["sequence"] == "ACDEFG"
    assert hashlib.sha256(b"ACDEFG").hexdigest() == protein["sequence_hash"]["sha256"]
    assert (
        upstream["entryAudit"]["entryVersion"]
        == protein["source_receipt"]["entry_version"]["value"]
    )
    rcsb = json.loads((FIXTURES / "rcsb-synthetic-v1.json").read_bytes())
    summary = data["structure"]["descriptor"]["source"]
    assert (
        rcsb["entry"]["rcsb_entry_info"]["structure_determination_methodology"]
        == summary["origin"]
    )
    assert (
        rcsb["polymer_entity"]["entity_poly"]["pdbx_seq_one_letter_code_can"]
        == summary["polymer_sequence"]["value"]
    )
    for receipt, name in (
        (protein["source_receipt"], "uniprot"),
        (summary["source_receipt"], "rcsb"),
    ):
        raw = (FIXTURES / f"{name}-synthetic-v1.json").read_bytes()
        assert receipt["raw_artifact"]["byte_size"] == len(raw)
        assert (
            receipt["raw_artifact"]["content_hash"]["sha256"]
            == hashlib.sha256(raw).hexdigest()
        )
        assert receipt["raw_artifact"]["evidence"] == "synthetic"
        assert receipt["release"]["state"] == "unavailable"
        assert receipt["raw_artifact"]["rights"]["license"]["value"] == "Apache-2.0"


# All expected failures are independently specified mutations of the frozen
# wire fixture. Dotted paths select array positions without altering originals.
def set_path(data: dict[str, Any], path: str, value: object) -> None:
    target: Any = data
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    last = parts[-1]
    target[int(last) if isinstance(target, list) else last] = value


PRESENT = {"state": "present", "value": "A", "reason": None}
ABSENT = {"state": "unavailable", "value": None, "reason": "Synthetic absence."}
REFERENCE_BAD: list[tuple[str, object]] = [
    ("schema_version", "neurofold-biological/2"),
    ("reference_id", " "),
    ("captured_at", "2026-11-10"),
    ("protein.sequence", "ACDEFA"),
    ("protein.sequence", "acdefg"),
    ("protein.sequence_hash.encoding", "raw-bytes/1"),
    ("protein.summary.sequence_length", 5),
    ("protein.summary.sequence_length", 0),
    ("protein.summary.accession", "BAD"),
    ("protein.summary.canonical", False),
    ("protein.summary.isoform", PRESENT),
    ("protein.summary.organism_name", {"state": "present", "value": 2, "reason": None}),
    ("protein.summary.taxon_id.value", 0),
    ("protein.summary.taxon_id.value", True),
    ("protein.summary.reviewed.value", "true"),
    ("protein.summary.source_receipt_id", "different-receipt"),
    ("protein.source_receipt.accession.value", "P00002"),
    ("protein.source_receipt.taxon_id.value", 2),
    ("protein.source_receipt.isoform", ABSENT),
    ("protein.normalization", ""),
]


@pytest.mark.parametrize(("path", "value"), REFERENCE_BAD)
def test_invalid_reference(path: str, value: object) -> None:
    data = fixture()["reference"]
    set_path(data, path, value)
    with pytest.raises(ValueError):
        bio.ReferenceSnapshot.from_dict(data)
    with pytest.raises(ValueError):
        http.ReferenceResponse.model_validate(data)


MAPPING_BAD: list[tuple[str, object]] = [
    ("reference_length", 0),
    ("reference_length", 2),
    ("identity.reference.content_hash.encoding", "raw-bytes/1"),
    ("identity.structure.content_hash.encoding", "sequence-ascii/1"),
    ("identity.selection.entity_id", ""),
    ("identity.selection.auth_asym_id.value", 1),
    ("identity.selection.operator_id", ABSENT),
    ("rows.0.identity.selection.model_id", "3"),
    ("rows.0.reference_position.value", 0),
    ("rows.0.reference_position.value", True),
    ("rows.0.reference_position", ABSENT),
    ("rows.0.reference_residue.value", "ALA"),
    ("rows.0.reference_residue.value", "a"),
    ("rows.0.observed_residue.value", "Δ"),
    ("rows.0.observed_residue.value", "S"),
    ("rows.0.coordinate_present", False),
    ("rows.0.reason", "unexpected"),
    ("rows.0.candidate_reference_positions", [1]),
    ("rows.1.reason", None),
    ("rows.1.reason", " "),
    ("rows.1.observed_residue.value", "C"),
    ("rows.1.reference_position.value", 1),
    ("rows.1.label_seq_id.value", 1),
    ("rows.2.coordinate_present", True),
    ("rows.3.reference_residue", ABSENT),
    ("rows.3.label_seq_id", {"state": "present", "value": 6, "reason": None}),
    ("rows.4.candidate_reference_positions", [1]),
    ("rows.4.label_seq_id", ABSENT),
    ("rows.5.reference_position", {"state": "present", "value": 5, "reason": None}),
    ("rows.5.reference_residue", PRESENT),
    ("rows.5.candidate_reference_positions", [6, 5]),
    ("rows.5.candidate_reference_positions", [5, 5]),
    ("rows.5.candidate_reference_positions", [0]),
    ("rows.5.candidate_reference_positions", [7]),
    ("rows.5.label_seq_id", ABSENT),
    ("rows.0.auth_seq_id.value", -2),
]


@pytest.mark.parametrize(("path", "value"), MAPPING_BAD)
def test_invalid_mapping(path: str, value: object) -> None:
    data = fixture()["structure"]["mapping"]
    set_path(data, path, value)
    with pytest.raises(ValueError):
        bio.ResidueMap.from_dict(data)
    with pytest.raises(ValueError):
        http.ResidueMapDTO.model_validate(data)


STRUCTURE_BAD: list[tuple[str, object]] = [
    ("format", "pdb"),
    ("evidence", "predicted"),
    ("raw_artifact.evidence", "experimental"),
    ("source.source_receipt.raw_artifact.evidence", "experimental"),
    ("mapping.content_hash.encoding", "raw-bytes/1"),
    ("selection.label_asym_id", "Z"),
    ("source.experimental_methods", []),
    ("source.experimental_methods", ["SOLUTION NMR", "SOLUTION NMR"]),
    ("source.experimental_methods", [" "]),
    ("source.resolutions", []),
    ("source.resolutions.0.method", "X-RAY DIFFRACTION"),
    ("source.origin", "computed"),
    ("source.polymer_sequence.value", "asd hg"),
    ("source.mapped_coverage.mapped_positions", 7),
    ("source.mapped_coverage.reference_length", 0),
    ("source.mapped_coverage", PRESENT),
    ("source.source_receipt.raw_artifact.evidence", "predicted"),
]


@pytest.mark.parametrize(("path", "value"), STRUCTURE_BAD)
def test_invalid_structure(path: str, value: object) -> None:
    data = fixture()["structure"]["descriptor"]
    set_path(data, path, value)
    with pytest.raises(ValueError):
        bio.StructureDescriptor.from_dict(data)
    with pytest.raises(ValueError):
        http.StructureDescriptorDTO.model_validate(data)


@pytest.mark.parametrize("value", ["0", "-1", "1.0", "1e2", "NaN", 2])
def test_invalid_resolution(value: object) -> None:
    with pytest.raises(ValueError):
        bio.Resolution.from_dict(
            {
                "method": "X-RAY DIFFRACTION",
                "unit": "angstrom",
                "value": {"state": "present", "value": value, "reason": None},
            }
        )


def test_absence_variants_and_isoforms_remain_explicit() -> None:
    data = fixture()["reference"]
    protein = data["protein"]
    protein["summary"]["accession"] = "P00001-2"
    protein["summary"]["canonical"] = False
    isoform = {"state": "present", "value": "P00001-2", "reason": None}
    protein["summary"]["isoform"] = isoform
    protein["source_receipt"]["isoform"] = isoform
    protein["source_receipt"]["accession"]["value"] = "P00001-2"
    assert not bio.ProteinRecord.from_dict(protein).summary.canonical
    with pytest.raises(ValueError, match="Isoform references"):
        bio.ReferenceSnapshot.from_dict(data)
    protein["summary"]["isoform"]["value"] = "P00001-3"
    with pytest.raises(ValueError, match="Isoform identifier"):
        bio.ProteinRecord.from_dict(protein)
    data = fixture()["reference"]
    data["protein"]["summary"]["taxon_id"] = ABSENT
    data["protein"]["source_receipt"]["taxon_id"] = ABSENT
    with pytest.raises(ValueError, match="known taxon"):
        bio.ReferenceSnapshot.from_dict(data)
    descriptor = fixture()["structure"]["descriptor"]
    descriptor["source"]["mapped_coverage"] = ABSENT
    assert bio.StructureDescriptor.from_dict(descriptor).source.mapped_coverage
    selection = descriptor["selection"]
    na = {
        "state": "not_applicable",
        "value": None,
        "reason": "Asymmetric unit selected.",
    }
    selection["assembly_id"] = na
    selection["operator_id"] = na
    bio.StructureSelection.from_dict(selection)
    selection["operator_id"] = PRESENT
    with pytest.raises(ValueError, match="Asymmetric unit"):
        bio.StructureSelection.from_dict(selection)
    assert (
        bio.Resolution.from_dict(
            {
                "method": "X-RAY DIFFRACTION",
                "unit": "angstrom",
                "value": {"state": "present", "value": "2.5", "reason": None},
            }
        ).value.value
        == "2.5"
    )


@pytest.mark.parametrize("key", ["protein_page", "structure_page"])
def test_page_absence_bounds_and_warnings(key: str) -> None:
    cls = bio.ProteinPage if key == "protein_page" else bio.StructurePage
    page = fixture()[key]
    page["items"] = []
    page["availability"] = "complete"
    page["warnings"] = []
    assert cls.from_dict(page).availability is bio.Availability.COMPLETE
    page["availability"] = "unavailable"
    with pytest.raises(ValueError, match="explain"):
        cls.from_dict(page)
    page["warnings"] = ["Synthetic provider unavailable."]
    assert cls.from_dict(page).availability is bio.Availability.UNAVAILABLE
    page["items"] = fixture()[key]["items"]
    with pytest.raises(ValueError, match="Unavailable pages"):
        cls.from_dict(page)
    page["availability"] = "partial"
    assert cls.from_dict(page).availability is bio.Availability.PARTIAL
    page["items"] *= 101
    with pytest.raises(ValueError, match="maximum size"):
        cls.from_dict(page)
    page = fixture()[key]
    page["source_receipts"] *= 2
    with pytest.raises(ValueError, match="Duplicate page"):
        cls.from_dict(page)


@pytest.mark.parametrize(("key", "record_type", "dto"), RECORDS)
def test_strict_required_fields(
    key: str, record_type: type[Contract], dto: type[http.DTO]
) -> None:
    data = fixture()[key]
    del data["schema_version"]
    with pytest.raises(ValueError):
        record_type.from_dict(data)
    with pytest.raises(ValueError):
        dto.model_validate(data)
    data = fixture()[key]
    data["unknown"] = None
    with pytest.raises(ValueError):
        record_type.from_dict(data)
    with pytest.raises(ValueError):
        dto.model_validate(data)


def test_structure_response_checks_cross_record_integrity() -> None:
    data = fixture()["structure"]
    data["descriptor"]["mapping"]["content_hash"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="identities disagree"):
        http.StructureResponse.model_validate(data)
    data = fixture()["structure"]
    data["artifact_url"] = "https://example.invalid/raw"
    with pytest.raises(ValueError, match="registered artifact"):
        http.StructureResponse.model_validate(data)


def test_hash_domains_remain_distinct() -> None:
    sequence = ContentHash(
        sha256=hashlib.sha256(b"ACDEFG").hexdigest(), encoding=HashEncoding.SEQUENCE
    )
    assert replace(sequence, encoding=HashEncoding.RAW) != sequence


def test_missing_mapping_is_an_explicit_state_not_a_fabricated_map() -> None:
    data = fixture()["structure"]
    data["descriptor"]["mapping"] = ABSENT
    data["mapping"] = ABSENT
    response = http.StructureResponse.model_validate(data)
    assert response.mapping.to_core() == Metadata.from_dict(ABSENT)
    data["mapping"] = {**ABSENT, "reason": "Different absence."}
    with pytest.raises(ValueError, match="explicit state/reason"):
        http.StructureResponse.model_validate(data)
    data = fixture()["structure"]
    data["mapping"] = ABSENT
    with pytest.raises(ValueError, match="must be included"):
        http.StructureResponse.model_validate(data)
    data["descriptor"]["mapping"] = PRESENT
    with pytest.raises(ValueError, match="content reference"):
        bio.StructureDescriptor.from_dict(data["descriptor"])


@pytest.mark.parametrize("key", ["protein_page", "structure_page"])
def test_page_retains_item_receipts(key: str) -> None:
    cls = bio.ProteinPage if key == "protein_page" else bio.StructurePage
    data = fixture()[key]
    data["source_receipts"] = []
    with pytest.raises(ValueError, match="receipt is missing"):
        cls.from_dict(data)

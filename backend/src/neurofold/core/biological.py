"""NF-02 M1 immutable biological contracts; no clients, storage or alignment."""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol

from neurofold.core._contracts import Contract
from neurofold.core.canonical import canonical_decimal, sequence_sha256, sha256_bytes
from neurofold.core.provenance import (
    ArtifactDescriptor,
    ContentHash,
    ContentReference,
    EvidenceKind,
    HashEncoding,
    Metadata,
    MetadataState,
    ReferenceCollection,
    SourceReceipt,
    _text,
    _utc,
)

ACCESSION_PATTERN = (
    r"(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})"
)


def validate_accession(value: str, *, canonical: bool = False) -> None:
    pattern = ACCESSION_PATTERN + ("" if canonical else r"(?:-[1-9][0-9]*)?")
    if not re.fullmatch(pattern, value):
        raise ValueError("Unsupported UniProtKB accession or isoform")


def _positive(value: int) -> None:
    if value <= 0:
        raise ValueError("Expected a positive integer")


def _metadata(value: Metadata, kind: type[str] | type[int]) -> None:
    if value.state is MetadataState.PRESENT:
        if type(value.value) is not kind:
            raise ValueError("Invalid biological metadata type")
        if isinstance(value.value, str):
            _text(value.value)
        elif type(value.value) is int:
            _positive(value.value)


def _hash(value: ContentHash, encoding: HashEncoding) -> None:
    if value.encoding is not encoding:
        raise ValueError("Incorrect biological identity hash domain")


class Availability(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class MappingStatus(StrEnum):
    EXACT = "exact"
    MISMATCH = "mismatch"
    UNOBSERVED = "unobserved"
    UNMAPPED = "unmapped"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, kw_only=True)
class BiologicalRecord(Contract):
    schema_version: Literal["neurofold-biological/1"] = "neurofold-biological/1"

    @property
    def content_hash(self) -> ContentHash:
        return ContentHash(
            sha256=sha256_bytes(self.to_json()), encoding=HashEncoding.CANONICAL_JSON
        )


@dataclass(frozen=True, kw_only=True)
class ProteinSummary(BiologicalRecord):
    accession: str
    canonical: bool
    isoform: Metadata
    gene_names: ReferenceCollection
    organism_name: Metadata
    taxon_id: Metadata
    reviewed: Metadata
    sequence_length: int
    source_receipt_id: str

    def _validate(self) -> None:
        validate_accession(self.accession, canonical=self.canonical)
        if self.canonical != ("-" not in self.accession):
            raise ValueError("Canonical/isoform identity disagrees with accession")
        if self.canonical:
            if self.isoform.state is not MetadataState.NOT_APPLICABLE:
                raise ValueError("Canonical sequence must mark isoform not applicable")
        elif self.isoform.value != self.accession:
            raise ValueError("Isoform identifier must be retained exactly")
        _metadata(self.organism_name, str)
        _metadata(self.taxon_id, int)
        if self.reviewed.state is MetadataState.PRESENT:
            if type(self.reviewed.value) is not bool:
                raise ValueError("Reviewed flag must be boolean")
        _positive(self.sequence_length)
        _text(self.source_receipt_id)


@dataclass(frozen=True, kw_only=True)
class ProteinRecord(BiologicalRecord):
    summary: ProteinSummary
    sequence: str
    sequence_hash: ContentHash
    source_receipt: SourceReceipt
    normalization: str

    def _validate(self) -> None:
        _hash(self.sequence_hash, HashEncoding.SEQUENCE)
        if sequence_sha256(self.sequence) != self.sequence_hash.sha256:
            raise ValueError("Sequence checksum mismatch")
        if len(self.sequence) != self.summary.sequence_length:
            raise ValueError("Sequence length mismatch")
        if self.summary.source_receipt_id != self.source_receipt.receipt_id:
            raise ValueError("Source receipt identity mismatch")
        for actual, expected in (
            (self.source_receipt.accession, self.summary.accession),
            (self.source_receipt.taxon_id, self.summary.taxon_id.value),
        ):
            if actual.state is MetadataState.PRESENT and actual.value != expected:
                raise ValueError("Source receipt biological identity mismatch")
        if self.source_receipt.isoform != self.summary.isoform:
            raise ValueError("Source receipt isoform mismatch")
        _text(self.normalization)


@dataclass(frozen=True, kw_only=True)
class ReferenceSnapshot(BiologicalRecord):
    reference_id: str
    protein: ProteinRecord
    captured_at: str

    def _validate(self) -> None:
        _text(self.reference_id)
        _utc(self.captured_at)
        if not self.protein.summary.canonical:
            raise ValueError(
                "Isoform references are unsupported; select canonical explicitly"
            )
        if self.protein.summary.taxon_id.state is not MetadataState.PRESENT:
            raise ValueError("Pinning requires a known taxon")


@dataclass(frozen=True, kw_only=True)
class StructureSelection(Contract):
    entity_id: str
    label_asym_id: str
    auth_asym_id: Metadata
    model_id: str
    assembly_id: Metadata
    operator_id: Metadata

    def _validate(self) -> None:
        for value in (self.entity_id, self.label_asym_id, self.model_id):
            _text(value)
        for metadata in (self.auth_asym_id, self.assembly_id, self.operator_id):
            _metadata(metadata, str)
        if self.assembly_id.state is MetadataState.NOT_APPLICABLE:
            if self.operator_id.state is not MetadataState.NOT_APPLICABLE:
                raise ValueError("Asymmetric unit has no assembly operator")
        elif self.assembly_id.state is MetadataState.PRESENT:
            if self.operator_id.state is not MetadataState.PRESENT:
                raise ValueError("Assembly selection requires an operator")


@dataclass(frozen=True, kw_only=True)
class Resolution(Contract):
    value: Metadata
    method: str
    unit: Literal["angstrom"] = "angstrom"

    def _validate(self) -> None:
        _text(self.method)
        _metadata(self.value, str)
        if self.value.state is MetadataState.PRESENT:
            assert isinstance(self.value.value, str)
            canonical_decimal(self.value.value)
            if self.value.value.startswith("-") or self.value.value == "0":
                raise ValueError("Resolution must be positive")


@dataclass(frozen=True, kw_only=True)
class MappingCoverage(Contract):
    """Reference-position coverage, never atom or coordinate coverage."""

    mapped_positions: int
    reference_length: int
    definition: Literal["unique-reference-positions/1"] = "unique-reference-positions/1"

    def _validate(self) -> None:
        _positive(self.reference_length)
        if not 0 <= self.mapped_positions <= self.reference_length:
            raise ValueError("Coverage exceeds its reference denominator")


@dataclass(frozen=True, kw_only=True)
class ExperimentalStructureSummary(BiologicalRecord):
    entry_id: str
    entity_id: str
    label_asym_id: str
    auth_asym_id: Metadata
    experimental_methods: tuple[str, ...]
    resolutions: tuple[Resolution, ...]
    source_revision: Metadata
    revision_date: Metadata
    assembly_ids: ReferenceCollection
    polymer_sequence: Metadata
    mapped_coverage: MappingCoverage | Metadata
    citations: ReferenceCollection
    source_receipt: SourceReceipt
    origin: Literal["experimental"] = "experimental"

    def _validate(self) -> None:
        for value in (self.entry_id, self.entity_id, self.label_asym_id):
            _text(value)
        if not self.experimental_methods or len(set(self.experimental_methods)) != len(
            self.experimental_methods
        ):
            raise ValueError("Experimental origin requires distinct reported methods")
        for value in self.experimental_methods:
            _text(value)
        if (
            len(self.resolutions) != len(self.experimental_methods)
            or tuple(value.method for value in self.resolutions)
            != self.experimental_methods
        ):
            raise ValueError(
                "Resolution or explicit absence is required for each method"
            )
        for metadata in (
            self.auth_asym_id,
            self.source_revision,
            self.revision_date,
            self.polymer_sequence,
        ):
            _metadata(metadata, str)
        if self.polymer_sequence.state is MetadataState.PRESENT:
            assert isinstance(self.polymer_sequence.value, str)
            sequence_sha256(self.polymer_sequence.value)
        if isinstance(self.mapped_coverage, Metadata):
            if self.mapped_coverage.state is MetadataState.PRESENT:
                raise ValueError(
                    "Present coverage requires a typed numerator/denominator"
                )
        if self.source_receipt.raw_artifact.evidence is EvidenceKind.PREDICTED:
            raise ValueError("Computed models cannot enter experimental discovery")


@dataclass(frozen=True, kw_only=True)
class MappingIdentity(Contract):
    reference: ContentReference
    structure: ContentReference
    selection: StructureSelection

    def _validate(self) -> None:
        _hash(self.reference.content_hash, HashEncoding.SEQUENCE)
        _hash(self.structure.content_hash, HashEncoding.RAW)


@dataclass(frozen=True, kw_only=True)
class ResidueMapRow(Contract):
    identity: MappingIdentity
    reference_position: Metadata
    reference_residue: Metadata
    label_seq_id: Metadata
    auth_seq_id: Metadata
    insertion_code: Metadata
    observed_residue: Metadata
    coordinate_present: bool
    status: MappingStatus
    reason: str | None
    candidate_reference_positions: tuple[int, ...]

    def _validate(self) -> None:
        for value in (self.reference_position, self.label_seq_id):
            _metadata(value, int)
        for value in (
            self.reference_residue,
            self.auth_seq_id,
            self.insertion_code,
            self.observed_residue,
        ):
            _metadata(value, str)
        for value in (self.reference_residue, self.observed_residue):
            if value.state is MetadataState.PRESENT:
                if len(str(value.value)) != 1:
                    raise ValueError("Residues use one-letter sequence symbols")
                sequence_sha256(str(value.value))
        candidates = self.candidate_reference_positions
        if candidates != tuple(sorted(set(candidates))):
            raise ValueError("Ambiguous positions must be unique and sorted")
        for position in candidates:
            _positive(position)
        resolved = self.status in (
            MappingStatus.EXACT,
            MappingStatus.MISMATCH,
            MappingStatus.UNOBSERVED,
        )
        if resolved:
            if any(
                value.state is not MetadataState.PRESENT
                for value in (
                    self.reference_position,
                    self.reference_residue,
                    self.label_seq_id,
                    self.observed_residue,
                )
            ):
                raise ValueError(
                    "Resolved rows require reference and polymer identities"
                )
            if candidates:
                raise ValueError("Resolved rows cannot carry ambiguous candidates")
            same = self.reference_residue.value == self.observed_residue.value
            if (self.status is MappingStatus.MISMATCH) == same:
                raise ValueError("Mapping status disagrees with sequence residues")
        elif self.status is MappingStatus.AMBIGUOUS:
            if self.reference_position.state is MetadataState.PRESENT:
                raise ValueError("Unresolved rows cannot assert a reference position")
            if self.reference_residue.state is MetadataState.PRESENT:
                raise ValueError("Unresolved rows cannot assert a reference residue")
        else:
            if candidates:
                raise ValueError("Unmapped rows have no candidate reference positions")
            has_reference = self.reference_position.state is MetadataState.PRESENT
            if has_reference != (self.reference_residue.state is MetadataState.PRESENT):
                raise ValueError(
                    "Reference gap identity requires both position and residue"
                )
            if has_reference and self.label_seq_id.state is MetadataState.PRESENT:
                raise ValueError(
                    "An unmapped gap cannot assert a reference/polymer pair"
                )
            if (
                not has_reference
                and self.label_seq_id.state is not MetadataState.PRESENT
            ):
                raise ValueError("Unmapped rows must retain one side of the gap")
        if self.status is MappingStatus.EXACT:
            if not self.coordinate_present or self.reason is not None:
                raise ValueError("Exact rows require coordinates and no reason")
        else:
            if self.reason is None:
                raise ValueError("Non-exact mapping requires an explicit reason")
            _text(self.reason)
        if self.status is MappingStatus.UNOBSERVED and self.coordinate_present:
            raise ValueError("Unobserved residues cannot have coordinates")
        if self.coordinate_present and any(
            value.state is not MetadataState.PRESENT
            for value in (self.label_seq_id, self.observed_residue)
        ):
            raise ValueError("Coordinates require a polymer residue identity")


@dataclass(frozen=True, kw_only=True)
class ResidueMap(BiologicalRecord):
    mapping_id: str
    identity: MappingIdentity
    reference_length: int
    method: str
    method_version: str
    rows: tuple[ResidueMapRow, ...]

    def _validate(self) -> None:
        for value in (self.mapping_id, self.method, self.method_version):
            _text(value)
        _positive(self.reference_length)
        positions: set[int] = set()
        polymer_positions: set[int] = set()
        for row in self.rows:
            if row.identity != self.identity:
                raise ValueError("Row belongs to a different mapping identity")
            if row.reference_position.state is MetadataState.PRESENT:
                position = row.reference_position.value
                assert type(position) is int
                if position > self.reference_length or position in positions:
                    raise ValueError("Duplicate or out-of-bounds reference position")
                positions.add(position)
            if any(
                position > self.reference_length
                for position in row.candidate_reference_positions
            ):
                raise ValueError("Candidate position exceeds reference length")
            if row.label_seq_id.state is MetadataState.PRESENT:
                label = row.label_seq_id.value
                assert type(label) is int
                if label in polymer_positions:
                    raise ValueError("Duplicate polymer position in selected instance")
                polymer_positions.add(label)


@dataclass(frozen=True, kw_only=True)
class StructureDescriptor(BiologicalRecord):
    structure_id: str
    raw_artifact: ArtifactDescriptor
    evidence: EvidenceKind
    selection: StructureSelection
    source: ExperimentalStructureSummary
    mapping: ContentReference | Metadata
    format: Literal["mmcif"] = "mmcif"

    def _validate(self) -> None:
        _text(self.structure_id)
        if self.evidence is EvidenceKind.PREDICTED:
            raise ValueError(
                "NF-02 describes experimental or synthetic structures only"
            )
        if self.raw_artifact.evidence is not self.evidence or (
            self.source.source_receipt.raw_artifact.evidence is not self.evidence
        ):
            raise ValueError("Structure evidence disagrees with raw/source evidence")
        if isinstance(self.mapping, ContentReference):
            _hash(self.mapping.content_hash, HashEncoding.CANONICAL_JSON)
        elif self.mapping.state is MetadataState.PRESENT:
            raise ValueError("Present mapping requires a content reference")
        if (
            self.selection.entity_id,
            self.selection.label_asym_id,
            self.selection.auth_asym_id,
        ) != (
            self.source.entity_id,
            self.source.label_asym_id,
            self.source.auth_asym_id,
        ):
            raise ValueError("Selected instance disagrees with source metadata")


@dataclass(frozen=True, kw_only=True)
class CatalogPage(BiologicalRecord):
    """Empty complete results differ from unavailable or partial discovery."""

    next_cursor: Metadata
    availability: Availability
    warnings: tuple[str, ...]
    source_receipts: tuple[SourceReceipt, ...]

    def _validate(self) -> None:
        _metadata(self.next_cursor, str)
        if self.availability is not Availability.COMPLETE and not self.warnings:
            raise ValueError("Incomplete discovery must explain its limitations")
        for warning in self.warnings:
            _text(warning)
        ids = [receipt.receipt_id for receipt in self.source_receipts]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate page source receipt")


@dataclass(frozen=True, kw_only=True)
class ProteinPage(CatalogPage):
    items: tuple[ProteinSummary, ...]

    def _validate(self) -> None:
        super()._validate()
        if self.availability is Availability.UNAVAILABLE and self.items:
            raise ValueError("Unavailable pages cannot assert results")
        if len(self.items) > 100:
            raise ValueError("Page exceeds maximum size")
        receipt_ids = {receipt.receipt_id for receipt in self.source_receipts}
        if any(item.source_receipt_id not in receipt_ids for item in self.items):
            raise ValueError("Protein item receipt is missing from the page")


@dataclass(frozen=True, kw_only=True)
class StructurePage(CatalogPage):
    items: tuple[ExperimentalStructureSummary, ...]

    def _validate(self) -> None:
        super()._validate()
        if self.availability is Availability.UNAVAILABLE and self.items:
            raise ValueError("Unavailable pages cannot assert results")
        if len(self.items) > 100:
            raise ValueError("Page exceeds maximum size")
        if any(item.source_receipt not in self.source_receipts for item in self.items):
            raise ValueError("Structure item receipt is missing from the page")


class ProteinCatalog(Protocol):
    """Future provider seam. No implicit canonical substitution or live calls in M1.

    KeyError means absent; ValueError means invalid input. Provider transport
    failures must remain failures, never complete empty pages.
    """

    def search(
        self, *, gene: str, taxon_id: int | None, cursor: str | None, limit: int
    ) -> ProteinPage: ...

    def get(self, accession: str) -> ProteinRecord: ...


class ExperimentalStructureCatalog(Protocol):
    def discover(
        self, reference: ReferenceSnapshot, *, cursor: str | None, limit: int
    ) -> StructurePage: ...


class ReferenceRepository(Protocol):
    """Append-only publication: KeyError for absent, ValueError for conflicting ID."""

    def get(self, reference_id: str) -> ReferenceSnapshot: ...

    def publish(self, snapshot: ReferenceSnapshot) -> None: ...


class StructureRepository(Protocol):
    """Publish descriptor/map atomically, validating cross-record IDs and hashes.

    KeyError for absent; ValueError for conflicts/integrity failures. No storage
    implementation exists in M1. ArtifactStore is reused from core.provenance.
    """

    def get(self, structure_id: str) -> StructureDescriptor: ...

    def get_mapping(self, mapping_id: str) -> ResidueMap: ...

    def publish(
        self, descriptor: StructureDescriptor, mapping: ResidueMap | Metadata
    ) -> None: ...

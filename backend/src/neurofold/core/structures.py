"""Additive M3 import seams and audit; frozen biological v1 stays unchanged."""

from dataclasses import dataclass
from typing import Literal, Protocol

from neurofold.core._contracts import Contract
from neurofold.core.biological import (
    ExperimentalStructureSummary,
    MappingCoverage,
    MappingStatus,
    ReferenceSnapshot,
    ResidueMap,
    StructureDescriptor,
    StructureSelection,
)
from neurofold.core.canonical import CanonicalObject
from neurofold.core.provenance import (
    ContentReference,
    Metadata,
    MetadataState,
    SourceReceipt,
    _text,
    _utc,
)


class UnsupportedStructure(ValueError):
    """Unsupported selection, chemistry, ambiguity capacity or resource profile."""


class RevisionUnavailable(ValueError):
    """No authoritative version: fail closed rather than publishing a snapshot."""


class StructureSourceChanged(ValueError):
    """Typed source revision conflict for later HTTP 409 translation."""

    def __init__(self, expected: str, actual: str) -> None:
        self.expected, self.actual = expected, actual
        super().__init__("Structure revision changed; inspect and select again.")


@dataclass(frozen=True, kw_only=True)
class StructureCheck(Contract):
    source_receipt_id: str
    checked_at: str
    response_status: Literal[200, 304]
    response_headers: CanonicalObject
    adapter_version: str

    def _validate(self) -> None:
        _text(self.source_receipt_id)
        _text(self.adapter_version)
        _utc(self.checked_at)


@dataclass(frozen=True)
class StructureSource:
    summary: ExperimentalStructureSummary
    checks: tuple[StructureCheck, ...]


@dataclass(frozen=True)
class StructureDownload:
    receipt: SourceReceipt
    decoded: bytes
    check: StructureCheck


@dataclass(frozen=True)
class PolymerResidue:
    label_seq_id: int
    residue: str
    auth_seq_id: Metadata
    insertion_code: Metadata
    coordinate_present: bool
    uncertain: bool = False


@dataclass(frozen=True)
class ParsedStructure:
    sequence: str
    residues: tuple[PolymerResidue, ...]
    details: CanonicalObject


class StructureProvider(Protocol):
    def inspect(
        self,
        reference: ReferenceSnapshot,
        entry_id: str,
        label_asym_id: str,
        *,
        fresh: bool,
    ) -> StructureSource: ...

    def download(self, entry_id: str, revision: str) -> StructureDownload: ...

    def revalidate(self, entry_id: str, revision: str) -> StructureCheck: ...


class StructureParser(Protocol):
    def parse(
        self,
        data: bytes,
        source: ExperimentalStructureSummary,
        selection: StructureSelection,
    ) -> ParsedStructure: ...


class StructureMapper(Protocol):
    def map(
        self,
        reference: ReferenceSnapshot,
        structure_id: str,
        download: StructureDownload,
        selection: StructureSelection,
        parsed: ParsedStructure,
    ) -> tuple[ResidueMap, CanonicalObject]: ...


@dataclass(frozen=True, kw_only=True)
class StructureImport(Contract):
    """One atomic publication unit; no change to the v1 descriptor/map wire form."""

    descriptor: StructureDescriptor
    mapping: ResidueMap
    reference: ContentReference
    checks: tuple[StructureCheck, ...]
    parsing: CanonicalObject
    alignment: CanonicalObject
    schema_version: Literal["neurofold-structure-import/1"] = (
        "neurofold-structure-import/1"
    )

    def _validate(self) -> None:
        descriptor, mapping = self.descriptor, self.mapping
        if descriptor.mapping != ContentReference(
            record_id=mapping.mapping_id, content_hash=mapping.content_hash
        ):
            raise ValueError("Descriptor/map hash mismatch")
        identity = mapping.identity
        if (
            identity.structure.record_id != descriptor.structure_id
            or identity.structure.content_hash != descriptor.raw_artifact.content_hash
            or identity.selection != descriptor.selection
            or identity.reference.record_id != self.reference.record_id
            or mapping.mapping_id != descriptor.structure_id + ":map"
        ):
            raise ValueError("Structure mapping identity mismatch")
        if len(self.checks) < 5 or descriptor.source.source_receipt.receipt_id not in {
            check.source_receipt_id for check in self.checks
        }:
            raise ValueError("Missing source validation checks")

    def validate_reference(self, reference: ReferenceSnapshot) -> None:
        if (
            self.reference
            != ContentReference(
                record_id=reference.reference_id, content_hash=reference.content_hash
            )
            or self.mapping.identity.reference.content_hash
            != reference.protein.sequence_hash
        ):
            raise ValueError("Pinned reference identity mismatch")
        if self.mapping.reference_length != len(reference.protein.sequence):
            raise ValueError("Reference length mismatch")
        coverage = MappingCoverage(
            mapped_positions=sum(
                row.status
                in (
                    MappingStatus.EXACT,
                    MappingStatus.MISMATCH,
                    MappingStatus.UNOBSERVED,
                )
                for row in self.mapping.rows
            ),
            reference_length=self.mapping.reference_length,
        )
        if self.descriptor.source.mapped_coverage != coverage:
            raise ValueError("Imported mapping coverage mismatch")
        polymer = self.descriptor.source.polymer_sequence.value
        if not isinstance(polymer, str):
            raise ValueError("Import requires polymer sequence")
        reference_positions: set[int] = set()
        polymer_positions: set[int] = set()
        for row in self.mapping.rows:
            if row.reference_position.state is MetadataState.PRESENT:
                position = row.reference_position.value
                assert type(position) is int
                if (
                    row.reference_residue.value
                    != reference.protein.sequence[position - 1]
                ):
                    raise ValueError("Map disagrees with actual pinned reference")
                reference_positions.add(position)
            if row.label_seq_id.state is MetadataState.PRESENT:
                label = row.label_seq_id.value
                assert type(label) is int
                if (
                    label > len(polymer)
                    or row.observed_residue.value != polymer[label - 1]
                ):
                    raise ValueError("Map disagrees with selected polymer")
                polymer_positions.add(label)
        if reference_positions != set(range(1, len(reference.protein.sequence) + 1)):
            raise ValueError("Map omits reference positions")
        if polymer_positions != set(range(1, len(polymer) + 1)):
            raise ValueError("Map omits polymer positions")


class StructureImportRepository(Protocol):
    def publish_import(self, record: StructureImport) -> None: ...

    def get_import(self, structure_id: str) -> StructureImport: ...

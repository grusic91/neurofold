"""NF-02 M1 HTTP DTOs only. No operational /v1 routes are registered yet."""

from typing import Annotated, ClassVar, Literal, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    JsonValue,
    model_validator,
)

from neurofold.core import biological as bio
from neurofold.core import provenance as prov
from neurofold.core._contracts import Contract

Text = Annotated[str, Field(min_length=1, pattern=r"\S")]
OpaqueID = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
Accession = Annotated[
    str, Field(pattern="^" + bio.ACCESSION_PATTERN + r"(?:-[1-9][0-9]*)?$")
]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Positive = Annotated[int, Field(gt=0, le=9007199254740991)]


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    contract: ClassVar[type[Contract]]

    @model_validator(mode="after")
    def validate_contract(self) -> Self:
        self.to_core()
        return self

    def to_core(self) -> Contract:
        return self.contract.from_dict(self.model_dump(mode="json"))

    @classmethod
    def from_core(cls, record: Contract) -> Self:
        return cls.model_validate(record.to_dict())


class MetadataDTO(DTO):
    contract = prov.Metadata
    state: Literal["present", "unavailable", "not_applicable"]
    value: str | int | bool | dict[str, JsonValue] | None
    reason: str | None


class ReferencesDTO(DTO):
    contract = prov.ReferenceCollection
    state: Literal["present", "unavailable", "not_applicable"]
    values: list[str]
    reason: str | None


class HashDTO(DTO):
    contract = prov.ContentHash
    algorithm: Literal["sha256"]
    encoding: Literal["raw-bytes/1", "sequence-ascii/1", "neurofold-json/1"]
    sha256: Digest


class ContentReferenceDTO(DTO):
    contract = prov.ContentReference
    record_id: OpaqueID
    content_hash: HashDTO


class RightsDTO(DTO):
    contract = prov.ArtifactRights
    license: MetadataDTO
    attribution: MetadataDTO
    redistribution: Literal["allowed", "prohibited", "unknown"]
    basis: Text


class ArtifactDTO(DTO):
    contract = prov.ArtifactDescriptor
    schema_version: Literal["neurofold-research/1"]
    record_kind: Literal["artifact"]
    artifact_id: OpaqueID
    content_hash: HashDTO
    byte_size: Annotated[int, Field(ge=0)]
    media_type: Text
    evidence: Literal["experimental", "predicted", "synthetic"]
    rights: RightsDTO
    parents: list[HashDTO]
    transformation: MetadataDTO


class ReceiptDTO(DTO):
    contract = prov.SourceReceipt
    schema_version: Literal["neurofold-research/1"]
    record_kind: Literal["source_receipt"]
    receipt_id: Text
    provider: Text
    query: Text
    retrieved_at: Text
    raw_artifact: ArtifactDTO
    accession: MetadataDTO
    isoform: MetadataDTO
    taxon_id: MetadataDTO
    entry_version: MetadataDTO
    sequence_version: MetadataDTO
    release: MetadataDTO
    release_date: MetadataDTO
    etag: MetadataDTO
    last_modified: MetadataDTO
    license_references: ReferencesDTO
    citation_references: ReferencesDTO


class ProteinSummaryDTO(DTO):
    contract = bio.ProteinSummary
    schema_version: Literal["neurofold-biological/1"]
    accession: Accession
    canonical: bool
    isoform: MetadataDTO
    gene_names: ReferencesDTO
    organism_name: MetadataDTO
    taxon_id: MetadataDTO
    reviewed: MetadataDTO
    sequence_length: Positive
    source_receipt_id: Text


class ProteinResponse(DTO):
    contract = bio.ProteinRecord
    schema_version: Literal["neurofold-biological/1"]
    summary: ProteinSummaryDTO
    sequence: Text
    sequence_hash: HashDTO
    source_receipt: ReceiptDTO
    normalization: Text


class ReferenceResponse(DTO):
    contract = bio.ReferenceSnapshot
    schema_version: Literal["neurofold-biological/1"]
    reference_id: Text
    protein: ProteinResponse
    captured_at: Text


class SelectionDTO(DTO):
    contract = bio.StructureSelection
    entity_id: Text
    label_asym_id: Text
    auth_asym_id: MetadataDTO
    model_id: Text
    assembly_id: MetadataDTO
    operator_id: MetadataDTO


class ResolutionDTO(DTO):
    contract = bio.Resolution
    value: MetadataDTO
    method: Text
    unit: Literal["angstrom"]


class CoverageDTO(DTO):
    contract = bio.MappingCoverage
    mapped_positions: Annotated[int, Field(ge=0)]
    reference_length: Positive
    definition: Literal["unique-reference-positions/1"]


class StructureSummaryDTO(DTO):
    contract = bio.ExperimentalStructureSummary
    schema_version: Literal["neurofold-biological/1"]
    entry_id: Text
    entity_id: Text
    label_asym_id: Text
    auth_asym_id: MetadataDTO
    experimental_methods: list[Text]
    resolutions: list[ResolutionDTO]
    source_revision: MetadataDTO
    revision_date: MetadataDTO
    assembly_ids: ReferencesDTO
    polymer_sequence: MetadataDTO
    mapped_coverage: CoverageDTO | MetadataDTO
    citations: ReferencesDTO
    source_receipt: ReceiptDTO
    origin: Literal["experimental"]


class MappingIdentityDTO(DTO):
    contract = bio.MappingIdentity
    reference: ContentReferenceDTO
    structure: ContentReferenceDTO
    selection: SelectionDTO


class MapRowDTO(DTO):
    contract = bio.ResidueMapRow
    identity: MappingIdentityDTO
    reference_position: MetadataDTO
    reference_residue: MetadataDTO
    label_seq_id: MetadataDTO
    auth_seq_id: MetadataDTO
    insertion_code: MetadataDTO
    observed_residue: MetadataDTO
    coordinate_present: bool
    status: Literal["exact", "mismatch", "unobserved", "unmapped", "ambiguous"]
    reason: str | None
    candidate_reference_positions: list[Positive]


class ResidueMapDTO(DTO):
    contract = bio.ResidueMap
    schema_version: Literal["neurofold-biological/1"]
    mapping_id: Text
    identity: MappingIdentityDTO
    reference_length: Positive
    method: Text
    method_version: Text
    rows: list[MapRowDTO]


class StructureDescriptorDTO(DTO):
    contract = bio.StructureDescriptor
    schema_version: Literal["neurofold-biological/1"]
    structure_id: Text
    raw_artifact: ArtifactDTO
    evidence: Literal["experimental", "synthetic"]
    selection: SelectionDTO
    source: StructureSummaryDTO
    mapping: ContentReferenceDTO | MetadataDTO
    format: Literal["mmcif"]


class StructureResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    descriptor: StructureDescriptorDTO
    mapping: ResidueMapDTO | MetadataDTO
    artifact_url: Text

    @model_validator(mode="after")
    def consistent_identity(self) -> Self:
        descriptor = self.descriptor.to_core()
        mapping = self.mapping.to_core()
        assert isinstance(descriptor, bio.StructureDescriptor)
        if isinstance(descriptor.mapping, prov.Metadata):
            if mapping != descriptor.mapping:
                raise ValueError("Absent mapping must retain its explicit state/reason")
        else:
            self._validate_mapping(descriptor, mapping)
        if self.artifact_url != f"/v1/artifacts/{descriptor.raw_artifact.artifact_id}":
            raise ValueError("Artifact link must address the registered artifact")
        return self

    @staticmethod
    def _validate_mapping(
        descriptor: bio.StructureDescriptor, mapping: Contract
    ) -> None:
        if not isinstance(mapping, bio.ResidueMap):
            raise ValueError("A referenced mapping must be included in the response")
        if descriptor.mapping != prov.ContentReference(
            record_id=mapping.mapping_id, content_hash=mapping.content_hash
        ) or mapping.identity != bio.MappingIdentity(
            reference=mapping.identity.reference,
            structure=prov.ContentReference(
                record_id=descriptor.structure_id,
                content_hash=descriptor.raw_artifact.content_hash,
            ),
            selection=descriptor.selection,
        ):
            raise ValueError("Descriptor and residue mapping identities disagree")


class ProteinPageResponse(DTO):
    contract = bio.ProteinPage
    schema_version: Literal["neurofold-biological/1"]
    items: Annotated[list[ProteinSummaryDTO], Field(max_length=100)]
    next_cursor: MetadataDTO
    availability: Literal["complete", "partial", "unavailable"]
    warnings: list[Text]
    source_receipts: list[ReceiptDTO]


class StructurePageResponse(DTO):
    contract = bio.StructurePage
    schema_version: Literal["neurofold-biological/1"]
    items: Annotated[list[StructureSummaryDTO], Field(max_length=100)]
    next_cursor: MetadataDTO
    availability: Literal["complete", "partial", "unavailable"]
    warnings: list[Text]
    source_receipts: list[ReceiptDTO]


class RequestDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


def _query_integer(value: object) -> object:
    # HTTP query strings are textual. Accept decimal digits explicitly while
    # preserving strict JSON/body validation and rejecting implicit float/bool casts.
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        return int(value)
    return value


class PageQuery(RequestDTO):
    cursor: Annotated[str, Field(min_length=1, max_length=2048)] | None = None
    limit: Annotated[int, Field(ge=1, le=100), BeforeValidator(_query_integer)] = 20


class ProteinQuery(PageQuery):
    gene: Annotated[str, Field(min_length=1, max_length=128, pattern=r"^\S+$")]
    taxon_id: Annotated[Positive, BeforeValidator(_query_integer)] | None = None


class ReferenceRequest(RequestDTO):
    accession: Accession
    expected_sequence_sha256: Digest

    @model_validator(mode="after")
    def canonical_only(self) -> Self:
        bio.validate_accession(self.accession, canonical=True)
        return self


class StructureRequest(RequestDTO):
    reference_id: OpaqueID
    entry_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_]{4,32}$")]
    entity_id: Text
    label_asym_id: Text
    model_id: Text
    assembly_id: MetadataDTO
    operator_id: MetadataDTO
    expected_source_revision: MetadataDTO

    @model_validator(mode="after")
    def explicit_selection(self) -> Self:
        bio.StructureSelection(
            entity_id=self.entity_id,
            label_asym_id=self.label_asym_id,
            auth_asym_id=prov.Metadata(
                state=prov.MetadataState.UNAVAILABLE,
                value=None,
                reason="Author chain is resolved from selected source metadata.",
            ),
            model_id=self.model_id,
            assembly_id=prov.Metadata.from_dict(self.assembly_id.model_dump()),
            operator_id=prov.Metadata.from_dict(self.operator_id.model_dump()),
        )
        revision = prov.Metadata.from_dict(self.expected_source_revision.model_dump())
        if revision.state is prov.MetadataState.PRESENT:
            if type(revision.value) is not str or not revision.value.strip():
                raise ValueError("Source revision must be nonblank text")
        return self


class ErrorDetail(RequestDTO):
    code: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]*$")]
    message: Text
    retryable: bool
    details: dict[str, JsonValue]
    request_id: OpaqueID


class ErrorResponse(RequestDTO):
    error: ErrorDetail

"""NF-08 M1 shared provenance foundation; no capture, storage, or execution.

All wire fields, including constructor defaults, are serialized and required on
read. Version 1 rejects unknown fields/versions rather than dropping history.
"""

import re
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import BinaryIO, Literal, Protocol

from neurofold.core._contracts import Contract
from neurofold.core.canonical import CanonicalObject, sha256_bytes

SCHEMA_VERSION: Literal["neurofold-research/1"] = "neurofold-research/1"


class EvidenceKind(StrEnum):
    EXPERIMENTAL = "experimental"
    PREDICTED = "predicted"
    SYNTHETIC = "synthetic"


class MetadataState(StrEnum):
    PRESENT = "present"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


class HashEncoding(StrEnum):
    RAW = "raw-bytes/1"
    SEQUENCE = "sequence-ascii/1"
    CANONICAL_JSON = "neurofold-json/1"


class RecordStatus(StrEnum):
    """Capture state, never an assertion of successful scientific execution."""

    RECORDED = "recorded"
    INCOMPLETE = "incomplete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RedistributionStatus(StrEnum):
    ALLOWED = "allowed"
    PROHIBITED = "prohibited"
    UNKNOWN = "unknown"


def _text(value: str) -> None:
    if not value.strip():
        raise ValueError("Expected nonblank text")


def _utc(value: str) -> None:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.[0-9]{1,6})?Z", value):
        raise ValueError("Expected an explicit UTC timestamp ending in Z")
    datetime.fromisoformat(value)


def _sorted_unique(values: tuple[str, ...]) -> None:
    if tuple(sorted(set(values))) != values:
        raise ValueError("Expected unique lexicographically sorted identifiers")
    for value in values:
        _text(value)


@dataclass(frozen=True, kw_only=True)
class Metadata(Contract):
    """No bare null/zero sentinel: absent scientific information has a reason.

    Structured present values use a CanonicalObject for deep immutability.
    Individual producers must additionally validate their field-specific units,
    types and requiredness; this envelope is not a metric definition.
    """

    state: MetadataState
    value: str | int | bool | CanonicalObject | None
    reason: str | None

    def _validate(self) -> None:
        if self.state is MetadataState.PRESENT:
            if self.value is None or self.reason is not None:
                raise ValueError("Present metadata needs a value and no absence reason")
        elif self.value is not None or self.reason is None:
            raise ValueError("Absent metadata needs null value and a reason")
        else:
            _text(self.reason)


@dataclass(frozen=True, kw_only=True)
class ReferenceCollection(Contract):
    """An unordered license/citation inventory with explicit absence semantics."""

    state: MetadataState
    values: tuple[str, ...]
    reason: str | None

    def _validate(self) -> None:
        _sorted_unique(self.values)
        if self.state is MetadataState.PRESENT:
            if not self.values or self.reason is not None:
                raise ValueError(
                    "Present references need identifiers and no absence reason"
                )
        elif self.values or self.reason is None:
            raise ValueError("Absent references need an empty inventory and a reason")
        else:
            _text(self.reason)


@dataclass(frozen=True, kw_only=True)
class ContentHash(Contract):
    """The same hex digest can refer to distinct encoding domains."""

    sha256: str
    encoding: HashEncoding
    algorithm: Literal["sha256"] = "sha256"

    def _validate(self) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            raise ValueError("SHA-256 must be 64 lowercase hexadecimal characters")


@dataclass(frozen=True, kw_only=True)
class VersionedRecord(Contract):
    schema_version: Literal["neurofold-research/1"] = SCHEMA_VERSION


@dataclass(frozen=True, kw_only=True)
class ScientificInput(VersionedRecord):
    """An immutable content-identity envelope, not a domain validation shortcut.

    Producers resolve defaults and validate payload against input_schema before
    construction. Receipt dates, display settings and local paths stay outside.
    """

    input_schema: str
    payload: CanonicalObject
    record_kind: Literal["scientific_input"] = "scientific_input"
    canonicalization_version: Literal["neurofold-json/1"] = "neurofold-json/1"

    def _validate(self) -> None:
        _text(self.input_schema)

    @property
    def content_hash(self) -> ContentHash:
        return ContentHash(
            sha256=sha256_bytes(self.to_json()), encoding=HashEncoding.CANONICAL_JSON
        )


@dataclass(frozen=True, kw_only=True)
class ContentReference(Contract):
    """Opaque record identity plus an independently verifiable content identity."""

    record_id: str
    content_hash: ContentHash

    def _validate(self) -> None:
        _text(self.record_id)


@dataclass(frozen=True, kw_only=True)
class ArtifactRights(Contract):
    """Rights belong to each artifact; project licensing grants no default rights."""

    license: Metadata
    attribution: Metadata
    redistribution: RedistributionStatus
    basis: str

    def _validate(self) -> None:
        _text(self.basis)
        for metadata in (self.license, self.attribution):
            if metadata.state is MetadataState.PRESENT:
                if type(metadata.value) is not str:
                    raise ValueError(
                        "License and attribution must be textual references"
                    )
                _text(metadata.value)
        if self.redistribution is RedistributionStatus.ALLOWED:
            if self.license.state is not MetadataState.PRESENT:
                raise ValueError(
                    "Redistribution permission requires an identified license"
                )


@dataclass(frozen=True, kw_only=True)
class ArtifactDescriptor(VersionedRecord):
    """Registered original bytes, never a path or a reserialization of results."""

    artifact_id: str
    content_hash: ContentHash
    byte_size: int
    media_type: str
    evidence: EvidenceKind
    rights: ArtifactRights
    parents: tuple[ContentHash, ...]
    transformation: Metadata
    record_kind: Literal["artifact"] = "artifact"

    def _validate(self) -> None:
        _text(self.artifact_id)
        if self.content_hash.encoding is not HashEncoding.RAW:
            raise ValueError("Artifact checksums must identify original raw bytes")
        if self.byte_size < 0:
            raise ValueError("Artifact size cannot be negative")
        if not re.fullmatch(
            r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+", self.media_type
        ):
            raise ValueError("Expected a media type without parameters")
        keys = tuple(f"{item.encoding}:{item.sha256}" for item in self.parents)
        _sorted_unique(keys)
        if self.content_hash in self.parents:
            raise ValueError("An artifact cannot be its own parent")
        if self.parents:
            if self.transformation.state is not MetadataState.PRESENT:
                raise ValueError("Derived artifacts need transformation metadata")
        elif self.transformation.state is not MetadataState.NOT_APPLICABLE:
            raise ValueError(
                "Original artifacts must explicitly mark no transformation"
            )


@dataclass(frozen=True, kw_only=True)
class SourceReceipt(VersionedRecord):
    """One retrieval event; equal source bytes never erase separate receipts."""

    receipt_id: str
    provider: str
    query: str
    retrieved_at: str
    raw_artifact: ArtifactDescriptor
    accession: Metadata
    isoform: Metadata
    taxon_id: Metadata
    entry_version: Metadata
    sequence_version: Metadata
    release: Metadata
    release_date: Metadata
    etag: Metadata
    last_modified: Metadata
    license_references: ReferenceCollection
    citation_references: ReferenceCollection
    record_kind: Literal["source_receipt"] = "source_receipt"

    def _validate(self) -> None:
        for value in (self.receipt_id, self.provider, self.query):
            _text(value)
        _utc(self.retrieved_at)
        for metadata in (
            self.accession,
            self.isoform,
            self.release,
            self.release_date,
            self.etag,
            self.last_modified,
        ):
            if metadata.state is MetadataState.PRESENT:
                if type(metadata.value) is not str:
                    raise ValueError("Source text metadata must be a string")
                _text(metadata.value)
        for metadata in (self.entry_version, self.sequence_version):
            if metadata.state is MetadataState.PRESENT:
                if type(metadata.value) not in (str, int):
                    raise ValueError("Source versions must be strings or integers")
                if isinstance(metadata.value, str):
                    _text(metadata.value)
        if self.taxon_id.state is MetadataState.PRESENT:
            if type(self.taxon_id.value) is not int or self.taxon_id.value <= 0:
                raise ValueError("NCBI taxon identity must be a positive integer")


@dataclass(frozen=True, kw_only=True)
class ProvenanceSections(Contract):
    """Explicit capture slots; producers own the typed contents in later tasks."""

    preprocessing: Metadata
    model: Metadata
    execution: Metadata
    environment: Metadata
    comparison: Metadata
    interpretation: Metadata
    rights_privacy: Metadata


@dataclass(frozen=True, kw_only=True)
class ProvenanceRecord(VersionedRecord):
    """Manifest skeleton, not a publishable successful prediction schema.

    NF-04 must introduce a versioned complete prediction contract/validator before
    publishing successes. These records can describe incomplete/failed attempts.
    """

    record_id: str
    subject_kind: str
    created_at: str
    producer_version: str
    status: RecordStatus
    evidence: EvidenceKind
    inputs: tuple[ContentReference, ...]
    source_receipt_ids: tuple[str, ...]
    artifacts: tuple[ArtifactDescriptor, ...]
    sections: ProvenanceSections
    warnings: tuple[str, ...]
    record_kind: Literal["provenance"] = "provenance"
    canonicalization_version: Literal["neurofold-json/1"] = "neurofold-json/1"

    def _validate(self) -> None:
        for value in (self.record_id, self.subject_kind, self.producer_version):
            _text(value)
        _utc(self.created_at)
        _sorted_unique(self.source_receipt_ids)
        artifact_ids = tuple(item.artifact_id for item in self.artifacts)
        if len(set(artifact_ids)) != len(artifact_ids):
            raise ValueError("Duplicate artifact ID")
        input_ids = tuple(item.record_id for item in self.inputs)
        if len(set(input_ids)) != len(input_ids):
            raise ValueError("Duplicate input ID")
        if self.evidence is EvidenceKind.SYNTHETIC and any(
            item.evidence is not EvidenceKind.SYNTHETIC for item in self.artifacts
        ):
            raise ValueError(
                "Synthetic records must label every output artifact as synthetic"
            )
        if self.subject_kind == "prediction" and self.status is RecordStatus.RECORDED:
            raise ValueError("M1 skeleton cannot certify a successful prediction")
        for warning in self.warnings:
            _text(warning)


class ArtifactStore(Protocol):
    """Future streaming registry; implementations verify bytes and publish atomically.

    Unknown IDs raise KeyError. Conflicting immutable writes/integrity failures
    raise ValueError. No caller-controlled filesystem paths cross this seam.
    """

    def describe(self, artifact_id: str) -> ArtifactDescriptor: ...

    def open(self, artifact_id: str) -> AbstractContextManager[BinaryIO]: ...

    def publish(self, source: BinaryIO, *, descriptor: ArtifactDescriptor) -> None: ...


class ManifestRepository(Protocol):
    """Future append-only manifest registry; identical repeats may be idempotent.

    Unknown IDs raise KeyError; conflicting writes raise ValueError. Publication
    does not itself certify scientific completeness or license permission.
    """

    def get(self, record_id: str) -> ProvenanceRecord: ...

    def publish(self, record: ProvenanceRecord) -> None: ...

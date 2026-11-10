"""Predicted samples, complete provenance and pure publication validation."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol

from neurofold.core.biological import ReferenceSnapshot
from neurofold.core.canonical import canonical_decimal, sha256_bytes
from neurofold.core.prediction_base import (
    PredictionError,
    PredictionRecord,
    SoftwareIdentity,
    domain,
    identifier,
    require,
    unique,
)
from neurofold.core.prediction_base import (
    PredictionErrorCode as E,
)
from neurofold.core.prediction_base import (
    ValidationStage as S,
)
from neurofold.core.prediction_inputs import (
    AuxiliaryInput,
    PredictionProfile,
    PredictionSpec,
    validate_inputs,
)
from neurofold.core.prediction_jobs import (
    PredictionAttempt,
    PredictionJob,
    instant,
    validate_success_eligibility,
)
from neurofold.core.provenance import (
    ArtifactDescriptor,
    ArtifactRights,
    ContentHash,
    ContentReference,
    EvidenceKind,
    HashEncoding,
    Metadata,
    MetadataState,
    SourceReceipt,
    _text,
)
from neurofold.core.variants import VariantDefinition


@dataclass(frozen=True, kw_only=True)
class OutputRecord(PredictionRecord):
    schema_version: Literal["neurofold-prediction-result/1"] = (
        "neurofold-prediction-result/1"
    )


@dataclass(frozen=True, kw_only=True)
class PredictionResidue(OutputRecord):
    chain_id: str
    token_index: int
    input_position: int
    coordinate_residue_id: str
    insertion_code: Metadata

    def _validate(self) -> None:
        identifier(self.chain_id)
        require(self.token_index >= 0 and self.input_position > 0)
        _text(self.coordinate_residue_id)
        require(
            self.insertion_code.state is not MetadataState.PRESENT
            or type(self.insertion_code.value) is str
        )


@dataclass(frozen=True, kw_only=True)
class PredictionMapping(OutputRecord):
    mapping_id: str
    sample_id: str
    spec_hash: ContentHash
    sequence_hash: ContentHash
    structure: ContentReference
    method: SoftwareIdentity
    rows: tuple[PredictionResidue, ...]
    transformations: tuple[str, ...]
    numbering: Literal["input-1-based;token-0-based;coordinate-text"] = (
        "input-1-based;token-0-based;coordinate-text"
    )
    coordinate_units: Literal["angstrom"] = "angstrom"
    coordinate_convention: Literal["cartesian"] = "cartesian"

    def _validate(self) -> None:
        identifier(self.mapping_id)
        identifier(self.sample_id)
        require(self.spec_hash.encoding is HashEncoding.CANONICAL_JSON)
        require(self.sequence_hash.encoding is HashEncoding.SEQUENCE)
        domain(self.structure, HashEncoding.RAW)
        require(bool(self.rows))
        require(
            tuple(row.input_position for row in self.rows)
            == tuple(range(1, len(self.rows) + 1))
        )
        require(
            sorted(row.token_index for row in self.rows) == list(range(len(self.rows)))
        )
        require(len({row.chain_id for row in self.rows}) == 1)
        require(
            len(
                {
                    (
                        row.coordinate_residue_id,
                        row.insertion_code.state,
                        row.insertion_code.value,
                    )
                    for row in self.rows
                }
            )
            == len(self.rows)
        )
        for step in self.transformations:
            _text(step)


@dataclass(frozen=True, kw_only=True)
class ConfidenceDescriptor(OutputRecord):
    name: str
    state: MetadataState
    reason: str | None
    source_field: str | None
    definition: str | None
    units: str | None
    scale_min: str | None
    scale_max: str | None
    scope: Literal["sample", "residue", "residue_pair"]
    artifact: ContentReference | None
    mapping: ContentReference | None

    def _validate(self) -> None:
        identifier(self.name)
        fields = (
            self.source_field,
            self.definition,
            self.units,
            self.scale_min,
            self.scale_max,
        )
        if self.state is MetadataState.PRESENT:
            require(self.reason is None and all(value is not None for value in fields))
            require(self.artifact is not None and self.mapping is not None)
            assert self.artifact is not None and self.mapping is not None
            domain(self.artifact, HashEncoding.RAW)
            domain(self.mapping, HashEncoding.CANONICAL_JSON)
            for value in fields:
                assert value is not None
                _text(value)
            assert self.scale_min is not None and self.scale_max is not None
            require(
                Decimal(canonical_decimal(self.scale_min))
                < Decimal(canonical_decimal(self.scale_max))
            )
        else:
            require(self.reason is not None and all(value is None for value in fields))
            assert self.reason is not None
            _text(self.reason)
            require(self.artifact is None and self.mapping is None)


@dataclass(frozen=True, kw_only=True)
class PredictionSample(OutputRecord):
    sample_id: str
    evidence: EvidenceKind
    returned_rank: int
    ranking_definition: str
    structure: ContentReference
    mapping: PredictionMapping
    confidence: tuple[ConfidenceDescriptor, ...]
    raw_artifacts: tuple[ContentReference, ...]
    warnings: tuple[str, ...]

    def _validate(self) -> None:
        identifier(self.sample_id)
        require(self.evidence in (EvidenceKind.SYNTHETIC, EvidenceKind.PREDICTED))
        require(self.returned_rank > 0)
        _text(self.ranking_definition)
        domain(self.structure, HashEncoding.RAW)
        require(
            self.mapping.sample_id == self.sample_id
            and self.mapping.structure == self.structure
        )
        unique(tuple(item.record_id for item in self.raw_artifacts))
        require(self.structure in self.raw_artifacts and bool(self.confidence))
        unique(tuple(item.name for item in self.confidence))
        for item in self.raw_artifacts:
            domain(item, HashEncoding.RAW)
        mapping_ref = ContentReference(
            record_id=self.mapping.mapping_id, content_hash=self.mapping.content_hash
        )
        for descriptor in self.confidence:
            if descriptor.state is MetadataState.PRESENT:
                require(
                    descriptor.mapping == mapping_ref
                    and descriptor.artifact in self.raw_artifacts
                )
        for warning in self.warnings:
            _text(warning)


@dataclass(frozen=True, kw_only=True)
class PredictionResult(OutputRecord):
    result_id: str
    spec_hash: ContentHash
    job_id: str
    attempt_id: str
    evidence: EvidenceKind
    manifest: ContentReference
    samples: tuple[PredictionSample, ...]
    raw_artifacts: tuple[ContentReference, ...]
    warnings: tuple[str, ...]

    def _validate(self) -> None:
        for value in (self.result_id, self.job_id, self.attempt_id):
            identifier(value)
        require(self.spec_hash.encoding is HashEncoding.CANONICAL_JSON)
        domain(self.manifest, HashEncoding.CANONICAL_JSON)
        require(bool(self.samples))
        unique(tuple(item.sample_id for item in self.samples))
        unique(tuple(item.mapping.mapping_id for item in self.samples))
        require(len({item.returned_rank for item in self.samples}) == len(self.samples))
        require(len({item.ranking_definition for item in self.samples}) == 1)
        unique(tuple(item.record_id for item in self.raw_artifacts))
        for item in self.raw_artifacts:
            domain(item, HashEncoding.RAW)
        for sample in self.samples:
            require(sample.evidence == self.evidence)
            require(sample.mapping.spec_hash == self.spec_hash)
            require(all(item in self.raw_artifacts for item in sample.raw_artifacts))
        for warning in self.warnings:
            _text(warning)


@dataclass(frozen=True, kw_only=True)
class ProvenanceSection(PredictionRecord):
    schema_version: Literal["neurofold-prediction-provenance/1"] = (
        "neurofold-prediction-provenance/1"
    )


@dataclass(frozen=True, kw_only=True)
class WeightIdentity(ProvenanceSection):
    identity: SoftwareIdentity
    artifact: ContentReference
    rights: ArtifactRights

    def _validate(self) -> None:
        domain(self.artifact, HashEncoding.RAW)


@dataclass(frozen=True, kw_only=True)
class ModelProvenance(ProvenanceSection):
    model_state: MetadataState
    weights_state: MetadataState
    model: SoftwareIdentity | None
    model_absence_reason: str | None
    weights: tuple[WeightIdentity, ...]
    weights_absence_reason: str | None

    def _validate(self) -> None:
        require((self.model_state is MetadataState.PRESENT) == (self.model is not None))
        require((self.weights_state is MetadataState.PRESENT) == bool(self.weights))
        require((self.model is None) == (self.model_absence_reason is not None))
        require((not self.weights) == (self.weights_absence_reason is not None))
        unique(tuple(item.artifact.record_id for item in self.weights))
        for reason in (self.model_absence_reason, self.weights_absence_reason):
            if reason is not None:
                _text(reason)


@dataclass(frozen=True, kw_only=True)
class EnvironmentProvenance(ProvenanceSection):
    runtime: SoftwareIdentity
    operating_system: SoftwareIdentity
    hardware: str
    processor_kind: Literal["cpu", "accelerator"]
    accelerator: Metadata
    driver: Metadata
    cuda: Metadata
    libraries: tuple[SoftwareIdentity, ...]
    dependency_locks: tuple[ContentReference, ...]

    def _validate(self) -> None:
        _text(self.hardware)
        require(bool(self.libraries) and bool(self.dependency_locks))
        unique(tuple(item.name for item in self.libraries))
        unique(tuple(item.record_id for item in self.dependency_locks))
        for lock in self.dependency_locks:
            domain(lock, HashEncoding.RAW)
        for metadata in (self.accelerator, self.driver, self.cuda):
            require(
                metadata.state is not MetadataState.PRESENT
                or type(metadata.value) is str
            )
            if metadata.state is MetadataState.PRESENT:
                assert isinstance(metadata.value, str)
                _text(metadata.value)


@dataclass(frozen=True, kw_only=True)
class ExecutionProvenance(ProvenanceSection):
    job_id: str
    attempt: PredictionAttempt
    started_at: str
    ended_at: str

    def _validate(self) -> None:
        identifier(self.job_id)
        require(self.started_at == self.attempt.started_at)
        require(instant(self.started_at) <= instant(self.ended_at))


@dataclass(frozen=True, kw_only=True)
class PreprocessingProvenance(ProvenanceSection):
    software: SoftwareIdentity
    steps: tuple[str, ...]
    no_steps_reason: str | None

    def _validate(self) -> None:
        require(bool(self.steps) == (self.no_steps_reason is None))
        if self.no_steps_reason is not None:
            _text(self.no_steps_reason)
        for step in self.steps:
            _text(step)


@dataclass(frozen=True, kw_only=True)
class AuxiliaryProvenance(ProvenanceSection):
    """Actual captured inputs, including later remote-generated artifacts."""

    resolved: AuxiliaryInput
    provider: SoftwareIdentity | None
    obtained_at: str | None

    def _validate(self) -> None:
        require(self.resolved.mode != "remote")
        require((self.provider is None) == (self.obtained_at is None))
        if self.obtained_at is not None:
            instant(self.obtained_at)


@dataclass(frozen=True, kw_only=True)
class SuccessfulPredictionProvenance(ProvenanceSection):
    manifest_id: str
    result_id: str
    spec: PredictionSpec
    source_receipt: SourceReceipt
    evidence: EvidenceKind
    model: ModelProvenance
    environment: EnvironmentProvenance
    execution: ExecutionProvenance
    preprocessing: PreprocessingProvenance
    msa: AuxiliaryProvenance
    templates: AuxiliaryProvenance
    constraints: AuxiliaryProvenance
    samples: tuple[PredictionSample, ...]
    returned_sample_ids: tuple[str, ...]
    raw_artifacts: tuple[ContentReference, ...]
    artifacts: tuple[ArtifactDescriptor, ...]
    warnings: tuple[str, ...]
    known_nondeterminism: tuple[str, ...]
    interpretation_limits: tuple[str, ...]
    status: Literal["succeeded"] = "succeeded"

    def _validate(self) -> None:
        identifier(self.manifest_id)
        identifier(self.result_id)
        unique(self.returned_sample_ids)
        unique(tuple(item.artifact_id for item in self.artifacts))
        unique(tuple(item.record_id for item in self.raw_artifacts))
        require(
            bool(self.samples)
            and bool(self.known_nondeterminism)
            and bool(self.interpretation_limits)
        )
        for text in (
            *self.warnings,
            *self.known_nondeterminism,
            *self.interpretation_limits,
        ):
            _text(text)


class ArtifactResolver(Protocol):
    """Bounded registry reads; KeyError means missing; failures must be typed.

    Supplied implementations own read bounds and safe IO error translation.
    M1's tests use in-memory authored bytes only.
    """

    def describe(self, artifact_id: str) -> ArtifactDescriptor: ...

    def read(self, artifact_id: str) -> bytes: ...


def validate_completeness(manifest: SuccessfulPredictionProvenance) -> None:
    """Required declarations, not runtime truth, molecular parsing or license review."""
    require(type(manifest) is SuccessfulPredictionProvenance)
    spec, model, environment = manifest.spec, manifest.model, manifest.environment
    require(
        manifest.evidence == spec.profile.evidence,
        E.INCOMPLETE_PROVENANCE,
        S.PROVENANCE,
    )
    require(
        manifest.preprocessing.steps == spec.transformations,
        E.INCOMPLETE_PROVENANCE,
        S.PROVENANCE,
    )
    synthetic = manifest.evidence is EvidenceKind.SYNTHETIC
    require(
        synthetic or manifest.evidence is EvidenceKind.PREDICTED,
        E.INCOMPLETE_PROVENANCE,
        S.PROVENANCE,
    )
    require(
        spec.profile.availability == "available"
        or (synthetic and spec.profile.availability == "contract_only"),
        E.INCOMPLETE_PROVENANCE,
        S.PROVENANCE,
    )
    for requested, captured in (
        (spec.msa, manifest.msa),
        (spec.templates, manifest.templates),
        (spec.constraints, manifest.constraints),
    ):
        if requested.mode == "remote":
            require(
                captured.resolved.mode == "local"
                and captured.resolved.query_sequence_hash == spec.sequence_hash
                and captured.provider is not None
                and captured.obtained_at is not None,
                E.INCOMPLETE_PROVENANCE,
                S.PROVENANCE,
            )
            assert captured.obtained_at is not None
            require(
                instant(manifest.execution.started_at)
                <= instant(captured.obtained_at)
                <= instant(manifest.execution.ended_at),
                E.INCOMPLETE_PROVENANCE,
                S.PROVENANCE,
            )
        else:
            require(
                captured.resolved == requested and captured.provider is None,
                E.INCOMPLETE_PROVENANCE,
                S.PROVENANCE,
            )
    if synthetic:
        require(
            model.model_state is MetadataState.NOT_APPLICABLE
            and model.weights_state is MetadataState.NOT_APPLICABLE
            and model.model is None
            and not model.weights
            and environment.processor_kind == "cpu"
            and all(
                item.state is MetadataState.NOT_APPLICABLE
                for item in (
                    environment.accelerator,
                    environment.driver,
                    environment.cuda,
                )
            ),
            E.INCOMPLETE_PROVENANCE,
            S.PROVENANCE,
        )
    else:
        require(
            model.model_state is MetadataState.PRESENT
            and model.weights_state is MetadataState.PRESENT
            and model.model is not None
            and bool(model.weights),
            E.INCOMPLETE_PROVENANCE,
            S.PROVENANCE,
        )
        for weight in model.weights:
            require(
                weight.rights.license.state is MetadataState.PRESENT
                and weight.rights.attribution.state is MetadataState.PRESENT,
                E.INCOMPLETE_PROVENANCE,
                S.PROVENANCE,
            )
        expected = (
            MetadataState.PRESENT
            if environment.processor_kind == "accelerator"
            else MetadataState.NOT_APPLICABLE
        )
        require(
            all(
                item.state is expected
                for item in (
                    environment.accelerator,
                    environment.driver,
                    environment.cuda,
                )
            ),
            E.INCOMPLETE_PROVENANCE,
            S.PROVENANCE,
        )
    require(
        all(item.evidence == manifest.evidence for item in manifest.artifacts)
        and all(item.evidence == manifest.evidence for item in manifest.samples),
        E.INCOMPLETE_PROVENANCE,
        S.PROVENANCE,
    )


def _verify_artifact(
    resolver: ArtifactResolver, reference: ContentReference
) -> ArtifactDescriptor:
    try:
        descriptor = resolver.describe(reference.record_id)
        data = resolver.read(reference.record_id)
    except KeyError as exc:
        raise PredictionError(E.PUBLICATION_INTEGRITY, S.ARTIFACTS) from exc
    require(
        type(descriptor) is ArtifactDescriptor
        and type(data) is bytes
        and descriptor.artifact_id == reference.record_id
        and descriptor.content_hash == reference.content_hash
        and descriptor.byte_size == len(data)
        and descriptor.content_hash.sha256 == sha256_bytes(data),
        E.PUBLICATION_INTEGRITY,
        S.ARTIFACTS,
    )
    return descriptor


def validate_publication(
    *,
    job: PredictionJob,
    result: PredictionResult,
    manifest: SuccessfulPredictionProvenance,
    reference: ReferenceSnapshot,
    variant: VariantDefinition | None,
    profile: PredictionProfile,
    resolver: ArtifactResolver,
    expected_version: int,
    attempt_id: str,
    fence: int,
    now: str,
) -> None:
    """Validate supplied success proposal; M2 must atomically recheck fences/state."""
    require(
        type(job) is PredictionJob
        and type(result) is PredictionResult
        and type(manifest) is SuccessfulPredictionProvenance
    )
    validate_inputs(job.spec, reference=reference, variant=variant, profile=profile)
    validate_success_eligibility(
        job,
        expected_version=expected_version,
        attempt_id=attempt_id,
        fence=fence,
        now=now,
    )
    require(
        manifest.spec == job.spec
        and result.spec_hash == job.spec_hash
        and result.job_id == job.job_id == manifest.execution.job_id
        and result.attempt_id == attempt_id == manifest.execution.attempt.attempt_id
        and manifest.execution.attempt == job.attempt
        and manifest.result_id == result.result_id
        and result.manifest
        == ContentReference(
            record_id=manifest.manifest_id, content_hash=manifest.content_hash
        )
        and manifest.execution.ended_at == now
        and manifest.source_receipt == reference.protein.source_receipt,
        E.PUBLICATION_INTEGRITY,
        S.PROVENANCE,
    )
    validate_completeness(manifest)
    require(
        (instant(now) - instant(manifest.execution.started_at)).total_seconds()
        <= profile.limits.max_seconds,
        E.RESOURCE_LIMIT,
        S.PROVENANCE,
    )
    require(
        result.evidence == manifest.evidence
        and result.samples == manifest.samples
        and result.raw_artifacts == manifest.raw_artifacts
        and result.warnings == manifest.warnings
        and tuple(item.sample_id for item in result.samples)
        == manifest.returned_sample_ids
        and len(result.samples)
        == next(item.value for item in job.spec.parameters if item.name == "samples")
        and all(
            len(sample.mapping.rows) == len(job.spec.sequence)
            and sample.mapping.sequence_hash == job.spec.sequence_hash
            for sample in result.samples
        ),
        E.PUBLICATION_INTEGRITY,
        S.PROVENANCE,
    )
    outputs = {item.artifact_id: item for item in manifest.artifacts}
    require(
        set(outputs) == {item.record_id for item in result.raw_artifacts},
        E.PUBLICATION_INTEGRITY,
        S.ARTIFACTS,
    )
    require(
        sum(item.byte_size for item in outputs.values())
        <= profile.limits.max_output_bytes,
        E.RESOURCE_LIMIT,
        S.ARTIFACTS,
    )
    for artifact in result.raw_artifacts:
        require(
            _verify_artifact(resolver, artifact) == outputs[artifact.record_id],
            E.PUBLICATION_INTEGRITY,
            S.ARTIFACTS,
        )
    dependencies = [
        *manifest.environment.dependency_locks,
        *(weight.artifact for weight in manifest.model.weights),
        *(
            artifact
            for auxiliary in (manifest.msa, manifest.templates, manifest.constraints)
            for artifact in auxiliary.resolved.artifacts
        ),
        ContentReference(
            record_id=manifest.source_receipt.raw_artifact.artifact_id,
            content_hash=manifest.source_receipt.raw_artifact.content_hash,
        ),
    ]
    if job.spec.code.patch is not None:
        dependencies.append(job.spec.code.patch)
    verified: dict[str, ArtifactDescriptor] = {}
    for dependency in dependencies:
        descriptor = _verify_artifact(resolver, dependency)
        require(
            dependency.record_id not in outputs, E.PUBLICATION_INTEGRITY, S.ARTIFACTS
        )
        if dependency.record_id in verified:
            require(
                verified[dependency.record_id] == descriptor,
                E.PUBLICATION_INTEGRITY,
                S.ARTIFACTS,
            )
        verified[dependency.record_id] = descriptor
    require(
        verified[manifest.source_receipt.raw_artifact.artifact_id]
        == manifest.source_receipt.raw_artifact,
        E.PUBLICATION_INTEGRITY,
        S.ARTIFACTS,
    )
    for weight in manifest.model.weights:
        require(
            verified[weight.artifact.record_id].rights == weight.rights,
            E.PUBLICATION_INTEGRITY,
            S.ARTIFACTS,
        )
    known = {
        job.spec_hash,
        job.spec.reference.content_hash,
        job.spec.reference_sequence_hash,
        job.spec.sequence_hash,
        *(sample.mapping.content_hash for sample in result.samples),
        *(item.content_hash for item in outputs.values()),
        *(item.content_hash for item in verified.values()),
    }
    if job.spec.variant is not None:
        known.add(job.spec.variant.content_hash)
    _validate_lineage(tuple(outputs.values()) + tuple(verified.values()), known=known)


def _validate_lineage(
    descriptors: tuple[ArtifactDescriptor, ...], *, known: set[ContentHash]
) -> None:
    """Require closed declared parents and acyclic raw-artifact derivation."""
    parents: dict[ContentHash, set[ContentHash]] = {}
    for descriptor in descriptors:
        require(set(descriptor.parents) <= known, E.PUBLICATION_INTEGRITY, S.ARTIFACTS)
        parents.setdefault(descriptor.content_hash, set()).update(descriptor.parents)
    pending = {key: values & parents.keys() for key, values in parents.items()}
    while pending:
        ready = {key for key, values in pending.items() if not values}
        require(bool(ready), E.PUBLICATION_INTEGRITY, S.ARTIFACTS)
        pending = {
            key: values - ready for key, values in pending.items() if key not in ready
        }

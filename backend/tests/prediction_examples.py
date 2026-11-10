"""Authored tiny metadata/bytes, not an executable prediction adapter."""

from dataclasses import dataclass, replace

from test_variants import snapshot

from neurofold.core.biological import ReferenceSnapshot
from neurofold.core.canonical import sha256_bytes
from neurofold.core.prediction_base import SoftwareIdentity
from neurofold.core.prediction_inputs import (
    AuxiliaryInput,
    CodeIdentity,
    PredictionSpec,
    resolve_parameters,
    synthetic_profile,
)
from neurofold.core.prediction_jobs import PredictionAttempt, PredictionJob
from neurofold.core.prediction_outputs import (
    AuxiliaryProvenance,
    ConfidenceDescriptor,
    EnvironmentProvenance,
    ExecutionProvenance,
    ModelProvenance,
    PredictionMapping,
    PredictionResidue,
    PredictionResult,
    PredictionSample,
    PreprocessingProvenance,
    SuccessfulPredictionProvenance,
)
from neurofold.core.provenance import (
    ArtifactDescriptor,
    ContentHash,
    ContentReference,
    EvidenceKind,
    HashEncoding,
    Metadata,
    MetadataState,
)

SUBMITTED = "2026-11-10T10:00:00Z"
STARTED = "2026-11-10T10:00:01Z"
ENDED = "2026-11-10T10:00:02Z"
EXPIRES = "2026-11-10T10:01:01Z"
SOFTWARE = SoftwareIdentity(name="authored-contract", version="1")
NA = Metadata(
    state=MetadataState.NOT_APPLICABLE,
    value=None,
    reason="Synthetic contract; no runtime operation or physical measurement.",
)


def raw_hash(data: bytes) -> ContentHash:
    return ContentHash(sha256=sha256_bytes(data), encoding=HashEncoding.RAW)


def ref(record_id: str, content_hash: ContentHash) -> ContentReference:
    return ContentReference(record_id=record_id, content_hash=content_hash)


def absence() -> AuxiliaryInput:
    return AuxiliaryInput(
        mode="none",
        artifacts=(),
        reason="Authored synthetic input without auxiliary data.",
        query_sequence_hash=None,
        transformation=None,
    )


def spec_for(reference: ReferenceSnapshot | None = None) -> PredictionSpec:
    reference = reference or snapshot()
    profile = synthetic_profile()
    return PredictionSpec(
        reference=ref(reference.reference_id, reference.content_hash),
        reference_sequence_hash=reference.protein.sequence_hash,
        variant=None,
        sequence=reference.protein.sequence,
        sequence_hash=reference.protein.sequence_hash,
        profile=profile,
        parameters=resolve_parameters(profile, {}),
        seed=0,
        msa=absence(),
        templates=absence(),
        constraints=absence(),
        code=CodeIdentity(revision="authored-source-v1", dirty=False, patch=None),
        transformations=(),
    )


def queued(spec: PredictionSpec | None = None) -> PredictionJob:
    spec = spec or spec_for()
    return PredictionJob(
        job_id="job-1",
        spec=spec,
        spec_hash=spec.content_hash,
        state="queued",
        version=0,
        submitted_at=SUBMITTED,
        started_at=None,
        ended_at=None,
        attempt=None,
        cancellation_requested=False,
        termination_confirmed=False,
        retry_of_job_id=None,
        stage="queued",
        progress_basis_points=None,
        failure=None,
        result=None,
        manifest=None,
    )


def running(spec: PredictionSpec | None = None) -> PredictionJob:
    return replace(
        queued(spec),
        state="running",
        version=1,
        started_at=STARTED,
        stage="preparing",
        attempt=PredictionAttempt(
            attempt_id="attempt-1",
            worker_id="worker-1",
            lease_id="lease-1",
            fence=1,
            started_at=STARTED,
            heartbeat_at=STARTED,
            lease_expires_at=EXPIRES,
            fenced=False,
        ),
    )


@dataclass
class MemoryArtifacts:
    descriptors: dict[str, ArtifactDescriptor]
    data: dict[str, bytes]

    def describe(self, artifact_id: str) -> ArtifactDescriptor:
        return self.descriptors[artifact_id]

    def read(self, artifact_id: str) -> bytes:
        return self.data[artifact_id]


@dataclass
class Example:
    reference: ReferenceSnapshot
    job: PredictionJob
    result: PredictionResult
    manifest: SuccessfulPredictionProvenance
    resolver: MemoryArtifacts


def example() -> Example:
    reference = snapshot()
    spec = spec_for(reference)
    job = running(spec)
    assert job.attempt is not None
    source = reference.protein.source_receipt.raw_artifact
    structure_data = b"authored synthetic structure placeholder\n"
    confidence_data = b'{"authored_score":[0,1,0,1,0]}\n'
    lock_data = b"authored dependency lock placeholder\n"
    descriptors = tuple(
        replace(
            source,
            artifact_id=name,
            content_hash=raw_hash(data),
            byte_size=len(data),
            media_type=media,
        )
        for name, data, media in (
            ("structure-1", structure_data, "text/plain"),
            ("confidence-1", confidence_data, "application/json"),
            ("lock-1", lock_data, "text/plain"),
        )
    )
    structure, confidence, lock = descriptors
    structure_ref = ref(structure.artifact_id, structure.content_hash)
    confidence_ref = ref(confidence.artifact_id, confidence.content_hash)
    mapping = PredictionMapping(
        mapping_id="mapping-1",
        sample_id="sample-1",
        spec_hash=spec.content_hash,
        sequence_hash=spec.sequence_hash,
        structure=structure_ref,
        method=SOFTWARE,
        rows=tuple(
            PredictionResidue(
                chain_id="A",
                token_index=i,
                input_position=i + 1,
                coordinate_residue_id=str(i + 1),
                insertion_code=NA,
            )
            for i in range(5)
        ),
        transformations=(),
    )
    sample = PredictionSample(
        sample_id="sample-1",
        evidence=EvidenceKind.SYNTHETIC,
        returned_rank=1,
        ranking_definition="Authored order only; no biological accuracy meaning.",
        structure=structure_ref,
        mapping=mapping,
        confidence=(
            ConfidenceDescriptor(
                name="authored-score",
                state=MetadataState.PRESENT,
                reason=None,
                source_field="authored_score",
                definition="Authored test values; no accuracy interpretation.",
                units="dimensionless",
                scale_min="0",
                scale_max="1",
                scope="residue",
                artifact=confidence_ref,
                mapping=ref(mapping.mapping_id, mapping.content_hash),
            ),
        ),
        raw_artifacts=(structure_ref, confidence_ref),
        warnings=(),
    )
    manifest = SuccessfulPredictionProvenance(
        manifest_id="manifest-1",
        result_id="result-1",
        spec=spec,
        source_receipt=reference.protein.source_receipt,
        evidence=EvidenceKind.SYNTHETIC,
        model=ModelProvenance(
            model_state=MetadataState.NOT_APPLICABLE,
            weights_state=MetadataState.NOT_APPLICABLE,
            model=None,
            model_absence_reason="Synthetic authored contract without a model.",
            weights=(),
            weights_absence_reason="No model weights used.",
        ),
        environment=EnvironmentProvenance(
            runtime=SOFTWARE,
            operating_system=SOFTWARE,
            hardware="Authored CPU identity, not an execution observation.",
            processor_kind="cpu",
            accelerator=NA,
            driver=NA,
            cuda=NA,
            libraries=(SOFTWARE,),
            dependency_locks=(ref(lock.artifact_id, lock.content_hash),),
        ),
        execution=ExecutionProvenance(
            job_id=job.job_id, attempt=job.attempt, started_at=STARTED, ended_at=ENDED
        ),
        preprocessing=PreprocessingProvenance(
            software=SOFTWARE,
            steps=(),
            no_steps_reason="Exact authored input retained unchanged.",
        ),
        msa=AuxiliaryProvenance(resolved=spec.msa, provider=None, obtained_at=None),
        templates=AuxiliaryProvenance(
            resolved=spec.templates, provider=None, obtained_at=None
        ),
        constraints=AuxiliaryProvenance(
            resolved=spec.constraints, provider=None, obtained_at=None
        ),
        samples=(sample,),
        returned_sample_ids=("sample-1",),
        raw_artifacts=(structure_ref, confidence_ref),
        artifacts=(structure, confidence),
        warnings=(),
        known_nondeterminism=(
            "Authored declarations only; seed guarantees no runtime determinism.",
        ),
        interpretation_limits=(
            "Synthetic placeholders are not molecular parsing or scientific evidence.",
        ),
    )
    result = PredictionResult(
        result_id="result-1",
        spec_hash=spec.content_hash,
        job_id=job.job_id,
        attempt_id=job.attempt.attempt_id,
        evidence=EvidenceKind.SYNTHETIC,
        manifest=ref(manifest.manifest_id, manifest.content_hash),
        samples=(sample,),
        raw_artifacts=manifest.raw_artifacts,
        warnings=(),
    )
    resolver = MemoryArtifacts(
        descriptors={item.artifact_id: item for item in (*descriptors, source)},
        data={
            structure.artifact_id: structure_data,
            confidence.artifact_id: confidence_data,
            lock.artifact_id: lock_data,
            source.artifact_id: reference.protein.sequence.encode("ascii"),
        },
    )
    return Example(
        reference=reference,
        job=job,
        result=result,
        manifest=manifest,
        resolver=resolver,
    )

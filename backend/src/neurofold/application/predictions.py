"""Offline prediction submission, publication and retained reads via core seams."""

import re
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from neurofold.core.biological import ReferenceRepository
from neurofold.core.canonical import sequence_sha256, sha256_bytes
from neurofold.core.errors import ArchiveIntegrityError
from neurofold.core.orchestration import (
    Clock,
    DurableJobs,
    OrchestrationError,
    PublicationArchive,
)
from neurofold.core.prediction_bundle import ChildBundle
from neurofold.core.prediction_inputs import (
    AuxiliaryInput,
    CodeIdentity,
    PredictionProfile,
    PredictionSpec,
    resolve_parameters,
    validate_inputs,
)
from neurofold.core.prediction_jobs import PredictionJob
from neurofold.core.prediction_outputs import (
    PredictionResult,
    SuccessfulPredictionProvenance,
)
from neurofold.core.provenance import ContentHash, ContentReference, HashEncoding
from neurofold.core.variants import VariantRepository


class PredictionService:
    def __init__(
        self,
        jobs: DurableJobs,
        archive: PublicationArchive,
        references: ReferenceRepository,
        variants: VariantRepository,
        *,
        profiles: tuple[PredictionProfile, ...],
        code: CodeIdentity | None,
        clock: Clock,
        worker_available: Callable[[], bool] = lambda: False,
    ) -> None:
        self.jobs, self.archive, self.references, self.variants = (
            jobs,
            archive,
            references,
            variants,
        )
        self.profiles, self.code, self.clock, self.worker_available = (
            profiles,
            code,
            clock,
            worker_available,
        )

    def submit(
        self,
        *,
        key: str,
        reference_id: str,
        variant_id: str | None,
        adapter_profile_id: str,
        parameters: dict[str, Any],
        seed: int,
        msa_artifact_id: str | None,
        retry_of_job_id: str | None,
    ) -> PredictionJob:
        if re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", key) is None:
            raise OrchestrationError("INVALID_IDEMPOTENCY_KEY")
        reference = self.references.get(reference_id)
        if reference.reference_id != reference_id:
            raise ArchiveIntegrityError("Reference repository identity mismatch")
        variant = self.variants.get(variant_id) if variant_id is not None else None
        if variant is not None and variant.variant_id != variant_id:
            raise ArchiveIntegrityError("Variant repository identity mismatch")
        profile = next(
            (p for p in self.profiles if p.profile.name == adapter_profile_id), None
        )
        if profile is None or msa_artifact_id is not None:
            raise OrchestrationError("PROFILE_UNAVAILABLE")
        if self.code is None:
            raise OrchestrationError("CODE_IDENTITY_REQUIRED")
        none = AuxiliaryInput(
            mode="none",
            artifacts=(),
            reason="Explicitly no auxiliary input.",
            query_sequence_hash=None,
            transformation=None,
        )
        sequence = variant.sequence if variant else reference.protein.sequence
        spec = PredictionSpec(
            reference=ContentReference(
                record_id=reference.reference_id, content_hash=reference.content_hash
            ),
            reference_sequence_hash=reference.protein.sequence_hash,
            variant=ContentReference(
                record_id=variant.variant_id,
                content_hash=ContentHash(
                    sha256=sha256_bytes(variant.to_json()),
                    encoding=HashEncoding.CANONICAL_JSON,
                ),
            )
            if variant
            else None,
            sequence=sequence,
            sequence_hash=ContentHash(
                sha256=sequence_sha256(sequence), encoding=HashEncoding.SEQUENCE
            ),
            profile=profile,
            parameters=resolve_parameters(profile, parameters),
            seed=seed,
            msa=none,
            templates=none,
            constraints=none,
            code=self.code,
            transformations=(),
        )
        validate_inputs(spec, reference=reference, variant=variant, profile=profile)
        job = self.jobs.submit(
            spec,
            key,
            retry_of_job_id,
            available=profile.availability == "available" and self.worker_available(),
        )

        if job.state == "succeeded":
            self.archive.verify(job)
        return job

    def get(self, job_id: str) -> PredictionJob:
        job = self.jobs.get(job_id)
        if job.state == "succeeded":
            self.archive.verify(job)
        return job

    def cancel(self, job_id: str) -> PredictionJob:
        return self.jobs.cancel(job_id)

    def records(
        self, job_id: str
    ) -> tuple[PredictionResult, SuccessfulPredictionProvenance]:
        job = self.jobs.get(job_id)
        if job.state != "succeeded":
            raise OrchestrationError("JOB_CONFLICT")
        return self.archive.verify(job)

    def publish(
        self, owner: PredictionJob, bundle: ChildBundle, launch: PredictionJob
    ) -> PredictionJob:
        # Validate original linkage before sealing only operational attempt fields.
        if (
            bundle.result.manifest
            != ContentReference(
                record_id=bundle.manifest.manifest_id,
                content_hash=bundle.manifest.content_hash,
            )
            or bundle.manifest.spec != owner.spec
            or bundle.result.job_id != owner.job_id
            or bundle.result.attempt_id != launch.attempt.attempt_id  # type: ignore[union-attr]
            or bundle.manifest.execution.attempt != launch.attempt
            or bundle.manifest.execution.job_id != owner.job_id
            or bundle.manifest.execution.started_at != launch.started_at
        ):
            raise ArchiveIntegrityError("Child proposal ownership mismatch")
        reference = self.references.get(owner.spec.reference.record_id)
        variant = (
            self.variants.get(owner.spec.variant.record_id)
            if owner.spec.variant
            else None
        )
        now = self.clock()
        assert owner.attempt is not None
        manifest = replace(
            bundle.manifest,
            execution=replace(
                bundle.manifest.execution, attempt=owner.attempt, ended_at=now
            ),
        )
        result = replace(
            bundle.result,
            manifest=ContentReference(
                record_id=manifest.manifest_id, content_hash=manifest.content_hash
            ),
        )
        bundle = replace(bundle, result=result, manifest=manifest)
        intent_id = self.jobs.begin_publication(owner)
        with self.archive.lock():
            publication = self.archive.register(
                intent_id, owner, bundle, reference, variant, now
            )
            self.jobs.ready(publication)
            return self.jobs.succeed(publication)

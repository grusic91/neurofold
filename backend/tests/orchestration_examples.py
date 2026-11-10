"""Authored M2 proposals and storage fixtures, never production capabilities."""

import base64
from dataclasses import replace
from pathlib import Path

from prediction_examples import ENDED, SUBMITTED, example, ref
from test_prediction_outputs import rebound_spec
from test_variant_storage import retain

from neurofold.adapters.biological.storage import FilesystemStore
from neurofold.adapters.prediction_archive import PredictionArchive
from neurofold.adapters.prediction_sqlite import SQLiteJobs
from neurofold.adapters.variant_storage import FilesystemVariants
from neurofold.application.predictions import PredictionService
from neurofold.core.prediction_bundle import ChildBundle, StagedArtifact
from neurofold.core.prediction_inputs import (
    CodeIdentity,
    PredictionProfile,
    synthetic_profile,
)
from neurofold.core.prediction_jobs import PredictionJob


class ManualClock:
    def __init__(self, now: str = SUBMITTED) -> None:
        self.now = now

    def __call__(self) -> str:
        return self.now


def test_profile() -> PredictionProfile:
    profile = synthetic_profile()
    return replace(
        profile,
        availability="available",
        availability_reason=None,
        limits=replace(profile.limits, max_memory_bytes=512 * 1024 * 1024),
    )


def service_for(root: Path, clock: ManualClock) -> PredictionService:
    source = FilesystemStore(root / "data/source")
    retain(source, example().reference)
    jobs = SQLiteJobs(root / "data/jobs.sqlite3", clock=clock)
    return PredictionService(
        jobs,
        PredictionArchive(root / "data/registered", jobs, source.artifact_store),
        source,
        FilesystemVariants(source, source),
        profiles=(test_profile(),),
        code=CodeIdentity(revision="authored-source-v1", dirty=False, patch=None),
        clock=clock,
        worker_available=lambda: True,
    )


def submit(
    service: PredictionService,
    key: str = "key-1",
    *,
    seed: int = 0,
    variant: str | None = None,
    retry: str | None = None,
) -> PredictionJob:
    return service.submit(
        key=key,
        reference_id="synthetic-variant-reference",
        variant_id=variant,
        adapter_profile_id="contract-monomer",
        parameters={},
        seed=seed,
        msa_artifact_id=None,
        retry_of_job_id=retry,
    )


def bundle_for(job: PredictionJob) -> ChildBundle:
    e = rebound_spec(example(), job.spec)
    assert job.attempt is not None and job.started_at is not None
    sample = e.result.samples[0]
    mapping = replace(sample.mapping, mapping_id="mapping-" + job.job_id)
    sample = replace(
        sample,
        mapping=mapping,
        confidence=tuple(
            replace(c, mapping=ref(mapping.mapping_id, mapping.content_hash))
            if c.mapping
            else c
            for c in sample.confidence
        ),
    )
    manifest = replace(
        e.manifest,
        samples=(sample,),
        msa=replace(e.manifest.msa, resolved=job.spec.msa),
        templates=replace(e.manifest.templates, resolved=job.spec.templates),
        constraints=replace(e.manifest.constraints, resolved=job.spec.constraints),
        execution=replace(
            e.manifest.execution,
            job_id=job.job_id,
            attempt=job.attempt,
            started_at=job.started_at,
            ended_at=max(job.started_at, ENDED),
        ),
        manifest_id="manifest-" + job.job_id,
        result_id="result-" + job.job_id,
    )
    result = replace(
        e.result,
        samples=(sample,),
        result_id=manifest.result_id,
        job_id=job.job_id,
        attempt_id=job.attempt.attempt_id,
        manifest=ref(manifest.manifest_id, manifest.content_hash),
    )
    return ChildBundle(
        result=result,
        manifest=manifest,
        artifacts=tuple(
            StagedArtifact(
                descriptor=descriptor,
                base64_bytes=base64.b64encode(e.resolver.data[identity]).decode(
                    "ascii"
                ),
            )
            for identity, descriptor in e.resolver.descriptors.items()
        ),
    )

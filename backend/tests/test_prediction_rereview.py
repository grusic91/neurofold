"""Second-review regressions: lineage, immutable failures and active contention."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from threading import Event
from typing import Literal

import pytest
from fastapi.testclient import TestClient
from orchestration_examples import ManualClock, bundle_for, service_for, submit
from prediction_examples import ENDED
from test_prediction_durable import claimed
from test_prediction_hardening import FinishedChild

from neurofold.adapters.prediction_sqlite import SQLiteJobs
from neurofold.api.main import create_app
from neurofold.application.prediction_identity import scope_outputs
from neurofold.application.prediction_worker import PredictionWorker
from neurofold.core.canonical import sha256_bytes
from neurofold.core.errors import InvalidChildOutput
from neurofold.core.orchestration import OrchestrationError
from neurofold.core.prediction_failure import OperationalFailure
from neurofold.core.prediction_jobs import PredictionJob
from neurofold.core.provenance import ContentReference, Metadata, MetadataState


def test_mapping_lineage_scopes_both_descriptors_and_survives_reopen(
    tmp_path: Path,
) -> None:
    service, clock, owner = claimed(tmp_path)
    clock.now = ENDED
    bundle = bundle_for(owner)
    sample = bundle.result.samples[0]
    old_mapping = sample.mapping.content_hash
    unchanged = (owner.spec.content_hash, sample.structure.content_hash)
    confidence = sample.confidence[0].artifact
    assert confidence is not None
    descriptor = next(
        a for a in bundle.manifest.artifacts if a.artifact_id == confidence.record_id
    )
    descriptor = replace(
        descriptor,
        parents=tuple(
            sorted((old_mapping, *unchanged), key=lambda p: f"{p.encoding}:{p.sha256}")
        ),
        transformation=Metadata(
            state=MetadataState.PRESENT,
            value="Authored mapping-derived synthetic confidence.",
            reason=None,
        ),
    )
    manifest = replace(
        bundle.manifest,
        artifacts=tuple(
            descriptor if a.artifact_id == descriptor.artifact_id else a
            for a in bundle.manifest.artifacts
        ),
    )
    bundle = replace(
        bundle,
        manifest=manifest,
        result=replace(
            bundle.result,
            manifest=ContentReference(
                record_id=manifest.manifest_id, content_hash=manifest.content_hash
            ),
        ),
        artifacts=tuple(
            replace(a, descriptor=descriptor)
            if a.descriptor.artifact_id == descriptor.artifact_id
            else a
            for a in bundle.artifacts
        ),
    )
    scoped = scope_outputs(owner, bundle)
    scoped_descriptor = next(
        a
        for a in scoped.manifest.artifacts
        if a.content_hash == descriptor.content_hash
    )
    assert scoped_descriptor.parents == tuple(
        sorted(
            (scoped.result.samples[0].mapping.content_hash, *unchanged),
            key=lambda p: f"{p.encoding}:{p.sha256}",
        )
    )
    assert old_mapping not in scoped_descriptor.parents
    assert (
        next(
            a.descriptor
            for a in scoped.artifacts
            if a.descriptor.content_hash == descriptor.content_hash
        )
        == scoped_descriptor
    )
    assert [a.base64_bytes for a in scoped.artifacts] == [
        a.base64_bytes for a in bundle.artifacts
    ]
    service.publish(owner, bundle, owner)
    reopened = service_for(tmp_path, clock)
    result, retained = reopened.records(owner.job_id)
    assert result == scoped.result
    assert retained == scoped.manifest


@pytest.mark.parametrize(
    "field", ["samples", "returned_sample_ids", "result_id", "raw_artifacts"]
)
def test_scoping_rejects_linkage_before_it_can_reseal(
    field: str, tmp_path: Path
) -> None:
    _, _, owner = claimed(tmp_path)
    bundle = bundle_for(owner)
    sample = bundle.manifest.samples[0]
    changes: dict[str, object] = {
        "samples": (replace(sample, warnings=("Manifest-only authored warning.",)),),
        "returned_sample_ids": ("different-sample",),
        "result_id": "different-result",
        "raw_artifacts": tuple(reversed(bundle.manifest.raw_artifacts)),
    }
    assert changes[field] != getattr(bundle.manifest, field)
    manifest = replace(bundle.manifest, **{field: changes[field]})  # type: ignore[arg-type]
    with pytest.raises(InvalidChildOutput, match="linkage"):
        scope_outputs(owner, replace(bundle, manifest=manifest))


@pytest.mark.parametrize(
    "damage", ["checksum", "job_id", "job_hash", "attempt", "ended", "missing"]
)
def test_failure_integrity_through_both_routes(tmp_path: Path, damage: str) -> None:
    service, clock, owner = claimed(tmp_path)
    clock.now = ENDED
    failed = service.jobs.finish(owner, "TIMEOUT", terminated=True)
    failure = service.jobs.failure(owner.job_id)
    assert isinstance(service.jobs, SQLiteJobs)
    with closing(sqlite3.connect(service.jobs.path)) as connection, connection:
        if damage == "missing":
            connection.execute("DROP TRIGGER immutable_failure_delete")
            connection.execute("DELETE FROM failures WHERE job=?", (owner.job_id,))
        else:
            replacement = failure
            if damage == "job_id":
                replacement = replace(
                    failure, job=replace(failure.job, record_id="other-job")
                )
            elif damage == "job_hash":
                replacement = replace(
                    failure, job=replace(failure.job, content_hash=owner.content_hash)
                )
                assert owner.content_hash != failed.content_hash
            elif damage == "attempt":
                replacement = replace(failure, attempt_id="other-attempt")
            elif damage == "ended":
                replacement = replace(failure, ended_at="2026-11-10T12:00:00Z")
            body = replacement.to_json()
            digest = "0" * 64 if damage == "checksum" else sha256_bytes(body)
            connection.execute("DROP TRIGGER immutable_failure_update")
            connection.execute(
                "UPDATE failures SET body=?,sha=? WHERE job=?",
                (body, digest, owner.job_id),
            )
    with TestClient(create_app(prediction_factory=lambda: service)) as client:
        for suffix in ("", "/failure"):
            response = client.get(f"/v1/prediction-jobs/{owner.job_id}{suffix}")
            assert response.status_code == 500, response.text
            assert response.json()["error"]["code"] == "ARCHIVE_INTEGRITY"


def test_failure_cannot_bind_to_nonfailed_job(tmp_path: Path) -> None:
    service, clock, owner = claimed(tmp_path)
    clock.now = ENDED
    succeeded = service.publish(owner, bundle_for(owner), owner)
    assert succeeded.attempt is not None and succeeded.ended_at is not None
    body = OperationalFailure(
        job=ContentReference(
            record_id=owner.job_id, content_hash=succeeded.content_hash
        ),
        attempt_id=succeeded.attempt.attempt_id,
        ended_at=succeeded.ended_at,
        cause="TIMEOUT",
    ).to_json()
    assert isinstance(service.jobs, SQLiteJobs)
    with closing(sqlite3.connect(service.jobs.path)) as connection, connection:
        connection.execute(
            "INSERT INTO failures(job,body,sha) VALUES(?,?,?)",
            (owner.job_id, body, sha256_bytes(body)),
        )
    with TestClient(create_app(prediction_factory=lambda: service)) as client:
        assert (
            client.get(f"/v1/prediction-jobs/{owner.job_id}/failure").status_code == 500
        )


@pytest.mark.parametrize(
    "statement",
    ["UPDATE failures SET sha=sha WHERE job=?", "DELETE FROM failures WHERE job=?"],
)
def test_failure_storage_is_immutable(tmp_path: Path, statement: str) -> None:
    service, _, owner = claimed(tmp_path)
    service.jobs.finish(owner, "TIMEOUT", terminated=True)
    original = service.jobs.failure(owner.job_id)
    assert isinstance(service.jobs, SQLiteJobs)
    with closing(sqlite3.connect(service.jobs.path)) as connection, connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(statement, (owner.job_id,))
    assert service.jobs.failure(owner.job_id) == original


def test_failure_conflicts_for_nonfailed_and_genuine_legacy_only(
    tmp_path: Path,
) -> None:
    service, _, owner = claimed(tmp_path)
    path = f"/v1/prediction-jobs/{owner.job_id}"
    with TestClient(create_app(prediction_factory=lambda: service)) as client:
        assert client.get(path + "/failure").status_code == 409
        assert client.get("/v1/prediction-jobs/absent/failure").status_code == 404
        service.jobs.finish(owner, "TIMEOUT", terminated=True)
        assert isinstance(service.jobs, SQLiteJobs)
        with closing(sqlite3.connect(service.jobs.path)) as connection, connection:
            connection.execute("DROP TRIGGER immutable_failure_delete")
            connection.execute("DELETE FROM failures WHERE job=?", (owner.job_id,))
            connection.execute(
                "INSERT INTO legacy_failures(job) VALUES(?)", (owner.job_id,)
            )
        assert client.get(path + "/failure").status_code == 409
        assert client.get(path).status_code == 200


@pytest.mark.parametrize("operation", ["renew", "validating"])
@pytest.mark.parametrize("release_early", [False, True])
def test_active_publication_contention_is_retried_and_truthfully_classified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str, release_early: bool
) -> None:
    service = service_for(tmp_path, ManualClock())
    queued = submit(service)
    assert isinstance(service.jobs, SQLiteJobs)
    entered, proceed, busy, finishing, finish_allowed = (Event() for _ in range(5))
    renew, stage, finish = service.jobs.renew, service.jobs.stage, service.jobs.finish

    def gate() -> None:
        entered.set()
        assert proceed.wait(10)

    def renewing(job: PredictionJob, seconds: float) -> PredictionJob:
        gate()
        try:
            return renew(job, seconds)
        except OrchestrationError as exc:
            if exc.code == "PREDICTION_BUSY":
                busy.set()
            raise

    def staging(
        job: PredictionJob, value: Literal["preparing", "inference", "validating"]
    ) -> PredictionJob:
        if value == "validating":
            gate()
        try:
            return stage(job, value)
        except OrchestrationError as exc:
            if exc.code == "PREDICTION_BUSY":
                busy.set()
            raise

    def finishing_job(
        job: PredictionJob, reason: str, *, terminated: bool
    ) -> PredictionJob:
        finishing.set()
        assert finish_allowed.wait(10)
        return finish(job, reason, terminated=terminated)  # type: ignore[arg-type]

    monkeypatch.setattr(
        service.jobs,
        "renew" if operation == "renew" else "stage",
        renewing if operation == "renew" else staging,
    )
    monkeypatch.setattr(service.jobs, "finish", finishing_job)

    class Launcher:
        def launch(self, directory: Path, job: PredictionJob) -> FinishedChild:
            (directory / "bundle.json").write_bytes(bundle_for(job).to_json())
            return FinishedChild()

    worker = PredictionWorker(service, Launcher(), tmp_path / "staging")
    with (
        ThreadPoolExecutor(1) as pool,
        closing(sqlite3.connect(service.jobs.path)) as lock,
    ):
        future = pool.submit(worker.once)
        try:
            assert entered.wait(10)
            lock.execute("BEGIN IMMEDIATE")
            proceed.set()
            assert busy.wait(10)
            if not release_early:
                assert finishing.wait(10)
        finally:
            lock.rollback()
            proceed.set()
            finish_allowed.set()
        assert future.result(10)
    retained = service.get(queued.job_id)
    assert retained.state == ("succeeded" if release_early else "failed")
    if not release_early:
        assert service.jobs.failure(queued.job_id).cause == "SUPERVISION_FAILED"
    else:
        assert not finishing.is_set()


def test_running_cancel_returns_202_until_confirmed(tmp_path: Path) -> None:
    service, _, owner = claimed(tmp_path)
    path = f"/v1/prediction-jobs/{owner.job_id}/cancel"
    with TestClient(create_app(prediction_factory=lambda: service)) as client:
        response = client.post(path, json={})
        assert response.status_code == 202, response.text
        assert response.headers["Retry-After"] == "1"
        value = response.json()["job"]
        assert value["state"] == "cancelling"
        assert value["cancellation_requested"] and not value["termination_confirmed"]
        service.jobs.finish(service.get(owner.job_id), "SHUTDOWN", terminated=True)
        assert client.post(path, json={}).status_code == 200

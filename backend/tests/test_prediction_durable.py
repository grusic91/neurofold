"""Real SQLite transactions, immutable graph registration and restart failures."""

import sqlite3
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from threading import Barrier
from typing import Any

import pytest
from orchestration_examples import ManualClock, bundle_for, service_for, submit
from prediction_examples import ENDED, EXPIRES, STARTED
from prediction_test_retries import retry_busy
from test_variant_storage import create

from neurofold.adapters.prediction_archive import PredictionArchive
from neurofold.adapters.prediction_sqlite import SQLiteJobs
from neurofold.application.predictions import PredictionService
from neurofold.core.biological import ReferenceSnapshot
from neurofold.core.errors import ArchiveIntegrityError
from neurofold.core.orchestration import OrchestrationError, Publication
from neurofold.core.prediction_base import PredictionError
from neurofold.core.prediction_inputs import capabilities
from neurofold.core.prediction_jobs import PredictionJob
from neurofold.core.variants import VariantError


def claimed(root: Path) -> tuple[PredictionService, ManualClock, PredictionJob]:
    clock = ManualClock()
    service = service_for(root, clock)
    queued = submit(service)
    clock.now = STARTED
    job = service.jobs.claim("worker-1", 60)
    assert job is not None and job.job_id == queued.job_id
    return service, clock, job


def prepared(root: Path) -> tuple[PredictionService, ManualClock, Publication]:
    service, clock, job = claimed(root)
    clock.now = ENDED
    bundle = bundle_for(job)
    identity = service.jobs.begin_publication(job)
    assert isinstance(service.archive, PredictionArchive)
    publication = service.archive.register(
        identity,
        job,
        bundle,
        service.references.get(job.spec.reference.record_id),
        None,
        clock.now,
    )
    service.jobs.ready(publication)
    return service, clock, publication


def test_concurrent_idempotency_reopen_conflict_and_exact_specs(tmp_path: Path) -> None:
    clock = ManualClock()
    service = service_for(tmp_path, clock)
    barrier = Barrier(8)

    def concurrent(index: int) -> PredictionJob:
        independent = retry_busy(lambda: service_for(tmp_path, clock))
        barrier.wait(timeout=60)  # Thread-startup hang guard under CPU saturation.
        # Rendezvous after initialization: its flock must not serialize submits.
        return retry_busy(lambda: submit(independent))

    with ThreadPoolExecutor(8) as pool:
        jobs = list(pool.map(concurrent, range(8)))
    assert len({job.job_id for job in jobs}) == 1
    assert submit(service_for(tmp_path, clock)) == jobs[0]
    with pytest.raises(OrchestrationError, match="IDEMPOTENCY_CONFLICT"):
        submit(service, seed=1)
    with pytest.raises(OrchestrationError, match="INVALID_IDEMPOTENCY_KEY"):
        submit(service, "bad key")
    assert jobs[0].spec.sequence == "MACAG"
    assert jobs[0].spec.parameters[0].value == 1
    # Availability check follows durable key comparison.
    service.worker_available = lambda: False
    assert submit(service) == jobs[0]
    with pytest.raises(OrchestrationError, match="PROFILE_UNAVAILABLE"):
        submit(service, "new-key")


def test_verified_variant_and_missing_inconsistent_inputs(tmp_path: Path) -> None:
    clock = ManualClock()
    service = service_for(tmp_path, clock)
    from neurofold.application.variants import VariantService

    variant = create(VariantService(service.references, service.variants)).definition
    job = submit(service, variant=variant.variant_id)
    assert job.spec.sequence == "MACVG" and job.spec.variant is not None
    other = replace(
        service.references.get("synthetic-variant-reference"), reference_id="other"
    )

    class OtherReference:
        def publish(self, snapshot: ReferenceSnapshot) -> None:
            raise AssertionError

        def get(self, identity: str) -> Any:
            return other

    service.references = OtherReference()
    with pytest.raises((PredictionError, VariantError, ArchiveIntegrityError)):
        submit(service, "other", variant=variant.variant_id)
    with pytest.raises(KeyError):
        submit(service_for(tmp_path, clock), "other", variant="absent")


def test_competing_claims_single_capacity_version_fence_and_retry(
    tmp_path: Path,
) -> None:
    clock = ManualClock()
    service = service_for(tmp_path, clock)
    first, second = submit(service), submit(service, "key-2")
    clock.now = STARTED
    barrier = Barrier(2)

    def claim(worker: str) -> PredictionJob | None:
        barrier.wait(timeout=5)
        return service.jobs.claim(worker, 60)

    with ThreadPoolExecutor(2) as pool:
        claims = list(pool.map(claim, ("worker-a", "worker-b")))
    owners = [job for job in claims if job]
    assert len(owners) == 1 and owners[0].job_id == first.job_id
    owner = owners[0]
    clock.now = ENDED
    renewed = service.jobs.renew(owner, 60)
    assert renewed.version == owner.version + 1
    operations: tuple[Callable[[], PredictionJob], ...] = (
        lambda: service.jobs.renew(owner, 60),
        lambda: service.jobs.stage(owner, "inference"),
    )
    for operation in operations:
        with pytest.raises(OrchestrationError, match="JOB_CONFLICT"):
            operation()
    failed = service.jobs.finish(renewed, "CHILD_FAILED", terminated=True)
    before = failed.to_json()
    with pytest.raises(OrchestrationError):
        service.jobs.cancel(failed.job_id)
    assert service.jobs.get(failed.job_id).to_json() == before
    retry = submit(service, "retry", retry=failed.job_id)
    assert retry.retry_of_job_id == first.job_id
    with pytest.raises(PredictionError):
        submit(service, "invalid-retry", seed=1, retry=failed.job_id)
    next_job = service.jobs.claim("worker-c", 60)
    assert next_job is not None and next_job.job_id == second.job_id


def test_expiry_fencing_no_auto_retry_and_immutable_terminal(tmp_path: Path) -> None:
    service, clock, job = claimed(tmp_path)
    service.jobs.begin_publication(job)
    clock.now = EXPIRES
    with pytest.raises(OrchestrationError):
        service.jobs.renew(job, 60)
    assert service.jobs.recover() == 1
    recovered = service.jobs.get(job.job_id)
    assert recovered.state == "failed"
    assert recovered.attempt is not None and recovered.attempt.fenced
    assert service.jobs.reason(job.job_id) == "WORKER_LOST"
    assert service.jobs.recover() == 0
    assert service.jobs.claim("new-worker", 60) is None
    with pytest.raises(OrchestrationError):
        service.publish(job, bundle_for(job), job)
    with pytest.raises(OrchestrationError):
        service.jobs.finish(job, "CHILD_FAILED", terminated=True)


@pytest.mark.parametrize("win", ["cancel", "expiry", "heartbeat", "success"])
def test_final_transaction_rechecks_after_ready(tmp_path: Path, win: str) -> None:
    service, clock, publication = prepared(tmp_path)
    job = publication.job
    if win == "cancel":
        assert service.jobs.cancel(job.job_id).state == "cancelling"
    elif win == "expiry":
        clock.now = EXPIRES
    elif win == "heartbeat":
        service.jobs.renew(job, 60)
    else:
        succeeded = service.jobs.succeed(publication)
        assert succeeded.state == "succeeded"
        assert service.get(job.job_id) == succeeded
        with pytest.raises(OrchestrationError):
            service.cancel(job.job_id)
        assert service_for(tmp_path, clock).get(job.job_id) == succeeded
    with pytest.raises((OrchestrationError, PredictionError)):
        service.jobs.succeed(publication)
    if win != "success":
        assert service.jobs.get(job.job_id).state != "succeeded"


def test_cancel_success_actual_race_has_one_serialized_winner(tmp_path: Path) -> None:
    service, _, publication = prepared(tmp_path)
    barrier = Barrier(2)

    def cancel() -> str:
        barrier.wait(timeout=5)
        try:
            return service.cancel(publication.job.job_id).state
        except OrchestrationError:
            return "conflict"

    def succeed() -> str:
        barrier.wait(timeout=5)
        try:
            return service.jobs.succeed(publication).state
        except (OrchestrationError, PredictionError):
            return "conflict"

    with ThreadPoolExecutor(2) as pool:
        a, b = pool.submit(cancel), pool.submit(succeed)
        outcomes = {a.result(), b.result()}
    assert outcomes in ({"succeeded", "conflict"}, {"cancelling", "conflict"})


@pytest.mark.parametrize(
    "kind", ["reference", "mapping", "manifest", "result", "artifact"]
)
@pytest.mark.parametrize("damage", ["missing", "bytes", "symlink"])
def test_retained_graph_corruption_never_becomes_absence(
    tmp_path: Path, kind: str, damage: str
) -> None:
    service, _, publication = prepared(tmp_path)
    job = service.jobs.succeed(publication)
    archive = service.archive
    assert isinstance(archive, PredictionArchive)
    registration = next(r for r in publication.graph if r.kind == kind)
    path = archive.store._path(kind, registration.record_id)
    if damage == "missing":
        path.unlink()
    elif damage == "bytes":
        path.write_bytes(b"corrupt")
    else:
        copy = path.with_suffix(".original")
        path.rename(copy)
        path.symlink_to(copy)
    with pytest.raises(ArchiveIntegrityError):
        service.get(job.job_id)


@pytest.mark.parametrize("boundary", ["intent", "registered", "ready", "committed"])
def test_restart_at_publication_boundaries(tmp_path: Path, boundary: str) -> None:
    service, clock, job = claimed(tmp_path)
    clock.now = ENDED
    identity = service.jobs.begin_publication(job)
    if boundary != "intent":
        bundle = bundle_for(job)
        pub = service.archive.register(
            identity,
            job,
            bundle,
            service.references.get(job.spec.reference.record_id),
            None,
            clock.now,
        )
        if boundary in ("ready", "committed"):
            service.jobs.ready(pub)
        if boundary == "committed":
            service.jobs.succeed(pub)
    clock.now = EXPIRES
    reopened = service_for(tmp_path, clock)
    reopened.jobs.recover()
    retained = reopened.get(job.job_id)
    assert retained.state == ("succeeded" if boundary == "committed" else "failed")


def test_database_corruption_unknown_versions_contention_and_graph_binding(
    tmp_path: Path,
) -> None:
    service, _, pub = prepared(tmp_path)
    jobs = service.jobs
    assert isinstance(jobs, SQLiteJobs)
    with closing(sqlite3.connect(jobs.path)) as connection, connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM registrations")
        connection.execute("UPDATE publications SET body=?", (b"{}",))
    with pytest.raises(OrchestrationError):
        jobs.succeed(pub)
    with closing(sqlite3.connect(jobs.path)) as connection, connection:
        connection.execute("UPDATE jobs SET sha='corrupt'")
    with pytest.raises(ArchiveIntegrityError):
        jobs.get(pub.job.job_id)
    unknown = tmp_path / "unknown.sqlite3"
    with closing(sqlite3.connect(unknown)) as connection, connection:
        connection.execute("PRAGMA user_version=2")
    with pytest.raises(ArchiveIntegrityError):
        SQLiteJobs(unknown)
    fresh = SQLiteJobs(tmp_path / "busy.sqlite3")
    with closing(sqlite3.connect(fresh.path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        with pytest.raises(OrchestrationError, match="PREDICTION_BUSY"):
            fresh.recover()


def test_unavailable_profile_code_identity_and_error_precedence(tmp_path: Path) -> None:
    service = service_for(tmp_path, ManualClock())
    service.profiles = capabilities()[0].profiles
    with pytest.raises(OrchestrationError, match="PROFILE_UNAVAILABLE"):
        submit(service)
    service.code = None
    with pytest.raises(OrchestrationError, match="CODE_IDENTITY_REQUIRED"):
        submit(service)
    with pytest.raises(OrchestrationError, match="INVALID_IDEMPOTENCY_KEY"):
        submit(service, "bad key")


@pytest.mark.parametrize(
    "damage",
    ["bytes", "spec", "attempt", "missing", "provenance", "evidence", "unlisted"],
)
def test_publication_rejects_bad_staged_graph(tmp_path: Path, damage: str) -> None:
    service, clock, job = claimed(tmp_path)
    clock.now = ENDED
    bundle = bundle_for(job)
    if damage == "bytes":
        import base64

        item = bundle.artifacts[0]
        bundle = replace(
            bundle,
            artifacts=(
                replace(
                    item,
                    base64_bytes=base64.b64encode(
                        b"x" * item.descriptor.byte_size
                    ).decode(),
                ),
                *bundle.artifacts[1:],
            ),
        )
    elif damage == "spec":
        changed = replace(job.spec, seed=1)
        bundle = bundle_for(replace(job, spec=changed, spec_hash=changed.content_hash))
    elif damage == "attempt":
        bundle = replace(
            bundle, result=replace(bundle.result, attempt_id="old-attempt")
        )
    elif damage == "missing":
        bundle = replace(
            bundle,
            artifacts=tuple(
                a for a in bundle.artifacts if a.descriptor.artifact_id != "structure-1"
            ),
        )
    elif damage == "provenance":
        from neurofold.core.provenance import MetadataState

        bundle = replace(
            bundle,
            manifest=replace(
                bundle.manifest,
                model=replace(
                    bundle.manifest.model, model_state=MetadataState.UNAVAILABLE
                ),
            ),
        )
    elif damage == "evidence":
        from neurofold.core.provenance import EvidenceKind

        bundle = replace(
            bundle, manifest=replace(bundle.manifest, evidence=EvidenceKind.PREDICTED)
        )
    else:
        bundle = replace(
            bundle,
            artifacts=(
                *bundle.artifacts,
                replace(
                    bundle.artifacts[0],
                    descriptor=replace(
                        bundle.artifacts[0].descriptor, artifact_id="unlisted"
                    ),
                ),
            ),
        )
    with pytest.raises((ArchiveIntegrityError, PredictionError)):
        service.publish(job, bundle, job)
    assert service.jobs.get(job.job_id).state == "running"


@pytest.mark.parametrize(
    "boundary", ["intent", "artifact", "registered", "ready", "committed"]
)
def test_abrupt_process_exit_during_publication(tmp_path: Path, boundary: str) -> None:
    import os
    import subprocess
    import sys

    script = """
import os, sys
from pathlib import Path
import orchestration_child  # socket and DNS guard before any storage operation
from test_prediction_durable import claimed
from orchestration_examples import bundle_for
from prediction_examples import ENDED
root, point = Path(sys.argv[1]), sys.argv[2]
service, clock, job = claimed(root)
(root / 'job-id').write_text(job.job_id)
clock.now = ENDED
identity = service.jobs.begin_publication(job)
if point == 'intent': os._exit(92)
bundle = bundle_for(job)
if point == 'artifact':
    original = service.archive.store._publish
    def interrupted(kind, identity, data):
        original(kind, identity, data)
        os._exit(92)
    service.archive.store._publish = interrupted
reference = service.references.get(job.spec.reference.record_id)
pub = service.archive.register(identity, job, bundle, reference, None, clock.now)
if point == 'registered': os._exit(92)
service.jobs.ready(pub)
if point == 'ready': os._exit(92)
service.jobs.succeed(pub)
os._exit(92)
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), boundary],
        env=os.environ | {"PYTHONPATH": str(Path(__file__).parent.resolve())},
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 92, result.stderr
    service = service_for(tmp_path, ManualClock(EXPIRES))
    service.jobs.recover()
    job = service.get((tmp_path / "job-id").read_text())
    assert job.state == ("succeeded" if boundary == "committed" else "failed")
    assert submit(service).job_id == job.job_id


@pytest.mark.parametrize(
    "boundary", ["before_link", "after_link", "sqlite_ready", "after_commit"]
)
def test_io_failure_honest_uncertainty_and_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    service, clock, job = claimed(tmp_path)
    clock.now = ENDED
    archive = service.archive
    assert isinstance(archive, PredictionArchive)
    if boundary in ("before_link", "after_link"):
        original = archive.store._publish

        def fail(kind: str, identity: str, data: bytes) -> bool:
            if boundary == "after_link":
                original(kind, identity, data)
            raise OSError("authored disk failure")

        monkeypatch.setattr(archive.store, "_publish", fail)
    elif boundary == "sqlite_ready":

        def ready(pub: Publication) -> None:
            raise OSError("authored SQLite failure")

        monkeypatch.setattr(service.jobs, "ready", ready)
    else:
        original_success = service.jobs.succeed

        def uncertain(pub: Publication) -> PredictionJob:
            original_success(pub)
            raise OSError("response lost after commit")

        monkeypatch.setattr(service.jobs, "succeed", uncertain)
    with pytest.raises(OSError):
        service.publish(job, bundle_for(job), job)
    reopened = service_for(tmp_path, ManualClock(EXPIRES))
    reopened.jobs.recover()
    assert reopened.get(job.job_id).state == (
        "succeeded" if boundary == "after_commit" else "failed"
    )


def test_owner_identity_clock_and_execution_deadline_rechecked(tmp_path: Path) -> None:
    service, clock, pub = prepared(tmp_path)
    assert pub.job.attempt is not None
    for attempt in (
        replace(pub.job.attempt, worker_id="other"),
        replace(pub.job.attempt, lease_id="other"),
        replace(pub.job.attempt, fence=99),
    ):
        forged = replace(pub.job, attempt=attempt)
        with pytest.raises(OrchestrationError):
            service.jobs.renew(forged, 60)
    clock.now = "2026-11-10T10:00:00Z"
    with pytest.raises(OrchestrationError):
        service.jobs.succeed(pub)
    clock.now = "2026-11-10T10:00:12Z"
    with pytest.raises(OrchestrationError):
        service.jobs.succeed(pub)
    assert service.jobs.get(pub.job.job_id).state == "running"


def test_database_disappearance_is_integrity_not_new_empty_history(
    tmp_path: Path,
) -> None:
    service, _, job = claimed(tmp_path)
    assert isinstance(service.jobs, SQLiteJobs)
    path = service.jobs.path
    path.unlink()
    with pytest.raises(ArchiveIntegrityError):
        service.jobs.get(job.job_id)
    with pytest.raises(ArchiveIntegrityError):
        SQLiteJobs(path)
    assert not path.exists()


def test_operational_reason_read_has_one_snapshot_during_heartbeat(
    tmp_path: Path,
) -> None:
    from collections.abc import Iterator
    from contextlib import contextmanager
    from threading import Event

    service, clock, owner = claimed(tmp_path)
    assert isinstance(service.jobs, SQLiteJobs)
    paused, resume = Event(), Event()

    class PausedReader(SQLiteJobs):
        @contextmanager
        def _connection(self) -> Iterator[sqlite3.Connection]:
            with super()._connection() as connection:

                def trace(statement: str) -> None:
                    if statement.startswith("SELECT body,fence FROM attempts"):
                        paused.set()
                        assert resume.wait(5)

                connection.set_trace_callback(trace)
                yield connection

    reader = PausedReader(service.jobs.path, clock=clock)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(reader.reason, owner.job_id)
        assert paused.wait(5)
        clock.now = ENDED
        service.jobs.renew(owner, 60)
        resume.set()
        assert future.result(timeout=5) is None

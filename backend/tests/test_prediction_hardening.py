"""Independent-review regressions, using actual storage and synchronized races."""

import asyncio
import os
import sqlite3
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from dataclasses import replace
from pathlib import Path
from threading import Barrier, Event

import pytest
from fastapi.testclient import TestClient
from orchestration_examples import ManualClock, bundle_for, service_for, submit
from prediction_examples import ENDED, STARTED
from test_prediction_durable import claimed
from test_prediction_http import BODY
from test_prediction_outputs import predicted_example, publish, rebound_spec
from test_variant_storage import create

from neurofold.adapters.prediction_archive import PredictionArchive
from neurofold.adapters.prediction_sqlite import SQLiteJobs
from neurofold.api.configuration import Settings
from neurofold.api.execution import BlockingExecutor
from neurofold.api.main import create_app
from neurofold.application.prediction_worker import PredictionWorker
from neurofold.application.variants import VariantService
from neurofold.core.errors import ArchiveIntegrityError
from neurofold.core.orchestration import OrchestrationError
from neurofold.core.prediction_base import PredictionError
from neurofold.core.prediction_bundle import MAX_BUNDLE_BYTES
from neurofold.core.prediction_jobs import PredictionJob
from neurofold.core.provenance import EvidenceKind


@pytest.mark.parametrize(
    "damage",
    ["missing", "empty", "truncated", "version", "table", "trigger", "index", "marker"],
)
def test_established_database_never_initializes_away_history(
    tmp_path: Path, damage: str
) -> None:
    service, _, _ = claimed(tmp_path)
    assert isinstance(service.jobs, SQLiteJobs)
    path = service.jobs.path
    if damage == "missing":
        path.unlink()
    elif damage == "empty":
        path.write_bytes(b"")
    elif damage == "truncated":
        path.write_bytes(path.read_bytes()[:128])
    elif damage == "marker":
        path.with_suffix(".identity").write_bytes(b"invalid")
    else:
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute(
                {
                    "version": "PRAGMA user_version=0",
                    "table": "DROP TABLE idempotency",
                    "trigger": "DROP TRIGGER immutable_registration_delete",
                    "index": "CREATE INDEX unexpected ON jobs(state)",
                }[damage]
            )
    before = path.read_bytes() if path.exists() else None
    with pytest.raises(ArchiveIntegrityError):
        SQLiteJobs(path)
    assert (path.read_bytes() if path.exists() else None) == before
    assert path.with_suffix(".identity").exists()


def test_empty_unmarked_file_is_not_a_fresh_database(tmp_path: Path) -> None:
    path = tmp_path / "jobs.sqlite3"
    path.touch()
    with pytest.raises(ArchiveIntegrityError):
        SQLiteJobs(path)
    assert path.read_bytes() == b""


def test_fresh_concurrent_initialization_and_idempotency(tmp_path: Path) -> None:
    barrier = Barrier(8)
    path = tmp_path / "jobs.sqlite3"

    def initialize(_: int) -> SQLiteJobs:
        barrier.wait(5)
        return SQLiteJobs(path)

    with ThreadPoolExecutor(8) as pool:
        repositories = list(pool.map(initialize, range(8)))
    spec = claimed(tmp_path / "fixture")[2].spec
    ids = {
        repository.submit(spec, "same", None, available=True).job_id
        for repository in repositories
    }
    assert len(ids) == 1


def test_v1_migration_preserves_all_job_bytes(tmp_path: Path) -> None:
    service, _, owner = claimed(tmp_path)
    assert isinstance(service.jobs, SQLiteJobs)
    old = service.jobs.finish(owner, "TIMEOUT", terminated=True)
    with closing(sqlite3.connect(service.jobs.path)) as connection, connection:
        for name in ("immutable_failure_update", "immutable_failure_delete"):
            connection.execute("DROP TRIGGER " + name)
        connection.execute("DROP TABLE failures")
        connection.execute("DROP TABLE legacy_failures")
        connection.execute("PRAGMA user_version=1")
    reopened = SQLiteJobs(service.jobs.path)
    assert reopened.get(owner.job_id).to_json() == old.to_json()
    assert reopened.reason(owner.job_id) == "TIMEOUT"
    with pytest.raises(OrchestrationError, match="JOB_CONFLICT"):
        reopened.failure(owner.job_id)  # No invented cause/capture for historical jobs.


@pytest.mark.parametrize("split", ["attempt", "reason"])
def test_consistent_snapshot_during_concurrent_write(
    tmp_path: Path, split: str
) -> None:
    service, clock, owner = claimed(tmp_path)
    assert isinstance(service.jobs, SQLiteJobs)
    paused, resume = Event(), Event()

    class PausedReader(SQLiteJobs):
        @contextmanager
        def _connection(self) -> Iterator[sqlite3.Connection]:
            with super()._connection() as connection:

                def trace(statement: str) -> None:
                    target = (
                        "SELECT body,fence FROM attempts"
                        if split == "attempt"
                        else "SELECT reason FROM jobs"
                    )
                    if statement.startswith(target):
                        paused.set()
                        assert resume.wait(5)

                if self.initialized:
                    connection.set_trace_callback(trace)
                yield connection

    reader = PausedReader(service.jobs.path, clock=clock)
    with ThreadPoolExecutor(1) as pool:
        operation = reader.get if split == "attempt" else reader.snapshot
        future = pool.submit(operation, owner.job_id)
        try:
            assert paused.wait(5)
            clock.now = ENDED
            if split == "attempt":
                service.jobs.renew(owner, 60)
            else:
                service.jobs.finish(owner, "TIMEOUT", terminated=True)
        finally:
            resume.set()
        assert future.result(5) == (owner if split == "attempt" else (owner, None))


def test_live_recovery_cancelling_capacity_and_retry_parent(tmp_path: Path) -> None:
    service, clock, owner = claimed(tmp_path)
    clock.now = ENDED
    assert service.jobs.recover() == 0
    assert service.jobs.get(owner.job_id) == owner
    second = submit(service, "second")
    cancelling = service.cancel(owner.job_id)
    assert service.jobs.claim("worker-2", 60) is None
    assert service.jobs.get(second.job_id).state == "queued"
    failed = service.jobs.finish(cancelling, "WORKER_LOST", terminated=False)
    with pytest.raises(OrchestrationError, match="IDEMPOTENCY_CONFLICT"):
        submit(service, "key-1", retry=failed.job_id)


def test_profile_evidence_cannot_be_relabeled() -> None:
    example = predicted_example()
    spec = replace(
        example.job.spec,
        profile=replace(example.job.spec.profile, evidence=EvidenceKind.SYNTHETIC),
    )
    with pytest.raises(PredictionError):
        publish(rebound_spec(example, spec))


def test_variant_publication_and_repeated_local_outputs_survive_reopen(
    tmp_path: Path,
) -> None:
    import base64

    from neurofold.core.canonical import sha256_bytes
    from neurofold.core.provenance import ContentReference

    service = service_for(tmp_path, ManualClock(STARTED))
    variant = create(VariantService(service.references, service.variants)).definition
    assert isinstance(service.jobs, SQLiteJobs)
    structures, mapping_ids, sample_ids = [], [], []
    for index, variant_id in enumerate([None, variant.variant_id, None]):
        queued = submit(service, f"key-{index}", variant=variant_id)
        owner = service.jobs.claim("worker", 60)
        assert owner is not None
        bundle = bundle_for(owner)  # Every job proposes structure-1/confidence-1.
        expected_bytes = b"authored synthetic structure placeholder\n"
        if index == 1:
            # A different job reuses the exact same local name for different bytes.
            expected_bytes = b"a different authored synthetic structure\n"
            sample = bundle.result.samples[0]
            identity = sample.structure.record_id
            content_hash = replace(
                sample.structure.content_hash, sha256=sha256_bytes(expected_bytes)
            )
            structure = replace(sample.structure, content_hash=content_hash)
            mapping = replace(sample.mapping, structure=structure)
            raw = tuple(
                structure if r.record_id == identity else r
                for r in sample.raw_artifacts
            )
            sample = replace(
                sample,
                structure=structure,
                mapping=mapping,
                raw_artifacts=raw,
                confidence=tuple(
                    replace(
                        c,
                        mapping=ContentReference(
                            record_id=mapping.mapping_id,
                            content_hash=mapping.content_hash,
                        ),
                    )
                    if c.mapping
                    else c
                    for c in sample.confidence
                ),
            )
            artifacts = tuple(
                replace(a, content_hash=content_hash, byte_size=len(expected_bytes))
                if a.artifact_id == identity
                else a
                for a in bundle.manifest.artifacts
            )
            manifest = replace(
                bundle.manifest,
                samples=(sample,),
                raw_artifacts=raw,
                artifacts=artifacts,
            )
            result = replace(
                bundle.result,
                samples=manifest.samples,
                raw_artifacts=raw,
                manifest=ContentReference(
                    record_id=manifest.manifest_id, content_hash=manifest.content_hash
                ),
            )
            staged = tuple(
                replace(
                    a,
                    descriptor=replace(
                        a.descriptor,
                        content_hash=content_hash,
                        byte_size=len(expected_bytes),
                    ),
                    base64_bytes=base64.b64encode(expected_bytes).decode("ascii"),
                )
                if a.descriptor.artifact_id == identity
                else a
                for a in bundle.artifacts
            )
            bundle = replace(bundle, result=result, manifest=manifest, artifacts=staged)
        succeeded = service.publish(owner, bundle, owner)
        reopened = service_for(tmp_path, ManualClock(STARTED))
        assert reopened.get(queued.job_id) == succeeded
        result, manifest = reopened.records(queued.job_id)
        structure_id = result.samples[0].structure.record_id
        assert reopened.archive.artifact(succeeded, structure_id)[0] == expected_bytes
        structures.append(structure_id)
        mapping_ids.append(result.samples[0].mapping.mapping_id)
        sample_ids.append(result.samples[0].sample_id)
        assert result.samples == manifest.samples
        if variant_id:
            assert result.samples[0].mapping.sequence_hash == variant.sequence_hash
            assert ("variant", variant_id) in {
                (k, i) for k, i, _, _ in service.jobs.graph(queued.job_id)
            }
            assert manifest.spec.reference.record_id == variant.reference_id
    assert len(set(structures)) == len(set(mapping_ids)) == len(set(sample_ids)) == 3


@pytest.mark.parametrize(
    "cause",
    [
        "TIMEOUT",
        "WORKER_LOST",
        "CHILD_FAILED",
        "INVALID_OUTPUT",
        "PUBLICATION_FAILED",
        "SHUTDOWN",
        "SUPERVISION_FAILED",
    ],
)
def test_failure_extension_is_truthful_checksummed_and_explicitly_retryable(
    tmp_path: Path, cause: str
) -> None:
    from neurofold.core.prediction_failure import OperationalFailure

    service, _, owner = claimed(tmp_path)
    # Strict codec keeps the cause vocabulary closed without a typing cast.
    record = OperationalFailure.from_dict(
        {
            "schema_version": "neurofold-prediction-failure/1",
            "job": {
                "record_id": owner.job_id,
                "content_hash": owner.content_hash.to_dict(),
            },
            "attempt_id": owner.attempt.attempt_id,  # type: ignore[union-attr]
            "cause": cause,
            "ended_at": ENDED,
            "retry_policy": "explicit-new-job-same-spec",
        }
    )
    failed = service.jobs.finish(owner, record.cause, terminated=True)
    failure = service.jobs.failure(owner.job_id)
    assert failure.cause == cause and failure.job.content_hash == failed.content_hash
    assert failure.retry_policy == "explicit-new-job-same-spec"
    assert submit(service, "retry", retry=failed.job_id).state == "queued"
    with TestClient(create_app(prediction_factory=lambda: service)) as client:
        response = client.get(f"/v1/prediction-jobs/{owner.job_id}/failure")
        assert response.status_code == 200
        assert OperationalFailure.from_dict(response.json()) == failure
    assert isinstance(service.jobs, SQLiteJobs)
    with closing(sqlite3.connect(service.jobs.path)) as connection, connection:
        connection.execute(
            "UPDATE jobs SET reason='SHUTDOWN' WHERE id=?", (owner.job_id,)
        )
    if cause != "SHUTDOWN":
        with pytest.raises(ArchiveIntegrityError):
            service.snapshot(owner.job_id)


class FinishedChild:
    def poll(self) -> int:
        return 0

    def reap(self) -> int:
        return 0

    def terminate_and_reap(self) -> None:
        pass


@pytest.mark.parametrize(
    "kind", ["fifo", "directory", "symlink", "device", "oversized"]
)
def test_special_child_output_never_blocks_or_reaches_decoder(
    tmp_path: Path, kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from neurofold.core.prediction_bundle import ChildBundle

    service = service_for(tmp_path, ManualClock())
    queued = submit(service)
    decoded = Event()
    original = ChildBundle.from_json
    reads = Event()
    original_read = os.read

    def read(descriptor: int, size: int) -> bytes:
        reads.set()
        return original_read(descriptor, size)

    monkeypatch.setattr(os, "read", read)

    def spy(data: bytes) -> ChildBundle:
        decoded.set()
        return original(data)

    monkeypatch.setattr(ChildBundle, "from_json", spy)

    class Launcher:
        def launch(self, directory: Path, job: PredictionJob) -> FinishedChild:
            target = directory / "bundle.json"
            if kind == "fifo":
                os.mkfifo(target)
            elif kind == "directory":
                target.mkdir()
            elif kind == "symlink":
                outside = tmp_path / "outside.json"
                outside.write_bytes(bundle_for(job).to_json())
                target.symlink_to(outside)
            elif kind == "device":
                # Exercise fstat's device classification without requiring mknod.
                original_open = os.open

                def open_device(
                    path: str | Path,
                    flags: int,
                    *args: object,
                    dir_fd: int | None = None,
                ) -> int:
                    return original_open(
                        "/dev/zero" if path == "bundle.json" else path,
                        flags,
                        dir_fd=dir_fd,
                    )

                monkeypatch.setattr(os, "open", open_device)
            else:
                with target.open("wb") as stream:
                    stream.truncate(MAX_BUNDLE_BYTES + 1)
            return FinishedChild()

    worker = PredictionWorker(service, Launcher(), tmp_path / "staging")
    with ThreadPoolExecutor(1) as pool:
        assert pool.submit(worker.once).result(3)
    assert not decoded.is_set()
    assert not reads.is_set()
    assert service.jobs.reason(queued.job_id) == "INVALID_OUTPUT"


def test_cancel_between_claim_and_launch_does_not_execute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = service_for(tmp_path, ManualClock())
    queued = submit(service)
    staged = service.jobs.stage

    def cancel_after_stage(owner: PredictionJob, stage: str) -> PredictionJob:
        result = staged(owner, stage)  # type: ignore[arg-type]
        service.cancel(owner.job_id)
        return result

    monkeypatch.setattr(service.jobs, "stage", cancel_after_stage)

    launched = Event()

    class NoLaunch:
        def launch(self, directory: Path, job: PredictionJob) -> FinishedChild:
            launched.set()
            return FinishedChild()

    worker = PredictionWorker(service, NoLaunch(), tmp_path / "staging")
    assert worker.once()
    assert not launched.is_set()
    retained = service.get(queued.job_id)
    assert retained.state == "cancelled" and retained.termination_confirmed


@pytest.mark.parametrize("action", ["release", "shutdown"])
def test_worker_recovers_from_sqlite_contention_and_stops_responsively(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    service = service_for(tmp_path, ManualClock())
    assert isinstance(service.jobs, SQLiteJobs)
    worker = PredictionWorker(service, object(), tmp_path / "staging")  # type: ignore[arg-type]
    import logging

    attempted, released = Event(), Event()
    monkeypatch.setattr(
        logging.getLogger("neurofold.application.prediction_worker"),
        "warning",
        lambda *args: attempted.set(),
    )
    original = service.jobs.recover

    def recover() -> int:
        value = original()
        released.set()
        return value

    monkeypatch.setattr(service.jobs, "recover", recover)
    with closing(sqlite3.connect(service.jobs.path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(worker.run)
            try:
                assert attempted.wait(10)
                if action == "release":
                    connection.rollback()
                    assert released.wait(5)
            finally:
                worker.stop.set()
            future.result(3)
    assert worker.blocked_reason is None


@pytest.mark.parametrize("state", ["queued", "running"])
def test_corrupt_queue_blocks_execution_preserves_evidence_and_stays_alive(
    tmp_path: Path, state: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = service_for(tmp_path, ManualClock())
    queued = submit(service)
    if state == "running":
        service.jobs.claim("old-worker", 60)
    assert isinstance(service.jobs, SQLiteJobs)
    with closing(sqlite3.connect(service.jobs.path)) as connection, connection:
        connection.execute("UPDATE jobs SET body=?", (b"corrupt-evidence",))
    observed = Event()
    original = service.jobs._get

    def get(connection: sqlite3.Connection, identity: str) -> PredictionJob:
        try:
            return original(connection, identity)
        finally:
            observed.set()

    monkeypatch.setattr(service.jobs, "_get", get)
    worker = PredictionWorker(service, object(), tmp_path / "staging")  # type: ignore[arg-type]
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(worker.run)
        try:
            assert observed.wait(3)
            # Synchronize on the worker's stop wait after the error is audited.
            assert not future.done()
        finally:
            worker.stop.set()
        future.result(3)
    assert worker.blocked_reason == "ARCHIVE_INTEGRITY"
    with closing(sqlite3.connect(service.jobs.path)) as connection:
        assert connection.execute("SELECT id,body FROM jobs").fetchall() == [
            (queued.job_id, b"corrupt-evidence")
        ]


def test_retained_reads_ignore_publication_lock_and_recover_api_capacity(
    tmp_path: Path,
) -> None:
    service, _, owner = claimed(tmp_path)
    succeeded = service.publish(owner, bundle_for(owner), owner)
    assert isinstance(service.archive, PredictionArchive)
    settings = Settings(archive_root=tmp_path / "data", workers=1, operation_seconds=10)
    with TestClient(
        create_app(settings=settings, prediction_factory=lambda: service)
    ) as client:
        with service.archive.lock():
            # A blocked flock formerly timed out and permanently consumed this slot.
            for _ in range(3):
                assert (
                    client.get(f"/v1/prediction-jobs/{succeeded.job_id}").status_code
                    == 200
                )
            # An absent retained biological record still needs the shared executor.
            assert client.get("/v1/references/absent").status_code == 404
            assert client.get("/health").status_code == 200


def test_cancelled_archive_awaiter_eventually_releases_capacity(tmp_path: Path) -> None:
    service, _, owner = claimed(tmp_path)
    succeeded = service.publish(owner, bundle_for(owner), owner)
    assert isinstance(service.archive, PredictionArchive)

    async def scenario() -> None:
        executor = BlockingExecutor(1, 1)
        started, release = Event(), Event()

        def read() -> PredictionJob:
            started.set()
            assert release.wait(3)
            return service.get(succeeded.job_id)

        try:
            task = asyncio.create_task(executor.run(read))
            assert await asyncio.to_thread(started.wait, 3)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            release.set()
            await executor.close()
            assert executor.slots.acquire(blocking=False)
            executor.slots.release()
        finally:
            release.set()

    with service.archive.lock():
        asyncio.run(scenario())


def test_bad_submission_configuration_preserves_retained_reads_and_cancel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from neurofold.api.composition import compose_predictions

    settings = Settings(archive_root=tmp_path / "data")
    monkeypatch.setenv("NEUROFOLD_CODE_IDENTITY", "malformed")
    service = compose_predictions(settings)
    # Populate this repository using an already resolved synthetic spec.
    spec = claimed(tmp_path / "spec")[2].spec
    queued = service.jobs.submit(spec, "retained", None, available=True)
    with TestClient(create_app(settings=settings)) as client:
        path = f"/v1/prediction-jobs/{queued.job_id}"
        assert client.get(path).status_code == 200
        assert client.post(path + "/cancel", json={}).status_code == 200
        response = client.post(
            "/v1/prediction-jobs", json=BODY, headers={"Idempotency-Key": "new"}
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "CODE_IDENTITY_REQUIRED"
        assert response.json()["error"]["details"] == {}


@pytest.mark.parametrize(
    "code,status,retryable",
    [
        ("PROFILE_UNAVAILABLE", 503, False),
        ("CODE_IDENTITY_REQUIRED", 503, False),
        ("PREDICTION_BUSY", 503, True),
        ("PREDICTION_QUEUE_FULL", 429, True),
    ],
)
def test_prediction_rejections_have_precise_retry_semantics(
    code: str, status: int, retryable: bool
) -> None:
    import json

    from neurofold.api.errors import translate

    # Construct only from the closed vocabulary, avoiding arbitrary exception text.
    for allowed in (
        "PROFILE_UNAVAILABLE",
        "CODE_IDENTITY_REQUIRED",
        "PREDICTION_BUSY",
        "PREDICTION_QUEUE_FULL",
    ):
        if code == allowed:
            response = translate(OrchestrationError(allowed), "request", mutating=True)
            error = json.loads(bytes(response.body))["error"]
            assert response.status_code == status
            assert error["retryable"] is retryable
            assert error["details"] == {}
            assert ("Retry-After" in response.headers) is retryable


def test_uncertain_commit_reports_recovery_and_preserves_idempotency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from neurofold.api.errors import translate

    service = service_for(tmp_path, ManualClock())
    assert isinstance(service.jobs, SQLiteJobs)
    jobs = service.jobs
    original = jobs._connection

    class CommitFailure(sqlite3.Connection):
        def commit(self) -> None:
            super().commit()
            raise sqlite3.OperationalError("authored failure after commit")

    @contextmanager
    def connection_with_failure() -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(
            jobs.path, isolation_level=None, factory=CommitFailure
        )
        try:
            yield connection
        finally:
            connection.close()

    monkeypatch.setattr(jobs, "_connection", connection_with_failure)
    with pytest.raises(
        OrchestrationError, match="PREDICTION_MUTATION_UNCERTAIN"
    ) as error:
        submit(service)
    response = translate(error.value, "request", mutating=True)
    assert response.status_code == 503 and "Retry-After" not in response.headers
    assert json.loads(bytes(response.body))["error"]["details"][
        "publication_may_complete"
    ]
    monkeypatch.setattr(jobs, "_connection", original)
    first = submit(service)
    assert submit(service).job_id == first.job_id


def test_publication_reserves_live_ownership_across_slow_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from neurofold.adapters.prediction_sqlite import after
    from neurofold.core.orchestration import Publication

    clock = ManualClock(STARTED)
    service = service_for(tmp_path, clock)
    queued = submit(service)
    assert isinstance(service.archive, PredictionArchive)
    register = service.archive.register
    observed = Event()

    def slow_register(*args: object, **kwargs: object) -> Publication:
        clock.now = after(STARTED, 3)
        assert service.jobs.recover() == 0
        observed.set()
        return register(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(service.archive, "register", slow_register)

    class Launcher:
        def launch(self, directory: Path, job: PredictionJob) -> FinishedChild:
            # Test publication/lease ownership independently of real child startup.
            (directory / "bundle.json").write_bytes(bundle_for(job).to_json())
            return FinishedChild()

    worker = PredictionWorker(
        service,
        Launcher(),
        tmp_path / "staging",
        lease_seconds=2,
        heartbeat_seconds=0.2,
    )
    assert worker.once() and observed.is_set()
    assert service.get(queued.job_id).state == "succeeded"


@pytest.mark.parametrize("interrupt", ["shutdown", "deadline"])
def test_publication_interrupts_leave_no_success_and_truthful_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interrupt: str
) -> None:
    from test_prediction_worker import ControlledLauncher

    from neurofold.adapters.prediction_sqlite import after

    clock = ManualClock(STARTED)
    service = service_for(tmp_path, clock)
    queued = submit(service)
    assert isinstance(service.archive, PredictionArchive)
    worker = PredictionWorker(service, ControlledLauncher(), tmp_path / "staging")
    original = service.archive.store._publish
    observed = Event()

    def interrupted(kind: str, identity: str, data: bytes) -> bool:
        result = original(kind, identity, data)
        observed.set()
        if interrupt == "shutdown":
            worker.stop.set()
        else:
            clock.now = after(STARTED, service.profiles[0].limits.max_seconds)
        return result

    monkeypatch.setattr(service.archive.store, "_publish", interrupted)
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).parent.resolve()))
    assert worker.once() and observed.is_set()
    assert service.get(queued.job_id).state == "failed"
    assert service.jobs.failure(queued.job_id).cause == (
        "SHUTDOWN" if interrupt == "shutdown" else "TIMEOUT"
    )
    assert list(
        service.archive.store.root.glob("artifact-*")
    )  # Orphans remain evidence.


def test_multisample_local_filenames_have_owned_identities(tmp_path: Path) -> None:
    from neurofold.core.provenance import ContentReference

    service = service_for(tmp_path, ManualClock(STARTED))
    service.submit(key="multiple", **(BODY | {"parameters": {"samples": 2}}))
    owner = service.jobs.claim("worker", 60)
    assert owner is not None
    bundle = bundle_for(owner)
    first = bundle.result.samples[0]
    mapping = replace(
        first.mapping, mapping_id="sample-2:mapping", sample_id="sample-2"
    )
    second = replace(
        first,
        sample_id=mapping.sample_id,
        mapping=mapping,
        returned_rank=2,
        confidence=tuple(
            replace(
                c,
                mapping=ContentReference(
                    record_id=mapping.mapping_id, content_hash=mapping.content_hash
                ),
            )
            if c.mapping
            else c
            for c in first.confidence
        ),
    )
    # A local filename may identify the same registered bytes in multiple samples.
    # Distinct bytes require distinct logical artifact IDs, never a filename alone.
    manifest = replace(
        bundle.manifest,
        samples=(first, second),
        returned_sample_ids=(first.sample_id, second.sample_id),
    )
    result = replace(
        bundle.result,
        samples=manifest.samples,
        manifest=ContentReference(
            record_id=manifest.manifest_id, content_hash=manifest.content_hash
        ),
    )
    service.publish(owner, replace(bundle, result=result, manifest=manifest), owner)
    retained, _ = service.records(owner.job_id)
    assert len({s.sample_id for s in retained.samples}) == 2
    assert len({s.mapping.mapping_id for s in retained.samples}) == 2
    assert retained.samples[0].structure == retained.samples[1].structure


def test_symlinked_prediction_root_is_server_configuration_error(
    tmp_path: Path,
) -> None:
    real = tmp_path / "real-data"
    real.mkdir()
    link = tmp_path / "data"
    link.symlink_to(real, target_is_directory=True)
    with TestClient(create_app(settings=Settings(archive_root=link))) as client:
        for path in ("/v1/prediction-jobs/absent", "/v1/references/absent"):
            response = client.get(path)
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "CONFIGURATION_ERROR"
        assert client.get("/health").status_code == 200


def test_queue_admission_is_429_without_uncertain_mutation(tmp_path: Path) -> None:
    service = service_for(tmp_path, ManualClock())
    assert isinstance(service.jobs, SQLiteJobs)
    service.jobs.max_queued = 1
    submit(service)
    with TestClient(create_app(prediction_factory=lambda: service)) as client:
        response = client.post(
            "/v1/prediction-jobs", json=BODY, headers={"Idempotency-Key": "full"}
        )
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "1"
        assert response.json()["error"]["retryable"]
        assert response.json()["error"]["details"] == {}


def test_processes_initialize_the_same_fresh_database(tmp_path: Path) -> None:
    import subprocess
    import sys

    path = tmp_path / "jobs.sqlite3"
    script = """
import sys
from pathlib import Path
from neurofold.adapters.prediction_sqlite import SQLiteJobs
sys.stdin.buffer.read(1)
SQLiteJobs(Path(sys.argv[1]))
print('initialized')
"""
    children = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(2)
    ]
    try:
        for child in children:
            assert child.stdin is not None
            child.stdin.write(b"x")
            child.stdin.flush()
        for child in children:
            output, error = child.communicate(timeout=10)
            assert child.returncode == 0, error
            assert output.strip() == b"initialized"
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait()
    SQLiteJobs(path)


def test_http_status_keeps_job_and_failure_in_the_same_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, clock, owner = claimed(tmp_path)
    assert isinstance(service.jobs, SQLiteJobs)
    read_ready, release = Event(), Event()
    original = service.jobs._get

    def pause_after_job(connection: sqlite3.Connection, job_id: str) -> PredictionJob:
        result = original(connection, job_id)
        if not read_ready.is_set():
            read_ready.set()
            assert release.wait(10)
        return result

    monkeypatch.setattr(service.jobs, "_get", pause_after_job)
    with TestClient(create_app(prediction_factory=lambda: service)) as client:
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(client.get, f"/v1/prediction-jobs/{owner.job_id}")
            try:
                assert read_ready.wait(10)
                clock.now = ENDED
                service.jobs.finish(owner, "TIMEOUT", terminated=True)
            finally:
                release.set()
            response = future.result(10)
    assert response.status_code == 200
    assert response.json()["job"]["state"] == "running"
    assert response.json()["operational_failure"] is None


@pytest.mark.parametrize("phase", ["composition", "reference", "availability"])
def test_pre_submission_io_failure_never_claims_job_mutation_uncertainty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    settings = Settings(archive_root=tmp_path / "data/production")
    service = service_for(tmp_path, ManualClock())

    def unavailable(*args: object, **kwargs: object) -> None:
        raise PermissionError("authored failure before job submission")

    if phase == "composition":
        monkeypatch.setattr("neurofold.api.composition.FilesystemStore", unavailable)
        app = create_app(settings=settings)
    else:
        if phase == "reference":
            monkeypatch.setattr(service.references, "get", unavailable)
        else:
            monkeypatch.setattr(service, "worker_available", unavailable)
        app = create_app(prediction_factory=lambda: service)
    with TestClient(app) as client:
        response = client.post(
            "/v1/prediction-jobs", json=BODY, headers={"Idempotency-Key": "no-write"}
        )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PREDICTION_UNAVAILABLE"
    assert response.json()["error"]["details"] == {}
    if phase == "composition":
        assert not (settings.archive_root / "predictions/jobs.sqlite3").exists()
    else:
        assert isinstance(service.jobs, SQLiteJobs)
        with closing(sqlite3.connect(service.jobs.path)) as connection:
            assert connection.execute("SELECT count(*) FROM jobs").fetchone() == (0,)


@pytest.mark.parametrize("case", ["ownership", "evidence", "write"])
def test_semantic_child_rejection_is_distinct_from_publication_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    from neurofold.core.provenance import ContentReference

    service = service_for(tmp_path, ManualClock(STARTED))
    queued = submit(service)
    assert isinstance(service.archive, PredictionArchive)
    if case == "write":

        def fail(kind: str, identity: str, data: bytes) -> bool:
            raise OSError("authored immutable-publication failure")

        monkeypatch.setattr(service.archive.store, "_publish", fail)

    class Launcher:
        def launch(self, directory: Path, job: PredictionJob) -> FinishedChild:
            bundle = bundle_for(job)
            if case == "ownership":
                result = replace(
                    bundle.result,
                    manifest=replace(
                        bundle.result.manifest,
                        content_hash=replace(
                            bundle.result.manifest.content_hash, sha256="0" * 64
                        ),
                    ),
                )
                bundle = replace(bundle, result=result)
            elif case == "evidence":
                manifest = replace(bundle.manifest, evidence=EvidenceKind.PREDICTED)
                result = replace(
                    bundle.result,
                    manifest=ContentReference(
                        record_id=manifest.manifest_id,
                        content_hash=manifest.content_hash,
                    ),
                )
                bundle = replace(bundle, manifest=manifest, result=result)
            (directory / "bundle.json").write_bytes(bundle.to_json())
            return FinishedChild()

    assert PredictionWorker(service, Launcher(), tmp_path / "staging").once()
    assert service.get(queued.job_id).state == "failed"
    assert service.jobs.failure(queued.job_id).cause == (
        "PUBLICATION_FAILED" if case == "write" else "INVALID_OUTPUT"
    )

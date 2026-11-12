"""Focused cleanup closure: real helper exits, outcome contention and ownership."""

import json
import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Event
from typing import Any

import pytest
from orchestration_examples import ManualClock, bundle_for, service_for, submit
from test_prediction_durable import claimed
from test_prediction_hardening import FinishedChild
from test_prediction_process import cleanup, exited_unreaped
from test_prediction_worker import ControlledLauncher

import neurofold.adapters.prediction_process as process_adapter
from neurofold.adapters.prediction_process import ProcessChild, ProcessLauncher
from neurofold.adapters.prediction_sqlite import SQLiteJobs
from neurofold.application.prediction_worker import PredictionWorker
from neurofold.core.orchestration import LaunchCleanupError, OrchestrationError
from neurofold.core.prediction_failure import FailureReason
from neurofold.core.prediction_jobs import PredictionJob


@pytest.mark.skipif(sys.platform != "darwin", reason="Darwin exiting-helper EPERM")
@pytest.mark.parametrize("attempt", range(10))
def test_real_exiting_helper_publishes_without_blocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, attempt: int
) -> None:
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).parent.resolve()))
    service = service_for(tmp_path, ManualClock())
    queued = submit(service)

    class HelperLauncher(ProcessLauncher):
        child: ProcessChild | None = None
        gate = -1
        armed = False

        def launch(self, directory: Path, job: PredictionJob) -> ProcessChild:
            (directory / "proposal.json").write_bytes(bundle_for(job).to_json())
            os.mkfifo(directory / "go.fifo")
            self.gate = os.open(directory / "go.fifo", os.O_RDWR | os.O_NONBLOCK)
            self.child = super().launch(directory, job)
            self.armed = True
            return self.child

    launcher = HelperLauncher("orchestration_helper_child", grace=0.1)
    original = service.jobs.get

    def release_on_poll(job_id: str) -> PredictionJob:
        value = original(job_id)
        if launcher.armed:
            launcher.armed = False
            assert launcher.child is not None
            os.write(launcher.gate, b"x")
            exited_unreaped(launcher.child.process)
        return value

    monkeypatch.setattr(service.jobs, "get", release_on_poll)
    worker = PredictionWorker(service, launcher, tmp_path / "staging")
    try:
        assert worker.once()
        assert service.get(queued.job_id).state == "succeeded"
        assert worker.blocked_reason is None and not worker.stop.is_set()
        assert worker.exit_code == 0
        assert launcher.child is not None
        assert launcher.child.process.returncode == 0
        assert launcher.child.death_writer == -1
    finally:
        if launcher.gate >= 0:
            os.close(launcher.gate)
        if launcher.child is not None:
            cleanup(launcher.child)


class RefusedChild(FinishedChild):
    process_id = 4242
    process_group_id = 4242

    def terminate_and_reap(self) -> None:
        raise PermissionError("PRIVATE_SEQUENCE_DO_NOT_LOG")


@pytest.mark.parametrize("phase", ["read", "write"])
@pytest.mark.parametrize("action", ["cancel", "shutdown", "timeout"])
def test_cleanup_outcome_retries_real_sqlite_contention_before_stop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    action: str,
    phase: str,
) -> None:
    clock = ManualClock()
    service = service_for(tmp_path, clock)
    queued = submit(service)
    assert isinstance(service.jobs, SQLiteJobs)
    entered, proceed, busy = Event(), Event(), Event()
    finish, get = service.jobs.finish, service.jobs.get

    class GatedRefusal(RefusedChild):
        def terminate_and_reap(self) -> None:
            entered.set()
            assert proceed.wait(10)
            super().terminate_and_reap()

    class Launcher:
        def launch(self, directory: Path, job: PredictionJob) -> GatedRefusal:
            if action == "cancel":
                service.cancel(job.job_id)
            elif action == "shutdown":
                worker.stop.set()
            else:
                clock.now = "2026-11-10T10:00:11Z"
            return GatedRefusal()

    def release_after_busy() -> None:
        # Assert and release on the worker thread before retry can finish.
        if action != "shutdown":
            assert not worker.stop.is_set()
        lock.rollback()
        busy.set()

    def contended_finish(
        job: PredictionJob, reason: FailureReason | None, *, terminated: bool
    ) -> PredictionJob:
        try:
            return finish(job, reason, terminated=terminated)
        except OrchestrationError as exc:
            if exc.code == "PREDICTION_BUSY":
                release_after_busy()
            raise

    def contended_get(job_id: str) -> PredictionJob:
        if phase == "read" and worker.blocked_reason is not None and not busy.is_set():
            release_after_busy()
            raise OrchestrationError("PREDICTION_BUSY")
        return get(job_id)

    monkeypatch.setattr(service.jobs, "get", contended_get)
    monkeypatch.setattr(service.jobs, "finish", contended_finish)
    worker = PredictionWorker(service, Launcher(), tmp_path / "staging")
    with (
        ThreadPoolExecutor(1) as pool,
        closing(sqlite3.connect(service.jobs.path, check_same_thread=False)) as lock,
    ):
        future = pool.submit(worker.once)
        try:
            assert entered.wait(10)
            lock.execute("BEGIN IMMEDIATE")
            proceed.set()
            assert busy.wait(10)
        finally:
            lock.rollback()
            proceed.set()
        assert future.result(10)
    failed = service.get(queued.job_id)
    assert failed.state == "failed" and not failed.termination_confirmed
    assert service.jobs.failure(queued.job_id).cause == "SUPERVISION_FAILED"
    assert worker.blocked_reason == "UNCONFIRMED_CLEANUP"
    assert worker.exit_code == 78 and worker.stop.is_set()
    record = json.loads(worker.block_path.read_bytes())
    assert record["job_id"] == queued.job_id
    assert failed.attempt is not None
    assert record["attempt_id"] == failed.attempt.attempt_id
    assert record["process_id"] == record["process_group_id"] == 4242
    assert worker.block_path.stat().st_mode & 0o777 == 0o600
    assert "PRIVATE_SEQUENCE_DO_NOT_LOG" not in caplog.text
    assert "outcome_recorded=True" in caplog.text
    assert f"job={queued.job_id}" in caplog.text
    assert f"attempt={failed.attempt.attempt_id}" in caplog.text
    assert "pid=4242 pgid=4242" in caplog.text
    second = submit(service, "second")
    reopened = PredictionWorker(service, Launcher(), worker.staging)
    monkeypatch.setattr(
        service.jobs, "recover", lambda: pytest.fail("Block before recovery")
    )
    assert not reopened.once()
    assert reopened.blocked_reason == "UNCONFIRMED_CLEANUP"
    assert reopened.exit_code == 78
    assert service.get(second.job_id).state == "queued"
    worker.stop.clear()
    assert not worker.once()  # Clearing an Event cannot resume the blocked owner.


def test_launch_failure_transfers_unconfirmed_child_to_worker(tmp_path: Path) -> None:
    service = service_for(tmp_path, ManualClock())
    queued = submit(service)

    class Launcher:
        def launch(self, directory: Path, job: PredictionJob) -> RefusedChild:
            service.cancel(job.job_id)
            raise LaunchCleanupError(RefusedChild())

    worker = PredictionWorker(service, Launcher(), tmp_path / "staging")
    assert worker.once()
    retained = service.get(queued.job_id)
    assert retained.state == "failed" and not retained.termination_confirmed
    assert service.jobs.failure(queued.job_id).cause == "SUPERVISION_FAILED"
    assert worker.exit_code == 78 and worker.block_path.exists()


@pytest.mark.parametrize("unconfirmed", [False, True])
def test_base_launcher_owns_process_when_postspawn_close_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, unconfirmed: bool
) -> None:
    _, _, owner = claimed(tmp_path)
    directory = tmp_path / "child"
    directory.mkdir()
    original_popen, original_close = subprocess.Popen, os.close
    children: list[ProcessChild] = []
    reader = -1
    failed = False

    def popen(*args: Any, **kwargs: Any) -> subprocess.Popen[bytes]:
        nonlocal reader
        reader = kwargs["pass_fds"][0]
        return original_popen(*args, **kwargs)

    class ObservedChild(ProcessChild):
        def terminate_and_reap(self) -> None:
            if unconfirmed:
                raise PermissionError("PRIVATE_SEQUENCE_DO_NOT_LOG")
            super().terminate_and_reap()

    def child(
        process: subprocess.Popen[bytes], writer: int, grace: float
    ) -> ProcessChild:
        value = ObservedChild(process, writer, grace)
        children.append(value)
        return value

    def close(fd: int) -> None:
        nonlocal failed
        if fd == reader and not failed:
            failed = True
            original_close(fd)
            raise OSError("Authored post-spawn close error")
        original_close(fd)

    try:
        with monkeypatch.context() as patch:
            patch.setattr(subprocess, "Popen", popen)
            patch.setattr(process_adapter, "ProcessChild", child)
            patch.setattr(os, "close", close)
            if unconfirmed:
                with pytest.raises(LaunchCleanupError) as error:
                    ProcessLauncher(grace=0.1).launch(directory, owner)
                assert error.value.child is children[0]
                assert children[0].death_writer >= 0
            else:
                with pytest.raises(OSError, match="post-spawn close error"):
                    ProcessLauncher(grace=0.1).launch(directory, owner)
                assert children[0].process.returncode is not None
                assert children[0].death_writer == -1
    finally:
        for value in children:
            cleanup(value)


def test_harness_launcher_transfers_failed_startup_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).parent.resolve()))
    _, _, owner = claimed(tmp_path)
    directory = tmp_path / "child"
    directory.mkdir()
    launcher = ControlledLauncher("bad_ready")

    def refuse(child: ProcessChild) -> None:
        raise PermissionError("PRIVATE_SEQUENCE_DO_NOT_LOG")

    try:
        with monkeypatch.context() as patch:
            patch.setattr(ProcessChild, "terminate_and_reap", refuse)
            with pytest.raises(LaunchCleanupError) as error:
                launcher.launch(directory, owner)
            assert error.value.child is launcher.child
    finally:
        if launcher.child is not None:
            cleanup(launcher.child)


@pytest.mark.parametrize("entrypoint", ["production", "controlled"])
def test_blocked_production_entrypoint_exits_unsuccessfully(
    tmp_path: Path, entrypoint: str
) -> None:
    root = tmp_path / "data/archive"
    marker = (
        root
        / ("predictions/staging" if entrypoint == "production" else "staging")
        / "worker-block.json"
    )
    marker.parent.mkdir(parents=True)
    marker.write_bytes(b"partial marker must still prevent resumption")
    result = subprocess.run(
        [sys.executable, "-m", "neurofold.worker"]
        if entrypoint == "production"
        else [
            sys.executable,
            str(
                Path(__file__).resolve().parents[2]
                / "infra/testing/prediction_worker.py"
            ),
        ],
        env=os.environ
        | {
            "NEUROFOLD_ARCHIVE_ROOT": str(root),
            "PYTHONPATH": str(Path(__file__).parent.resolve()),
        },
        capture_output=True,
        text=True,
        timeout=60,  # Hang guard for interpreter/fixture startup under emulation.
    )
    assert result.returncode == 78
    assert "UNCONFIRMED_CLEANUP" in result.stderr
    assert "manual_recovery_required=true" in result.stderr
    assert marker.read_bytes() == b"partial marker must still prevent resumption"


def test_unrecorded_cleanup_remains_blocked_after_retry_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    service = service_for(tmp_path, ManualClock())
    queued = submit(service)

    class Launcher:
        def launch(self, directory: Path, job: PredictionJob) -> RefusedChild:
            service.cancel(job.job_id)
            return RefusedChild()

    def busy(*args: object, **kwargs: object) -> PredictionJob:
        raise OrchestrationError("PREDICTION_BUSY")

    monkeypatch.setattr(service.jobs, "finish", busy)
    worker = PredictionWorker(service, Launcher(), tmp_path / "staging")
    with ThreadPoolExecutor(1) as pool:
        # Hang guard includes loaded scheduling; the recording budget remains 2 s.
        assert pool.submit(worker.once).result(30)
    assert service.get(queued.job_id).state == "cancelling"
    assert worker.block_path.exists() and worker.exit_code == 78
    assert "outcome_recorded=False" in caplog.text
    reopened = PredictionWorker(service, Launcher(), worker.staging)
    assert not reopened.once() and reopened.exit_code == 78

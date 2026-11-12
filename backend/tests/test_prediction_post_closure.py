"""Post-closure regressions: exit contracts, fail-closed markers and fake time."""

import errno
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from orchestration_examples import ManualClock, service_for, submit
from test_prediction_cleanup_closure import RefusedChild
from test_prediction_durable import claimed
from test_prediction_hardening import FinishedChild
from test_prediction_process import assert_reaped, cleanup, exited_unreaped

from neurofold.adapters.prediction_process import ProcessChild
from neurofold.application.prediction_worker import PredictionWorker
from neurofold.core.orchestration import LaunchCleanupError
from neurofold.core.prediction_failure import FailureReason
from neurofold.core.prediction_jobs import PredictionJob

ENTRYPOINT_PROBE = r"""
import os,runpy,sys
from pathlib import Path
from neurofold.adapters.prediction_sqlite import SQLiteJobs
from neurofold.core.errors import ArchiveIntegrityError
root,mode,entry=Path(sys.argv[1]),sys.argv[2],sys.argv[3]
if mode=='startup':
    relative='predictions/jobs.sqlite3' if entry=='production' else 'data/jobs.sqlite3'
    path=root/relative
    jobs=SQLiteJobs(path)
    path.with_suffix('.identity').write_bytes(b'damaged identity')
if mode=='marker':
    relative='predictions/staging' if entry=='production' else 'staging'
    marker=root/relative/'worker-block.json'
    marker.parent.mkdir(parents=True,exist_ok=True)
    marker.write_bytes(b'partial')
original=SQLiteJobs.recover
def recover(self):
    (root/'ready').write_bytes(b'ready')
    if mode=='runtime':
        raise ArchiveIntegrityError('Retained prediction job invalid') from ValueError(
            'PRIVATE_DETAIL_DO_NOT_LOG')
    return original(self)
SQLiteJobs.recover=recover
if entry=='production':
    runpy.run_module('neurofold.worker',run_name='__main__')
else:
    runpy.run_path(sys.argv[4],run_name='__main__')
"""


@pytest.mark.parametrize("entrypoint", ["production", "controlled"])
@pytest.mark.parametrize(
    "mode,code", [("normal", 0), ("runtime", 65), ("startup", 65), ("marker", 78)]
)
def test_entrypoint_exit_contract(
    tmp_path: Path, entrypoint: str, mode: str, code: int
) -> None:
    root = tmp_path / "data/archive"
    root.mkdir(parents=True)
    repo = Path(__file__).resolve().parents[2]
    env = os.environ | {
        "NEUROFOLD_ARCHIVE_ROOT": str(root),
        "PYTHONPATH": os.pathsep.join(
            [str(repo / "backend/tests"), str(repo / "infra/testing")]
        ),
    }
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            ENTRYPOINT_PROBE,
            str(root),
            mode,
            entrypoint,
            str(repo / "infra/testing/prediction_worker.py"),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        if mode in ("normal", "runtime"):
            until = (
                time.monotonic() + 60
            )  # Interpreter-startup hang guard under emulation.
            while not (root / "ready").exists():
                assert process.poll() is None, process.communicate()
                assert time.monotonic() < until, "Worker did not reach recovery"
                time.sleep(0.01)
            process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=60)
        assert process.returncode == code, (stdout, stderr)
        if mode in ("runtime", "startup"):
            assert "ARCHIVE_INTEGRITY" in stderr
            assert "error_type=ArchiveIntegrityError" in stderr
            message = (
                "Retained prediction job invalid"
                if mode == "runtime"
                else "Retained prediction database missing/invalid"
            )
            assert "message=" + message in stderr
            assert (
                "Traceback" not in stderr and "PRIVATE_DETAIL_DO_NOT_LOG" not in stderr
            )
        if mode == "marker":
            assert "UNCONFIRMED_CLEANUP" in stderr
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()


@pytest.mark.parametrize(
    "error",
    [
        PermissionError(errno.EACCES, "PRIVATE"),
        NotADirectoryError(errno.ENOTDIR, "PRIVATE"),
    ],
)
def test_marker_stat_errors_block_before_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: OSError,
) -> None:
    service = service_for(tmp_path, ManualClock())
    worker = PredictionWorker(service, object(), tmp_path / "staging")  # type: ignore[arg-type]
    original = os.lstat

    def denied(path: Any, *args: Any, **kwargs: Any) -> os.stat_result:
        if Path(path) == worker.block_path:
            raise error
        return original(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", denied)
    monkeypatch.setattr(
        service.jobs, "recover", lambda: pytest.fail("Recovery must not run")
    )
    assert worker.once() is False
    assert worker.blocked_reason == "UNCONFIRMED_CLEANUP" and worker.exit_code == 78
    assert errno.errorcode[error.errno or 0] in caplog.text
    assert "PRIVATE" not in caplog.text


@pytest.mark.parametrize("method", ["reap", "terminate_and_reap"])
@pytest.mark.parametrize("ends", [0.003, 0.099, None, 0.101])
def test_group_eperm_fake_clock_boundary(
    monkeypatch: pytest.MonkeyPatch, method: str, ends: float | None
) -> None:
    reader, writer = os.pipe()
    os.close(reader)
    process = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
    child = ProcessChild(process, writer, 0.1)
    denied = PermissionError(errno.EPERM, "original denial")
    now, calls = 0.0, 0

    def clock() -> float:
        return now

    def sleep(seconds: float) -> None:
        nonlocal now
        now = round(now + seconds, 9)

    def killpg(pid: int, value: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise denied
        if ends is None or now < ends:
            raise PermissionError(errno.EPERM, "later denial")
        raise ProcessLookupError()

    try:
        exited_unreaped(process)
        with monkeypatch.context() as patch:
            patch.setattr(os, "killpg", killpg)
            patch.setattr(time, "monotonic", clock)
            patch.setattr(time, "sleep", sleep)
            if ends is None or ends > 0.1:
                with pytest.raises(PermissionError) as error:
                    getattr(child, method)()
                assert error.value is denied
                assert now >= 0.1
            else:
                getattr(child, method)()
                assert ends <= now < 0.1
            assert calls >= 4
        assert_reaped(child, writer)
    finally:
        cleanup(child)


def test_cancel_race_during_cleanup_outcome_is_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _, owner = claimed(tmp_path)
    worker = PredictionWorker(service, object(), tmp_path / "staging")  # type: ignore[arg-type]
    original, calls = service.jobs.finish, 0

    def cancel_first(
        job: PredictionJob, reason: FailureReason | None, *, terminated: bool
    ) -> PredictionJob:
        nonlocal calls
        calls += 1
        if calls == 1:
            service.cancel(job.job_id)
        return original(job, reason, terminated=terminated)

    monkeypatch.setattr(service.jobs, "finish", cancel_first)
    worker._block_cleanup(owner, RefusedChild(), PermissionError("PRIVATE"))
    assert service.get(owner.job_id).state == "failed"
    assert service.jobs.failure(owner.job_id).cause == "SUPERVISION_FAILED"
    assert calls == 2 and worker.exit_code == 78


def test_dangling_marker_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = service_for(tmp_path, ManualClock())
    worker = PredictionWorker(service, object(), tmp_path / "staging")  # type: ignore[arg-type]
    worker.staging.mkdir()
    worker.block_path.symlink_to(tmp_path / "missing-target")
    monkeypatch.setattr(
        service.jobs, "recover", lambda: pytest.fail("Recovery must not run")
    )
    assert worker.once() is False and worker.exit_code == 78


def test_in_memory_block_survives_failed_marker_write_and_event_clear(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _, owner = claimed(tmp_path)
    worker = PredictionWorker(service, object(), tmp_path / "staging")  # type: ignore[arg-type]
    original = os.open

    def no_marker(path: Any, *args: Any, **kwargs: Any) -> int:
        if Path(path) == worker.block_path:
            raise OSError(errno.ENOSPC, "PRIVATE")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", no_marker)
    worker._block_cleanup(owner, RefusedChild(), PermissionError("PRIVATE"))
    assert not worker.block_path.exists()
    worker.stop.clear()
    monkeypatch.setattr(
        service.jobs, "recover", lambda: pytest.fail("Recovery must not run")
    )
    assert not worker.once() and worker.exit_code == 78


def test_transferred_launch_child_can_finish_confirmed_cancel(tmp_path: Path) -> None:
    service = service_for(tmp_path, ManualClock())
    queued = submit(service)

    class Recoverable(FinishedChild):
        calls = 0

        def terminate_and_reap(self) -> None:
            self.calls += 1
            if self.calls == 1:
                raise PermissionError("first cleanup failed")

    child = Recoverable()

    class Launcher:
        def launch(self, directory: Path, job: PredictionJob) -> Recoverable:
            service.cancel(job.job_id)
            try:
                child.terminate_and_reap()
            except PermissionError as exc:
                raise LaunchCleanupError(child) from exc
            return child

    worker = PredictionWorker(service, Launcher(), tmp_path / "staging")
    assert worker.once()
    assert service.get(queued.job_id).state == "cancelled"
    assert service.get(queued.job_id).termination_confirmed
    assert child.calls == 2
    assert worker.blocked_reason is None and not worker.block_path.exists()


def test_outcome_recording_does_not_adopt_foreign_attempt(tmp_path: Path) -> None:
    service, _, owner = claimed(tmp_path)
    assert owner.attempt is not None
    foreign = replace(owner, attempt=replace(owner.attempt, worker_id="other-worker"))
    worker = PredictionWorker(service, object(), tmp_path / "staging")  # type: ignore[arg-type]
    assert worker._record_cleanup_outcome(foreign) is False
    assert service.get(owner.job_id) == owner


def test_recovery_marker_contains_local_reference_time_and_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import socket

    from neurofold.application import prediction_worker as worker_module

    times = iter(["2026-11-12T10:00:00Z", "2026-11-12T10:00:01Z"])
    monkeypatch.setattr(worker_module, "_utc_now", lambda: next(times), raising=False)
    monkeypatch.setattr(socket, "gethostname", lambda: "test-host")
    service = service_for(tmp_path, ManualClock())
    queued = submit(service)

    class Launcher:
        def launch(self, directory: Path, job: PredictionJob) -> RefusedChild:
            service.cancel(job.job_id)
            return RefusedChild()

    worker = PredictionWorker(service, Launcher(), tmp_path / "staging")
    assert worker.once()
    record = json.loads(worker.block_path.read_bytes())
    assert record["created_at"] == "2026-11-12T10:00:01Z"
    assert record["child_launched_at"] == "2026-11-12T10:00:00Z"
    assert record["host_id"] == "test-host"
    assert f"worker_id={worker.worker_id}" in caplog.text
    assert record["job_id"] == queued.job_id
    assert "PRIVATE_SEQUENCE_DO_NOT_LOG" not in worker.block_path.read_text()

"""Harmless real POSIX children, FIFO/event barriers and confirmed reaping."""

import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest
from orchestration_examples import ManualClock, bundle_for, service_for, submit
from prediction_examples import ENDED

from neurofold.adapters.prediction_process import ProcessChild, ProcessLauncher
from neurofold.application.prediction_worker import PredictionWorker
from neurofold.core.orchestration import LaunchCleanupError
from neurofold.core.prediction_jobs import PredictionJob


class ControlledLauncher(ProcessLauncher):
    def __init__(self, mode: str = "copy", *, ready_seconds: float = 30) -> None:
        super().__init__("orchestration_child", grace=0.1)
        self.mode = mode
        self.started = Event()
        self.spawned = Event()
        self.stop = Event()
        self.ready_seconds = ready_seconds
        self.child: ProcessChild | None = None
        self.directory: Path | None = None

    def launch(self, directory: Path, job: PredictionJob) -> ProcessChild:
        (directory / "control.json").write_text(json.dumps({"mode": self.mode}))
        (directory / "proposal.json").write_bytes(bundle_for(job).to_json())
        os.mkfifo(directory / "ready.fifo")
        reader = os.open(directory / "ready.fifo", os.O_RDONLY | os.O_NONBLOCK)
        child = None
        deadline = time.monotonic() + min(
            self.ready_seconds, job.spec.profile.limits.max_seconds
        )
        try:
            try:
                child = super().launch(directory, job)
                self.child, self.directory = child, directory
                self.spawned.set()
                token = b""
                while True:
                    if self.stop.is_set():
                        raise RuntimeError("Controlled child startup interrupted")
                    try:
                        token += os.read(reader, 5 - len(token))
                    except BlockingIOError:
                        pass
                    if token == b"ready":
                        self.started.set()
                        return child
                    if not b"ready".startswith(token):
                        raise RuntimeError("Invalid controlled child readiness signal")
                    if child.poll() is not None:
                        raise RuntimeError("Controlled child exited before readiness")
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Controlled child readiness timed out")
                    self.stop.wait(0.01)
            finally:
                os.close(reader)
        except BaseException:
            if child is not None:
                try:
                    child.terminate_and_reap()
                except Exception as exc:
                    raise LaunchCleanupError(child) from exc
            raise


@pytest.fixture(autouse=True)
def child_imports(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).parent.resolve()))


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("copy", "succeeded"),
        ("crash", "failed"),
        ("missing", "failed"),
        ("malformed", "failed"),
        ("oversized", "failed"),
    ],
)
def test_real_child_output_and_reaping(
    tmp_path: Path, mode: str, expected: str
) -> None:
    clock = ManualClock()
    service = service_for(tmp_path, clock)
    queued = submit(service)
    clock.now = ENDED
    launcher = ControlledLauncher(mode)
    worker = PredictionWorker(service, launcher, tmp_path / "staging")
    assert worker.once()
    assert service.get(queued.job_id).state == expected
    assert launcher.child is not None
    assert launcher.child.process.returncode is not None
    with pytest.raises(ProcessLookupError):
        os.killpg(launcher.child.process.pid, 0)
    if mode == "copy":
        assert service.records(queued.job_id)[0].evidence == "synthetic"
    else:
        assert service.jobs.reason(queued.job_id) in ("CHILD_FAILED", "INVALID_OUTPUT")


@pytest.mark.parametrize("mode", ["wait", "ignore"])
@pytest.mark.parametrize("action", ["cancel", "shutdown", "expiry"])
def test_active_child_cancellation_shutdown_loss_and_force_kill(
    tmp_path: Path, mode: str, action: str
) -> None:
    clock = ManualClock()
    service = service_for(tmp_path, clock)
    queued = submit(service)
    clock.now = ENDED
    launcher = ControlledLauncher(mode)
    worker = PredictionWorker(
        service, launcher, tmp_path / "staging", poll_seconds=0.01
    )
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(worker.once)
        assert launcher.started.wait(10)
        if action == "cancel":
            assert service.cancel(queued.job_id).state == "cancelling"
        elif action == "shutdown":
            worker.stop.set()
        else:
            clock.now = "2026-11-10T11:00:00Z"
            service.jobs.recover()
        assert future.result(timeout=10)
    job = service.get(queued.job_id)
    assert job.state == ("cancelled" if action == "cancel" else "failed")
    assert job.termination_confirmed == (action == "cancel")
    assert launcher.child is not None and launcher.child.process.returncode is not None
    if mode == "ignore":
        assert launcher.child.process.returncode == -9


def test_timeout_before_capacity_released_and_queued_shutdown(tmp_path: Path) -> None:
    from dataclasses import replace

    clock = ManualClock()
    service = service_for(tmp_path, clock)
    profile = service.profiles[0]
    service.profiles = (
        replace(profile, limits=replace(profile.limits, max_seconds=1)),
    )
    queued = submit(service)
    clock.now = ENDED
    launcher = ControlledLauncher("ignore")
    worker = PredictionWorker(
        service,
        launcher,
        tmp_path / "staging",
        heartbeat_seconds=0.1,
        poll_seconds=0.01,
    )
    assert worker.once()
    assert service.get(queued.job_id).state == "failed"
    assert service.jobs.reason(queued.job_id) == "TIMEOUT"
    second = submit(service, "second")
    worker.stop.set()
    assert not worker.once()
    assert service.get(second.job_id).state == "queued"


def test_cancel_before_claim_and_confirmed_termination_required(tmp_path: Path) -> None:
    clock = ManualClock()
    service = service_for(tmp_path, clock)
    queued = submit(service)
    cancelled = service.cancel(queued.job_id)
    assert cancelled.termination_confirmed
    assert service.cancel(queued.job_id) == cancelled
    worker = PredictionWorker(service, ControlledLauncher(), tmp_path / "staging")
    assert not worker.once()
    assert submit(service) == cancelled
    assert submit(service, "second").state == "queued"
    running = service.jobs.claim("worker-1", 60)
    assert running
    cancelling = service.cancel(running.job_id)
    failed = service.jobs.finish(cancelling, "WORKER_LOST", terminated=False)
    assert failed.state == "failed" and not failed.termination_confirmed


def test_parent_death_pipe_kills_child_group(tmp_path: Path) -> None:
    # A real supervisor process abruptly exits, rather than a simulated transition.
    script = """
import os
from pathlib import Path
from orchestration_examples import ManualClock, service_for, submit
from test_prediction_worker import ControlledLauncher
from neurofold.application.prediction_worker import PredictionWorker
root = Path(__import__('sys').argv[1])
service = service_for(root, ManualClock())
submit(service)
launcher = ControlledLauncher('ignore')
job = service.jobs.claim('parent-worker', 60)
stage = root / 'child'
stage.mkdir()
child = launcher.launch(stage, job)
(root / 'child-pid').write_text(str(child.process.pid))
os._exit(91)
"""
    import select

    fifo = tmp_path / "liveness.fifo"
    os.mkfifo(fifo)
    reader = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
    try:
        result = subprocess.run(
            [sys.executable, "-c", script, str(tmp_path)],
            capture_output=True,
            timeout=15,
        )
        assert result.returncode == 91, result.stderr
        readable, _, _ = select.select([reader], [], [], 10)
        assert readable and os.read(reader, 1) == b""
    finally:
        os.close(reader)


def test_heartbeat_database_failure_stops_and_reaps_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = ManualClock()
    service = service_for(tmp_path, clock)
    job = submit(service)
    launcher = ControlledLauncher("ignore")

    def unavailable(owner: PredictionJob, lease_seconds: float) -> PredictionJob:
        raise OSError("authored heartbeat failure")

    monkeypatch.setattr(service.jobs, "renew", unavailable)
    worker = PredictionWorker(
        service,
        launcher,
        tmp_path / "staging",
        heartbeat_seconds=0.05,
        poll_seconds=0.01,
    )
    assert worker.once()
    assert service.get(job.job_id).state == "failed"
    assert service.jobs.reason(job.job_id) == "SUPERVISION_FAILED"
    assert launcher.child is not None and launcher.child.process.returncode == -9


@pytest.mark.parametrize(
    "mode", ["exit_before_ready", "no_ready", "bad_ready", "startup_shutdown"]
)
def test_startup_wait_is_bounded_interruptible_and_reaps(
    tmp_path: Path, mode: str
) -> None:
    service = service_for(tmp_path, ManualClock())
    queued = submit(service)
    launcher = ControlledLauncher(
        "no_ready" if mode == "startup_shutdown" else mode,
        ready_seconds=0.25 if mode == "no_ready" else 30,
    )
    worker = PredictionWorker(service, launcher, tmp_path / "staging")
    launcher.stop = worker.stop
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(worker.once)
        try:
            assert launcher.spawned.wait(10)
            if mode == "startup_shutdown":
                worker.stop.set()
            if mode == "exit_before_ready":
                assert launcher.child is not None
                assert launcher.child.process.wait(timeout=15) == 17
                assert future.result(2)
            else:
                assert future.result(2 if mode == "startup_shutdown" else 15)
            assert not launcher.started.is_set()
            assert launcher.child is not None
            assert launcher.child.poll() is not None
            assert launcher.child.death_writer == -1
            with pytest.raises(ProcessLookupError):
                os.killpg(launcher.child.process.pid, 0)
        finally:
            # Cleanup after assertions cannot turn a launcher leak into a pass.
            worker.stop.set()
            if launcher.child is not None and launcher.child.poll() is None:
                launcher.child.terminate_and_reap()
    assert service.get(queued.job_id).state == "failed"
    assert service.jobs.failure(queued.job_id).cause == (
        "SHUTDOWN" if mode == "startup_shutdown" else "SUPERVISION_FAILED"
    )
    if mode == "exit_before_ready":
        assert launcher.child.process.returncode == 17

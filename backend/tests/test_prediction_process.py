"""Real unreaped exits and signal failures in the POSIX process adapter."""

import errno
import os
import select
import signal
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

import pytest
from orchestration_examples import ManualClock, service_for, submit

from neurofold.adapters.prediction_process import ProcessChild, ProcessLauncher
from neurofold.application.prediction_worker import PredictionWorker
from neurofold.core.prediction_jobs import PredictionJob


def exited_unreaped(process: subprocess.Popen[bytes]) -> None:
    """Observe kernel exit without poll/wait consuming the child's exit status."""
    if sys.platform == "darwin":
        with closing(select.kqueue()) as queue:
            event = select.kevent(
                process.pid,
                filter=select.KQ_FILTER_PROC,
                flags=select.KQ_EV_ADD | select.KQ_EV_ONESHOT,
                fflags=select.KQ_NOTE_EXIT,
            )
            try:
                assert queue.control([event], 1, 15), "Child did not exit"
            except ProcessLookupError:
                # Registration can race with process exit.
                pass
    else:
        result = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOWAIT)
        assert result is not None and result.si_pid == process.pid
    assert process.returncode is None


def assert_reaped(child: ProcessChild, writer: int) -> None:
    assert child.process.returncode is not None
    assert child.death_writer == -1
    with pytest.raises(OSError) as error:
        os.fstat(writer)
    assert error.value.errno == errno.EBADF
    with pytest.raises(ChildProcessError):
        os.waitpid(child.process.pid, os.WNOHANG)


def cleanup(child: ProcessChild) -> None:
    # Independent fallback runs after assertions and must not heal a failing test.
    if child.process.poll() is None:
        child.process.kill()
    child.process.wait(timeout=5)
    if child.death_writer >= 0:
        os.close(child.death_writer)
        child.death_writer = -1


def test_exited_unreaped_child_can_be_terminated_and_pipe_closed() -> None:
    reader, writer = os.pipe()
    os.close(reader)
    process = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
    child = ProcessChild(process, writer, 0.1)
    try:
        exited_unreaped(process)
        child.terminate_and_reap()
        assert process.returncode == 0
        assert_reaped(child, writer)
    finally:
        cleanup(child)


@pytest.mark.parametrize("action", ["cancel", "shutdown", "timeout"])
def test_worker_retains_terminal_state_when_child_exits_before_cleanup(
    tmp_path: Path, action: str
) -> None:
    clock = ManualClock()
    service = service_for(tmp_path, clock)
    queued = submit(service)

    class ExitingLauncher(ProcessLauncher):
        child: ProcessChild | None = None
        writer = -1

        def launch(self, directory: Path, job: PredictionJob) -> ProcessChild:
            child = super().launch(directory, job)
            self.child, self.writer = child, child.death_writer
            exited_unreaped(child.process)
            if action == "cancel":
                service.cancel(job.job_id)
            elif action == "shutdown":
                worker.stop.set()
            else:
                clock.now = "2026-11-10T10:00:11Z"
            return child

    launcher = ExitingLauncher(grace=0.1)
    worker = PredictionWorker(service, launcher, tmp_path / "staging")
    try:
        assert worker.once()
        assert launcher.child is not None
        assert_reaped(launcher.child, launcher.writer)
        retained = service.get(queued.job_id)
        if action == "cancel":
            assert retained.state == "cancelled" and retained.termination_confirmed
        else:
            assert retained.state == "failed"
            assert service.jobs.failure(queued.job_id).cause == action.upper()
    finally:
        if launcher.child is not None:
            cleanup(launcher.child)


def test_signal_permission_error_is_not_ignored_for_live_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader, writer = os.pipe()
    os.close(reader)
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True
    )
    child = ProcessChild(process, writer, 0.1)

    def denied(pid: int, value: int) -> None:
        raise PermissionError(errno.EPERM, "Authored live-child denial")

    try:
        with monkeypatch.context() as patch:
            patch.setattr(os, "killpg", denied)
            with pytest.raises(PermissionError, match="live-child denial"):
                child._signal(signal.SIGTERM)
            assert process.returncode is None and child.death_writer == writer
    finally:
        cleanup(child)


def test_reap_closes_pipe_when_postwait_group_signal_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader, writer = os.pipe()
    os.close(reader)
    process = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
    child = ProcessChild(process, writer, 0.1)

    def failed(value: int) -> None:
        raise OSError("Authored group cleanup error")

    monkeypatch.setattr(child, "_signal", failed)
    try:
        with pytest.raises(OSError, match="group cleanup error"):
            child.reap()
        assert_reaped(child, writer)
    finally:
        cleanup(child)


def test_terminate_still_reaps_and_closes_after_initial_signal_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader, writer = os.pipe()
    os.close(reader)
    process = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
    child = ProcessChild(process, writer, 0.1)
    original = child._signal

    def failed(value: int) -> None:
        if value == signal.SIGTERM:
            raise OSError("Authored initial signal error")
        original(value)

    monkeypatch.setattr(child, "_signal", failed)
    try:
        exited_unreaped(process)
        with pytest.raises(OSError, match="initial signal error"):
            child.terminate_and_reap()
        assert_reaped(child, writer)
    finally:
        cleanup(child)


def test_exited_permission_error_is_handled_on_every_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader, writer = os.pipe()
    os.close(reader)
    process = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
    child = ProcessChild(process, writer, 0.1)
    signals: list[int] = []
    original = os.killpg

    def denied(pid: int, value: int) -> None:
        signals.append(value)
        if len(signals) == 1:
            raise PermissionError(errno.EPERM, "Authored Darwin exited-group behavior")
        original(pid, value)

    try:
        exited_unreaped(process)
        with monkeypatch.context() as patch:
            patch.setattr(os, "killpg", denied)
            child.terminate_and_reap()
        assert signals == [signal.SIGTERM, signal.SIGTERM, signal.SIGKILL]
        assert process.returncode == 0
        assert_reaped(child, writer)
    finally:
        cleanup(child)


@pytest.mark.skipif(sys.platform != "darwin", reason="Darwin exit-transition EPERM")
@pytest.mark.parametrize("attempt", range(10))
def test_cleanup_at_first_darwin_eperm(attempt: int) -> None:
    import time

    reader, writer = os.pipe()
    os.close(reader)
    process = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
    child = ProcessChild(process, writer, 0.1)
    try:
        until = time.monotonic() + 5
        while True:
            try:
                os.killpg(process.pid, 0)
            except PermissionError:
                break  # Act immediately, before a kqueue event or poll can wait.
            assert time.monotonic() < until, "Did not observe exit-transition EPERM"
        child.terminate_and_reap()
        assert process.returncode == 0
        assert_reaped(child, writer)
    finally:
        cleanup(child)


def test_permission_waits_for_exit_transition_on_every_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader, writer = os.pipe()
    os.close(reader)
    process = subprocess.Popen(
        ["/bin/sh", "-c", "read token"], stdin=subprocess.PIPE, start_new_session=True
    )
    child = ProcessChild(process, writer, 0.1)
    original = os.killpg
    calls = 0

    def exiting(pid: int, value: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            assert process.returncode is None
            assert process.stdin is not None
            process.stdin.close()
            raise PermissionError(errno.EPERM, "Authored exit transition")
        original(pid, value)

    try:
        with monkeypatch.context() as patch:
            patch.setattr(os, "killpg", exiting)
            # Reproduce the transitional observation even on Linux CI; wait()
            # must observe the real process exiting after its stdin is released.
            patch.setattr(process, "poll", lambda: None)
            child.terminate_and_reap()
        assert_reaped(child, writer)
    finally:
        if process.stdin is not None:
            process.stdin.close()
        cleanup(child)


@pytest.mark.parametrize("action", ["cancel", "shutdown", "timeout"])
def test_worker_records_cleanup_error_without_confirming_termination(
    tmp_path: Path,
    action: str,
) -> None:
    from test_prediction_hardening import FinishedChild

    clock = ManualClock()
    service = service_for(tmp_path, clock)
    queued = submit(service)

    class FailedCleanup(FinishedChild):
        def terminate_and_reap(self) -> None:
            raise PermissionError("Authored cleanup failure")

    class Launcher:
        def launch(self, directory: Path, job: PredictionJob) -> FailedCleanup:
            if action == "cancel":
                service.cancel(job.job_id)
            elif action == "shutdown":
                worker.stop.set()
            else:
                clock.now = "2026-11-10T10:00:11Z"
            return FailedCleanup()

    worker = PredictionWorker(service, Launcher(), tmp_path / "staging")
    assert worker.once()
    retained = service.get(queued.job_id)
    assert retained.state == "failed" and not retained.termination_confirmed
    assert service.jobs.failure(queued.job_id).cause == "SUPERVISION_FAILED"
    assert worker.stop.is_set()
    next_job = submit(service, "after-cleanup-failure")
    assert not worker.once()
    assert service.get(next_job.job_id).state == "queued"


def test_unsignalable_live_child_cleanup_is_bounded_and_closes_pipe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader, writer = os.pipe()
    os.close(reader)
    process = subprocess.Popen(
        ["/bin/sh", "-c", "read token"], stdin=subprocess.PIPE, start_new_session=True
    )
    child = ProcessChild(process, writer, 0.1)

    def denied(pid: int, value: int) -> None:
        raise PermissionError(errno.EPERM, "Authored unsignalable live child")

    try:
        with monkeypatch.context() as patch, ThreadPoolExecutor(1) as pool:
            patch.setattr(os, "killpg", denied)
            future = pool.submit(child.terminate_and_reap)
            try:
                with pytest.raises(PermissionError, match="unsignalable live child"):
                    future.result(5)
                assert process.poll() is None
                assert child.death_writer == -1
                with pytest.raises(OSError) as error:
                    os.fstat(writer)
                assert error.value.errno == errno.EBADF
            finally:
                # Release the child even if a removed bound made the test time out.
                assert process.stdin is not None
                process.stdin.close()
    finally:
        cleanup(child)


def test_group_permission_error_after_leader_exit_is_not_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader, writer = os.pipe()
    os.close(reader)
    process = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
    child = ProcessChild(process, writer, 0.1)

    def denied(pid: int, value: int) -> None:
        raise PermissionError(errno.EPERM, "Authored unsignalable group member")

    try:
        exited_unreaped(process)
        with monkeypatch.context() as patch:
            patch.setattr(os, "killpg", denied)
            with pytest.raises(PermissionError, match="unsignalable group member"):
                child.reap()
        assert_reaped(child, writer)  # Leader and FD only; group denial propagated.
    finally:
        cleanup(child)

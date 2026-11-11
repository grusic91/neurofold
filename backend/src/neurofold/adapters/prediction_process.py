"""POSIX argument-only isolated child launcher; never configured by HTTP."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from neurofold.core.orchestration import LaunchCleanupError
from neurofold.core.prediction_jobs import PredictionJob


class ProcessChild:
    def __init__(
        self, process: subprocess.Popen[bytes], death_writer: int, grace: float
    ) -> None:
        self.process, self.death_writer, self.grace = process, death_writer, grace

    @property
    def process_id(self) -> int:
        return self.process.pid

    @property
    def process_group_id(self) -> int:
        return self.process.pid  # ProcessLauncher creates a new session.

    def poll(self) -> int | None:
        return self.process.poll()

    def _signal(self, value: int) -> None:
        try:
            os.killpg(self.process.pid, value)
        except ProcessLookupError:
            pass
        except PermissionError as denied:
            # Darwin can reject signals before an exiting child is waitable.
            try:
                self.process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                raise denied from None
            # Leader exit alone cannot excuse an unsignalable live descendant.
            until = time.monotonic() + 0.1
            while True:
                try:
                    os.killpg(self.process.pid, value)
                    return
                except ProcessLookupError:
                    return
                except PermissionError:
                    if time.monotonic() >= until:
                        raise denied from None
                    time.sleep(0.001)

    def reap(self) -> int:
        try:
            code = self.process.wait(timeout=max(0.5, self.grace))
            # A returned leader is not proof that its descendants exited.
            self._signal(signal.SIGKILL)
            return code
        finally:
            if self.death_writer >= 0:
                writer, self.death_writer = self.death_writer, -1
                os.close(writer)

    def terminate_and_reap(self) -> None:
        try:
            self._signal(signal.SIGTERM)
            try:
                self.process.wait(timeout=self.grace)
            except subprocess.TimeoutExpired:
                self._signal(signal.SIGKILL)
        except BaseException:
            try:
                self.reap()
            except Exception:
                pass  # Preserve the original error after bounded cleanup.
            raise
        else:
            self.reap()


class ProcessLauncher:
    def __init__(
        self, module: str = "neurofold.prediction_child", *, grace: float = 2
    ) -> None:
        self.module, self.grace = module, grace

    def launch(self, directory: Path, job: PredictionJob) -> ProcessChild:
        (directory / "request.json").write_bytes(job.to_json())
        reader, writer = os.pipe()
        child = None
        try:
            try:
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "neurofold.process_child",
                        str(reader),
                        self.module,
                        str(directory),
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                    pass_fds=(reader,),
                )
                child = ProcessChild(process, writer, self.grace)
            finally:
                os.close(reader)
        except BaseException:
            if child is None:
                os.close(writer)
            else:
                try:
                    child.terminate_and_reap()
                except Exception as exc:
                    raise LaunchCleanupError(child) from exc
            raise
        return child

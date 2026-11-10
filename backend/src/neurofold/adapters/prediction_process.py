"""POSIX argument-only isolated child launcher; never configured by HTTP."""

import os
import signal
import subprocess
import sys
from pathlib import Path

from neurofold.core.prediction_jobs import PredictionJob


class ProcessChild:
    def __init__(
        self, process: subprocess.Popen[bytes], death_writer: int, grace: float
    ) -> None:
        self.process, self.death_writer, self.grace = process, death_writer, grace

    def poll(self) -> int | None:
        return self.process.poll()

    def _signal(self, value: int) -> None:
        try:
            os.killpg(self.process.pid, value)
        except ProcessLookupError:
            pass

    def reap(self) -> int:
        code = self.process.wait()
        # A returned leader is not proof that its descendants exited.
        self._signal(signal.SIGKILL)
        if self.death_writer >= 0:
            os.close(self.death_writer)
            self.death_writer = -1
        return code

    def terminate_and_reap(self) -> None:
        self._signal(signal.SIGTERM)
        try:
            self.process.wait(timeout=self.grace)
        except subprocess.TimeoutExpired:
            self._signal(signal.SIGKILL)
        self.reap()


class ProcessLauncher:
    def __init__(
        self, module: str = "neurofold.prediction_child", *, grace: float = 2
    ) -> None:
        self.module, self.grace = module, grace

    def launch(self, directory: Path, job: PredictionJob) -> ProcessChild:
        (directory / "request.json").write_bytes(job.to_json())
        reader, writer = os.pipe()
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
        except BaseException:
            os.close(writer)
            raise
        finally:
            os.close(reader)
        return ProcessChild(process, writer, self.grace)

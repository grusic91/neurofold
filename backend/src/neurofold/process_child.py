"""Private POSIX child envelope: parent death, resource bounds, trusted module."""

import os
import resource
import runpy
import signal
import sys
import threading
from pathlib import Path

from neurofold.core.prediction_jobs import PredictionJob


def main() -> None:
    reader = int(sys.argv[1])
    module, directory = sys.argv[2:4]

    def parent_death() -> None:
        try:
            os.read(reader, 1)
        finally:
            os.killpg(os.getpgrp(), signal.SIGKILL)

    threading.Thread(target=parent_death, daemon=True).start()
    job = PredictionJob.from_json((Path(directory) / "request.json").read_bytes())
    limits = job.spec.profile.limits
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024, 16 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(
        resource.RLIMIT_CPU, (limits.max_seconds + 1, limits.max_seconds + 2)
    )
    # RLIMIT_AS is not reliably supported on macOS. Real memory acceptance is a
    # Linux gate; enable a process address-space ceiling there.
    if sys.platform == "linux":
        resource.setrlimit(
            resource.RLIMIT_AS, (limits.max_memory_bytes, limits.max_memory_bytes)
        )
    os.chdir(directory)
    sys.argv = [module, directory]
    runpy.run_module(module, run_name="__main__")


if __name__ == "__main__":
    main()

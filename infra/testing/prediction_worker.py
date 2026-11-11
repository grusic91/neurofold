"""Separately launched acceptance worker; not production adapter registration."""

import fcntl
import os
import signal
from pathlib import Path

from prediction_app import services
from test_prediction_worker import ControlledLauncher

from neurofold.application.prediction_worker import PredictionWorker


def main() -> None:
    service = services()
    root = Path(os.environ["NEUROFOLD_ARCHIVE_ROOT"])
    with (root / "controlled-worker.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        launcher = ControlledLauncher(os.environ.get("CONTROLLED_CHILD", "copy"))
        worker = PredictionWorker(
            service,
            launcher,
            root / "staging",
            lease_seconds=6,
            heartbeat_seconds=1,
        )
        launcher.stop = worker.stop
        for value in (signal.SIGINT, signal.SIGTERM):
            signal.signal(value, lambda number, frame: worker.stop.set())
        worker.run()
        raise SystemExit(worker.exit_code)


if __name__ == "__main__":
    main()

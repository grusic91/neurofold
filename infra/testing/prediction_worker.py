"""Separately launched acceptance worker; not production adapter registration."""

import fcntl
import logging
import os
import signal
from pathlib import Path

from prediction_app import services
from test_prediction_worker import ControlledLauncher

from neurofold.application.prediction_worker import PredictionWorker, integrity_message
from neurofold.core.errors import ArchiveIntegrityError


def _run() -> None:
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


def main() -> None:
    try:
        _run()
    except ArchiveIntegrityError as exc:
        logging.getLogger(__name__).critical(
            "worker blocked reason=ARCHIVE_INTEGRITY exit_code=65 "
            "error_type=%s message=%s; operator recovery and restart required",
            type(exc).__name__,
            integrity_message(exc),
        )
        raise SystemExit(65) from None


if __name__ == "__main__":
    main()

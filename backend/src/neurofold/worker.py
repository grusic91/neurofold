"""Separately launched local worker; no API imports, no runtime probing."""

import fcntl
import logging
import os
import signal
from pathlib import Path

from neurofold.adapters.biological.storage import FilesystemStore
from neurofold.adapters.prediction_archive import PredictionArchive
from neurofold.adapters.prediction_process import ProcessLauncher
from neurofold.adapters.prediction_sqlite import SQLiteJobs, utc_now
from neurofold.adapters.variant_storage import FilesystemVariants
from neurofold.application.prediction_worker import PredictionWorker, integrity_message
from neurofold.application.predictions import PredictionService
from neurofold.core.errors import ArchiveIntegrityError
from neurofold.core.prediction_inputs import capabilities


def _run() -> None:
    root = Path(os.environ.get("NEUROFOLD_ARCHIVE_ROOT", "data/archive"))
    source = FilesystemStore(root)
    prediction_root = source.root / "predictions"
    prediction_root.mkdir(mode=0o700, exist_ok=True)
    with (prediction_root / "worker.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        jobs = SQLiteJobs(prediction_root / "jobs.sqlite3")
        service = PredictionService(
            jobs,
            PredictionArchive(
                prediction_root / "registered", jobs, source.artifact_store
            ),
            source,
            FilesystemVariants(source, source),
            profiles=tuple(p for c in capabilities() for p in c.profiles),
            code=None,
            clock=utc_now,
        )
        worker = PredictionWorker(
            service, ProcessLauncher(), prediction_root / "staging"
        )
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

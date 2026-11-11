"""Explicit M2 acceptance composition; copies authored proposals, no inference."""

import os
from pathlib import Path

from offline_app import services as biological_services
from orchestration_examples import ManualClock, service_for

from neurofold.adapters.prediction_sqlite import SQLiteJobs, utc_now
from neurofold.api.configuration import Settings
from neurofold.api.main import create_app
from neurofold.application.predictions import PredictionService


def services() -> PredictionService:
    service = service_for(Path(os.environ["NEUROFOLD_ARCHIVE_ROOT"]), ManualClock())
    service.clock = utc_now
    assert isinstance(service.jobs, SQLiteJobs)
    service.jobs.clock = utc_now
    return service


app = create_app(
    prediction_factory=services,
    service_factory=lambda: biological_services(
        Settings(
            archive_root=Path(os.environ["NEUROFOLD_ARCHIVE_ROOT"]) / "data/source"
        ),
        fixtures=Path("/app/backend/tests/fixtures"),
    ),
)

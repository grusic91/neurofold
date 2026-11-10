"""Explicit M2 acceptance composition; copies authored proposals, no inference."""

import os
from pathlib import Path

from orchestration_examples import ManualClock, service_for

from neurofold.adapters.prediction_sqlite import SQLiteJobs, utc_now
from neurofold.api.main import create_app
from neurofold.application.predictions import PredictionService


def services() -> PredictionService:
    service = service_for(Path(os.environ["NEUROFOLD_ARCHIVE_ROOT"]), ManualClock())
    service.clock = utc_now
    assert isinstance(service.jobs, SQLiteJobs)
    service.jobs.clock = utc_now
    return service


app = create_app(prediction_factory=services)

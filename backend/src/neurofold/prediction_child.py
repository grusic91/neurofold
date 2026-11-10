"""Production child entry point. M2 intentionally registers no runtime adapters."""

from pathlib import Path

from neurofold.core.orchestration import OrchestrationError
from neurofold.core.prediction import PredictionAdapter
from neurofold.core.prediction_jobs import PredictionJob


def selected_adapter(profile_id: str) -> PredictionAdapter:
    # M3/M5 own explicit reviewed registrations. Never promote contract_only.
    raise OrchestrationError("PROFILE_UNAVAILABLE")


def run(directory: Path) -> None:
    job = PredictionJob.from_json((directory / "request.json").read_bytes())
    if job.spec.profile.availability != "available":
        raise OrchestrationError("PROFILE_UNAVAILABLE")
    adapter = selected_adapter(job.spec.profile.profile.name)
    result = adapter.predict(job.spec, output_dir=directory)
    # A future selected adapter must also emit the strict proposal bundle; this
    # return value alone cannot authorize success or substitute provenance.
    if not (directory / "bundle.json").is_file() or result.job_id != job.job_id:
        raise OrchestrationError("JOB_CONFLICT")


if __name__ == "__main__":
    import sys

    run(Path(sys.argv[1]))

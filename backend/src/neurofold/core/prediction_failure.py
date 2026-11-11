"""Checksummed operational failure extension; frozen M1 job bytes stay unchanged."""

from dataclasses import dataclass
from typing import Literal

from neurofold.core.prediction_base import PredictionRecord, domain, identifier
from neurofold.core.prediction_jobs import instant
from neurofold.core.provenance import ContentReference, HashEncoding

FailureReason = Literal[
    "WORKER_LOST",
    "TIMEOUT",
    "SHUTDOWN",
    "CHILD_FAILED",
    "INVALID_OUTPUT",
    "PUBLICATION_FAILED",
    "SUPERVISION_FAILED",
]


@dataclass(frozen=True, kw_only=True)
class OperationalFailure(PredictionRecord):
    schema_version: Literal["neurofold-prediction-failure/1"] = (
        "neurofold-prediction-failure/1"
    )
    job: ContentReference
    attempt_id: str
    cause: FailureReason
    ended_at: str
    retry_policy: Literal["explicit-new-job-same-spec"] = "explicit-new-job-same-spec"

    def _validate(self) -> None:
        domain(self.job, HashEncoding.CANONICAL_JSON)
        identifier(self.attempt_id)
        instant(self.ended_at)

"""NF-04 M2 storage and process boundaries; standard-library only."""

# This boundary registers proposals but cannot declare success itself.
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from neurofold.core.biological import ReferenceSnapshot
from neurofold.core.prediction_bundle import ChildBundle
from neurofold.core.prediction_inputs import PredictionSpec
from neurofold.core.prediction_jobs import PredictionJob
from neurofold.core.prediction_outputs import (
    PredictionResult,
    SuccessfulPredictionProvenance,
)
from neurofold.core.provenance import ContentReference
from neurofold.core.variants import VariantDefinition

FailureReason = Literal[
    "WORKER_LOST",
    "TIMEOUT",
    "SHUTDOWN",
    "CHILD_FAILED",
    "INVALID_OUTPUT",
    "PUBLICATION_FAILED",
    "SUPERVISION_FAILED",
]


class OrchestrationError(RuntimeError):
    def __init__(
        self,
        code: Literal[
            "INVALID_IDEMPOTENCY_KEY",
            "IDEMPOTENCY_CONFLICT",
            "JOB_CONFLICT",
            "PROFILE_UNAVAILABLE",
            "PREDICTION_BUSY",
            "PREDICTION_UNAVAILABLE",
            "CODE_IDENTITY_REQUIRED",
        ],
    ) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Registration:
    kind: str
    record_id: str
    sha256: str
    byte_size: int


@dataclass(frozen=True)
class Publication:
    intent_id: str
    job: PredictionJob
    result: ContentReference
    manifest: ContentReference
    graph: tuple[Registration, ...]
    validated_at: str


class DurableJobs(Protocol):
    def get(self, job_id: str) -> PredictionJob: ...
    def reason(self, job_id: str) -> FailureReason | None: ...
    def submit(
        self, spec: PredictionSpec, key: str, retry: str | None, *, available: bool
    ) -> PredictionJob: ...
    def claim(self, worker_id: str, lease_seconds: float) -> PredictionJob | None: ...
    def cancel(self, job_id: str) -> PredictionJob: ...
    def renew(self, owner: PredictionJob, lease_seconds: float) -> PredictionJob: ...
    def stage(
        self,
        owner: PredictionJob,
        stage: Literal["preparing", "inference", "validating"],
    ) -> PredictionJob: ...
    def finish(
        self, owner: PredictionJob, reason: FailureReason | None, *, terminated: bool
    ) -> PredictionJob: ...
    def recover(self) -> int: ...
    def begin_publication(self, owner: PredictionJob) -> str: ...
    def ready(self, publication: Publication) -> None: ...
    def succeed(self, publication: Publication) -> PredictionJob: ...


class Child(Protocol):
    def poll(self) -> int | None: ...
    def terminate_and_reap(self) -> None: ...
    def reap(self) -> int: ...


class ChildLauncher(Protocol):
    def launch(self, directory: Path, job: PredictionJob) -> Child: ...


Clock = Callable[[], str]


class PublicationArchive(Protocol):
    def lock(self) -> AbstractContextManager[None]: ...
    def register(
        self,
        intent_id: str,
        job: PredictionJob,
        bundle: ChildBundle,
        reference: ReferenceSnapshot,
        variant: VariantDefinition | None,
        now: str,
    ) -> Publication: ...
    def verify(
        self, job: PredictionJob
    ) -> tuple[PredictionResult, SuccessfulPredictionProvenance]: ...
    def artifact(self, job: PredictionJob, artifact_id: str) -> tuple[bytes, str]: ...

"""NF-04 M2 storage and process boundaries; standard-library only."""

# This boundary registers proposals but cannot declare success itself.
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from neurofold.core.biological import ReferenceSnapshot
from neurofold.core.prediction_bundle import ChildBundle
from neurofold.core.prediction_failure import FailureReason as FailureReason
from neurofold.core.prediction_failure import OperationalFailure
from neurofold.core.prediction_inputs import PredictionSpec
from neurofold.core.prediction_jobs import PredictionJob
from neurofold.core.prediction_outputs import (
    PredictionResult,
    SuccessfulPredictionProvenance,
)
from neurofold.core.provenance import ContentReference
from neurofold.core.variants import VariantDefinition


class OrchestrationError(RuntimeError):
    def __init__(
        self,
        code: Literal[
            "INVALID_IDEMPOTENCY_KEY",
            "IDEMPOTENCY_CONFLICT",
            "JOB_CONFLICT",
            "PROFILE_UNAVAILABLE",
            "PREDICTION_BUSY",
            "PREDICTION_QUEUE_FULL",
            "PREDICTION_MUTATION_UNCERTAIN",
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
    def failure(self, job_id: str) -> OperationalFailure: ...
    def snapshot(self, job_id: str) -> tuple[PredictionJob, FailureReason | None]: ...
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


@runtime_checkable
class IdentifiedChild(Protocol):
    @property
    def process_id(self) -> int: ...

    @property
    def process_group_id(self) -> int: ...


class LaunchCleanupError(RuntimeError):
    """Launch failed after spawning; transfer the unconfirmed child to the caller."""

    def __init__(self, child: Child) -> None:
        self.child = child
        super().__init__("Launch cleanup unconfirmed")


class ChildLauncher(Protocol):
    """Own a spawned child until return. Ordinary errors guarantee cleanup;
    LaunchCleanupError explicitly transfers uncertain cleanup to the caller.
    """

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
        checkpoint: Callable[[], None] = lambda: None,
    ) -> Publication: ...
    def verify(
        self, job: PredictionJob
    ) -> tuple[PredictionResult, SuccessfulPredictionProvenance]: ...
    def artifact(self, job: PredictionJob, artifact_id: str) -> tuple[bytes, str]: ...

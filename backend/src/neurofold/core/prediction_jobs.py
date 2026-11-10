"""Pure lifecycle proposals; M2 must enforce these checks transactionally."""

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal, Protocol

from neurofold.core.prediction_base import (
    PredictionError,
    PredictionRecord,
    domain,
    identifier,
    require,
)
from neurofold.core.prediction_base import (
    PredictionErrorCode as E,
)
from neurofold.core.prediction_base import (
    ValidationStage as S,
)
from neurofold.core.prediction_inputs import PredictionSpec
from neurofold.core.provenance import ContentHash, ContentReference, HashEncoding, _utc

JobState = Literal[
    "queued", "running", "cancelling", "succeeded", "failed", "cancelled"
]
TERMINAL = frozenset({"succeeded", "failed", "cancelled"})
EDGES: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "cancelled"}),
    "running": frozenset({"cancelling", "succeeded", "failed"}),
    "cancelling": frozenset({"cancelled", "failed"}),
}


def instant(value: str) -> datetime:
    require(type(value) is str)
    try:
        _utc(value)
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise PredictionError(E.INVALID_REPRESENTATION, S.REPRESENTATION) from exc


@dataclass(frozen=True, kw_only=True)
class JobRecord(PredictionRecord):
    schema_version: Literal["neurofold-prediction-job/1"] = "neurofold-prediction-job/1"


@dataclass(frozen=True, kw_only=True)
class PredictionAttempt(JobRecord):
    attempt_id: str
    worker_id: str
    lease_id: str
    fence: int
    started_at: str
    heartbeat_at: str
    lease_expires_at: str
    fenced: bool

    def _validate(self) -> None:
        for value in (self.attempt_id, self.worker_id, self.lease_id):
            identifier(value)
        require(self.fence > 0)
        require(
            instant(self.started_at)
            <= instant(self.heartbeat_at)
            < instant(self.lease_expires_at)
        )


@dataclass(frozen=True, kw_only=True)
class PredictionFailure(JobRecord):
    code: E
    stage: S
    retryable: bool


@dataclass(frozen=True, kw_only=True)
class PredictionJob(JobRecord):
    job_id: str
    spec: PredictionSpec
    spec_hash: ContentHash
    state: JobState
    version: int
    submitted_at: str
    started_at: str | None
    ended_at: str | None
    attempt: PredictionAttempt | None
    cancellation_requested: bool
    termination_confirmed: bool
    retry_of_job_id: str | None
    stage: Literal["queued", "preparing", "inference", "validating", "finished"]
    progress_basis_points: int | None
    failure: PredictionFailure | None
    result: ContentReference | None
    manifest: ContentReference | None

    def _validate(self) -> None:
        identifier(self.job_id)
        require(self.version >= 0 and self.spec_hash == self.spec.content_hash)
        instant(self.submitted_at)
        if self.retry_of_job_id is not None:
            identifier(self.retry_of_job_id)
            require(self.retry_of_job_id != self.job_id)
        if self.progress_basis_points is not None:
            require(0 <= self.progress_basis_points <= 10000)
        if self.started_at is not None:
            require(instant(self.submitted_at) <= instant(self.started_at))
        if self.ended_at is not None:
            require(
                instant(self.started_at or self.submitted_at) <= instant(self.ended_at)
            )
        require((self.state in TERMINAL) == (self.ended_at is not None))
        require((self.state == "failed") == (self.failure is not None))
        require((self.state == "succeeded") == (self.result is not None))
        require((self.state == "succeeded") == (self.manifest is not None))
        for reference in (self.result, self.manifest):
            if reference is not None:
                domain(reference, HashEncoding.CANONICAL_JSON)
        if self.state == "queued":
            require(
                self.attempt is None
                and self.started_at is None
                and not self.cancellation_requested
                and not self.termination_confirmed
                and self.stage == "queued"
                and self.progress_basis_points is None
            )
        elif self.state == "cancelled":
            require(self.cancellation_requested and self.termination_confirmed)
            require((self.attempt is None) == (self.started_at is None))
        else:
            require(self.attempt is not None and self.started_at is not None)
            require(not self.termination_confirmed)
        if self.attempt is not None:
            require(self.attempt.started_at == self.started_at)
            if self.ended_at is not None:
                require(instant(self.attempt.heartbeat_at) <= instant(self.ended_at))
        if self.state == "cancelling":
            require(self.cancellation_requested)
        if self.state in ("running", "succeeded"):
            require(not self.cancellation_requested)
        require((self.state in TERMINAL) == (self.stage == "finished"))
        if self.state in ("running", "cancelling"):
            require(self.stage in ("preparing", "inference", "validating"))
        if self.state == "succeeded":
            assert self.attempt is not None and self.ended_at is not None
            require(
                not self.attempt.fenced
                and instant(self.ended_at) < instant(self.attempt.lease_expires_at)
            )


def validate_success_eligibility(
    job: PredictionJob, *, expected_version: int, attempt_id: str, fence: int, now: str
) -> None:
    require(type(job) is PredictionJob)
    require(
        type(expected_version) is int
        and type(fence) is int
        and job.version == expected_version
        and job.state == "running"
        and job.attempt is not None,
        E.ILLEGAL_TRANSITION,
        S.LIFECYCLE,
    )
    assert job.attempt is not None
    require(
        job.attempt.attempt_id == attempt_id
        and job.attempt.fence == fence
        and not job.attempt.fenced
        and instant(job.attempt.heartbeat_at)
        <= instant(now)
        < instant(job.attempt.lease_expires_at),
        E.ILLEGAL_TRANSITION,
        S.LIFECYCLE,
    )


def validate_transition(
    current: PredictionJob,
    proposed: PredictionJob,
    *,
    expected_version: int,
    attempt_id: str | None,
    fence: int | None,
    now: str,
) -> None:
    """Validate supplied snapshots only; no claim of compare-and-swap atomicity."""
    require(type(current) is PredictionJob and type(proposed) is PredictionJob)
    require(
        type(expected_version) is int
        and current.version == expected_version
        and proposed.version == current.version + 1
        and proposed.state in EDGES.get(current.state, frozenset())
        and proposed.job_id == current.job_id
        and proposed.spec == current.spec
        and proposed.submitted_at == current.submitted_at
        and proposed.retry_of_job_id == current.retry_of_job_id
        and proposed.cancellation_requested
        == (
            current.cancellation_requested
            or proposed.state in ("cancelling", "cancelled")
        ),
        E.ILLEGAL_TRANSITION,
        S.LIFECYCLE,
    )
    require(
        instant(now) >= instant(current.submitted_at)
        and (proposed.ended_at is None or proposed.ended_at == now),
        E.ILLEGAL_TRANSITION,
        S.LIFECYCLE,
    )
    if current.attempt is None:
        require(attempt_id is None and fence is None, E.ILLEGAL_TRANSITION, S.LIFECYCLE)
        if proposed.state == "running":
            require(proposed.started_at == now, E.ILLEGAL_TRANSITION, S.LIFECYCLE)
        else:
            require(proposed.attempt is None, E.ILLEGAL_TRANSITION, S.LIFECYCLE)
    else:
        require(
            type(fence) is int
            and current.attempt.attempt_id == attempt_id
            and current.attempt.fence == fence
            and (
                proposed.attempt == current.attempt
                or (
                    proposed.state == "failed"
                    and proposed.attempt == replace(current.attempt, fenced=True)
                )
            )
            and proposed.started_at == current.started_at
            and instant(now) >= instant(current.attempt.heartbeat_at),
            E.ILLEGAL_TRANSITION,
            S.LIFECYCLE,
        )
    if proposed.state == "succeeded":
        assert attempt_id is not None and fence is not None
        validate_success_eligibility(
            current,
            expected_version=expected_version,
            attempt_id=attempt_id,
            fence=fence,
            now=now,
        )


def validate_heartbeat(
    current: PredictionJob, proposed: PredictionJob, *, expected_version: int
) -> None:
    """A separate lease renewal proposal, never a state transition or new attempt."""
    require(type(current) is PredictionJob and type(proposed) is PredictionJob)
    require(
        type(expected_version) is int
        and expected_version == current.version
        and current.state in ("running", "cancelling")
        and current.attempt is not None
        and proposed.attempt is not None,
        E.ILLEGAL_TRANSITION,
        S.LIFECYCLE,
    )
    assert current.attempt is not None and proposed.attempt is not None
    old, new = current.attempt, proposed.attempt
    require(
        not old.fenced
        and not new.fenced
        and instant(old.heartbeat_at)
        <= instant(new.heartbeat_at)
        < instant(old.lease_expires_at)
        and instant(new.lease_expires_at) >= instant(old.lease_expires_at)
        and replace(
            new, heartbeat_at=old.heartbeat_at, lease_expires_at=old.lease_expires_at
        )
        == old
        and replace(proposed, attempt=old, version=current.version) == current
        and proposed.version == current.version + 1,
        E.ILLEGAL_TRANSITION,
        S.LIFECYCLE,
    )


class JobRepository(Protocol):
    """M2 boundary: commit rechecks expected version/state/fence inside transaction.

    Success additionally requires validated registered result/manifest dependencies.
    Unknown IDs use KeyError; domain conflicts use PredictionError. No implementation
    or job claim/dispatch behavior exists in M1.
    """

    def get(self, job_id: str) -> PredictionJob: ...

    def insert(self, job: PredictionJob) -> None: ...

    def commit(
        self,
        proposed: PredictionJob,
        *,
        expected_version: int,
        attempt_id: str | None,
        fence: int | None,
    ) -> None: ...


def validate_retry(previous: PredictionJob, retry: PredictionJob) -> None:
    """Explicit retry retains old history and creates a separate unclaimed job."""
    require(type(previous) is PredictionJob and type(retry) is PredictionJob)
    require(
        previous.state in ("failed", "cancelled")
        and retry.state == "queued"
        and retry.version == 0
        and retry.job_id != previous.job_id
        and retry.retry_of_job_id == previous.job_id
        and retry.spec == previous.spec
        and previous.ended_at is not None
        and instant(retry.submitted_at) >= instant(previous.ended_at),
        E.ILLEGAL_TRANSITION,
        S.LIFECYCLE,
    )

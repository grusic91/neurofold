"""Offline state/lease proposals, not execution, concurrency control or SQLite tests."""

from dataclasses import replace
from itertools import product
from typing import cast

import pytest
from prediction_examples import (
    ENDED,
    EXPIRES,
    STARTED,
    SUBMITTED,
    example,
    queued,
    ref,
    running,
)

from neurofold.core.prediction_base import (
    PredictionError,
    ValidationStage,
)
from neurofold.core.prediction_base import (
    PredictionErrorCode as E,
)
from neurofold.core.prediction_jobs import (
    EDGES,
    JobState,
    PredictionFailure,
    PredictionJob,
    validate_heartbeat,
    validate_retry,
    validate_success_eligibility,
    validate_transition,
)


def state_record(state: JobState) -> PredictionJob:
    if state == "queued":
        return queued()
    job = running()
    e = example()
    if state == "running":
        return job
    if state == "cancelling":
        return replace(job, state=state, cancellation_requested=True, version=2)
    return replace(
        job,
        state=state,
        version=3,
        ended_at=ENDED,
        stage="finished",
        cancellation_requested=state == "cancelled",
        termination_confirmed=state == "cancelled",
        failure=PredictionFailure(
            code=E.PUBLICATION_INTEGRITY,
            stage=ValidationStage.ARTIFACTS,
            retryable=False,
        )
        if state == "failed"
        else None,
        result=ref(e.result.result_id, e.result.content_hash)
        if state == "succeeded"
        else None,
        manifest=e.result.manifest if state == "succeeded" else None,
    )


STATES: tuple[JobState, ...] = (
    "queued",
    "running",
    "cancelling",
    "succeeded",
    "failed",
    "cancelled",
)


@pytest.mark.parametrize("source,target", list(product(STATES, STATES)))
def test_all_lifecycle_edges_and_forbidden_transitions(
    source: JobState, target: JobState
) -> None:
    current = state_record(source)
    proposed = state_record(target)
    if source == "queued" and target == "cancelled":
        proposed = replace(proposed, attempt=None, started_at=None)
    if source == "cancelling" and target == "failed":
        proposed = replace(proposed, cancellation_requested=True)
    # The queued version is operationally only an initial snapshot.
    proposed = replace(proposed, version=current.version + 1)
    attempt_id = current.attempt.attempt_id if current.attempt else None
    fence = current.attempt.fence if current.attempt else None
    now = STARTED if target == "running" else ENDED
    if target in EDGES.get(source, frozenset()):
        validate_transition(
            current,
            proposed,
            expected_version=current.version,
            attempt_id=attempt_id,
            fence=fence,
            now=now,
        )
    else:
        with pytest.raises(PredictionError) as error:
            validate_transition(
                current,
                proposed,
                expected_version=current.version,
                attempt_id=attempt_id,
                fence=fence,
                now=now,
            )
        assert error.value.code is E.ILLEGAL_TRANSITION


@pytest.mark.parametrize(
    "version,attempt_id,fence,now",
    [
        (0, "attempt-1", 1, ENDED),
        (True, "attempt-1", 1, ENDED),
        (1, "other", 1, ENDED),
        (1, "attempt-1", 2, ENDED),
        (1, "attempt-1", True, ENDED),
        (1, "attempt-1", 1, EXPIRES),
        (1, "attempt-1", 1, SUBMITTED),
    ],
)
def test_stale_expired_or_fenced_success(
    version: int, attempt_id: str, fence: int, now: str
) -> None:
    with pytest.raises(PredictionError) as error:
        validate_success_eligibility(
            running(),
            expected_version=version,
            attempt_id=attempt_id,
            fence=fence,
            now=now,
        )
    assert error.value.code is E.ILLEGAL_TRANSITION


def test_only_active_running_unfenced_attempt_can_propose_success() -> None:
    job = running()
    assert job.attempt is not None
    validate_success_eligibility(
        job, expected_version=1, attempt_id="attempt-1", fence=1, now=ENDED
    )
    for candidate in (
        replace(job, attempt=replace(job.attempt, fenced=True)),
        state_record("cancelling"),
        state_record("failed"),
        queued(),
    ):
        with pytest.raises(PredictionError):
            validate_success_eligibility(
                candidate,
                expected_version=candidate.version,
                attempt_id="attempt-1",
                fence=1,
                now=ENDED,
            )


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", 3),
        ("job_id", "other"),
        ("submitted_at", "2026-11-10T09:00:00Z"),
        ("retry_of_job_id", "old"),
        ("ended_at", "2026-11-10T10:00:03Z"),
    ],
)
def test_transition_proposal_cannot_rewrite_history(field: str, value: object) -> None:
    current = running()
    data = state_record("failed").to_dict() | {"version": 2, field: value}
    proposed = PredictionJob.from_dict(data)
    with pytest.raises(PredictionError):
        validate_transition(
            current,
            proposed,
            expected_version=1,
            attempt_id="attempt-1",
            fence=1,
            now=ENDED,
        )


def test_attempt_claim_and_competing_proposals_are_pure_only() -> None:
    current = queued()
    claim = running()
    assert claim.attempt is not None
    cancellation = replace(
        current,
        state="cancelled",
        version=1,
        cancellation_requested=True,
        termination_confirmed=True,
        ended_at=ENDED,
        stage="finished",
    )
    validate_transition(
        current, claim, expected_version=0, attempt_id=None, fence=None, now=STARTED
    )
    validate_transition(
        current,
        cancellation,
        expected_version=0,
        attempt_id=None,
        fence=None,
        now=ENDED,
    )
    # Both can validate against the old snapshot: storage must choose atomically in M2.
    with pytest.raises(PredictionError):
        validate_transition(
            claim,
            cancellation,
            expected_version=0,
            attempt_id="attempt-1",
            fence=1,
            now=ENDED,
        )
    with pytest.raises(PredictionError):
        validate_transition(
            current,
            claim,
            expected_version=0,
            attempt_id="unexpected",
            fence=1,
            now=STARTED,
        )
    with pytest.raises(PredictionError):
        validate_transition(
            current, claim, expected_version=0, attempt_id=None, fence=None, now=ENDED
        )
    with pytest.raises(PredictionError):
        validate_transition(
            claim,
            replace(
                state_record("failed"),
                version=2,
                attempt=replace(claim.attempt, worker_id="other"),
            ),
            expected_version=1,
            attempt_id="attempt-1",
            fence=1,
            now=ENDED,
        )


@pytest.mark.parametrize(
    "change",
    [
        {"progress_basis_points": -1},
        {"progress_basis_points": 10001},
        {"progress_basis_points": True},
        {"started_at": None},
        {"attempt": None},
        {"cancellation_requested": True},
        {"termination_confirmed": True},
        {"ended_at": ENDED},
        {"version": -1},
        {"retry_of_job_id": "job-1"},
        {"submitted_at": ENDED},
    ],
)
def test_running_state_invariants(change: dict[str, object]) -> None:
    with pytest.raises(PredictionError):
        PredictionJob.from_dict(running().to_dict() | change)


def test_explicit_progress_and_terminal_requirements() -> None:
    for value in (None, 0, 10000):
        assert (
            replace(running(), progress_basis_points=value).progress_basis_points
            == value
        )
    for state, change in (
        ("cancelled", {"termination_confirmed": False}),
        ("cancelled", {"cancellation_requested": False}),
        ("succeeded", {"result": None}),
        ("succeeded", {"manifest": None}),
        ("failed", {"failure": None}),
        ("cancelling", {"cancellation_requested": False}),
        ("queued", {"started_at": STARTED}),
        ("queued", {"stage": "preparing"}),
    ):
        with pytest.raises(PredictionError):
            PredictionJob.from_dict(
                state_record(cast(JobState, state)).to_dict() | change
            )
    succeeded = state_record("succeeded")
    assert succeeded.attempt is not None
    with pytest.raises(PredictionError):
        replace(succeeded, ended_at=EXPIRES)
    with pytest.raises(PredictionError):
        replace(succeeded, attempt=replace(succeeded.attempt, fenced=True))


def test_heartbeat_renewal_cannot_revive_expired_lease() -> None:
    current = running()
    assert current.attempt is not None
    renewed = replace(
        current,
        version=2,
        attempt=replace(
            current.attempt, heartbeat_at=ENDED, lease_expires_at="2026-11-10T10:02:01Z"
        ),
    )
    assert renewed.attempt is not None
    validate_heartbeat(current, renewed, expected_version=1)
    for old, proposed, version in (
        (current, renewed, 0),
        (queued(), renewed, 0),
        (current, replace(renewed, version=3), 1),
        (current, replace(renewed, attempt=replace(renewed.attempt, fence=2)), 1),
        (
            current,
            replace(renewed, attempt=replace(renewed.attempt, heartbeat_at=EXPIRES)),
            1,
        ),
        (replace(current, attempt=replace(current.attempt, fenced=True)), renewed, 1),
    ):
        with pytest.raises(PredictionError):
            validate_heartbeat(old, proposed, expected_version=version)
    for change in (
        {"fence": 0},
        {"fence": True},
        {"worker_id": "/private/path"},
        {"heartbeat_at": SUBMITTED},
        {"lease_expires_at": STARTED},
    ):
        with pytest.raises(PredictionError):
            type(current.attempt).from_dict(current.attempt.to_dict() | change)


def test_retry_creates_new_linked_queued_job_without_rewriting_old_spec() -> None:
    previous = state_record("failed")
    retry = replace(
        queued(previous.spec),
        job_id="job-2",
        retry_of_job_id="job-1",
        submitted_at=ENDED,
    )
    before = previous.to_json()
    validate_retry(previous, retry)
    assert retry.spec_hash == previous.spec_hash and previous.to_json() == before
    for old, new in (
        (running(), retry),
        (previous, queued()),
        (previous, replace(retry, retry_of_job_id="other")),
        (previous, replace(retry, submitted_at=SUBMITTED)),
    ):
        with pytest.raises(PredictionError):
            validate_retry(old, new)


def test_failure_can_fence_attempt_and_preserves_cancellation_history() -> None:
    current = state_record("cancelling")
    assert current.attempt is not None
    proposed = replace(
        state_record("failed"),
        version=3,
        cancellation_requested=True,
        attempt=replace(current.attempt, fenced=True),
    )
    validate_transition(
        current,
        proposed,
        expected_version=2,
        attempt_id="attempt-1",
        fence=1,
        now=ENDED,
    )
    with pytest.raises(PredictionError):
        validate_transition(
            current,
            replace(proposed, cancellation_requested=False),
            expected_version=2,
            attempt_id="attempt-1",
            fence=1,
            now=ENDED,
        )
    with pytest.raises(PredictionError) as error:
        validate_success_eligibility(
            running(),
            expected_version=1,
            attempt_id="attempt-1",
            fence=1,
            now="invalid UTC /private/path",
        )
    assert error.value.code is E.INVALID_REPRESENTATION
    assert "/private/path" not in str(error.value)

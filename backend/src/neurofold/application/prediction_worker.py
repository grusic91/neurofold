"""Single-capacity supervisor. Child lifetime is independent of HTTP awaiters."""

import errno
import json
import logging
import os
import socket
import stat
import time
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from threading import Event
from uuid import uuid4

from neurofold.application.predictions import PredictionService
from neurofold.core.errors import ArchiveIntegrityError, InvalidChildOutput
from neurofold.core.orchestration import (
    Child,
    ChildLauncher,
    FailureReason,
    IdentifiedChild,
    LaunchCleanupError,
    OrchestrationError,
)
from neurofold.core.prediction_base import PredictionError
from neurofold.core.prediction_bundle import MAX_BUNDLE_BYTES, ChildBundle
from neurofold.core.prediction_jobs import TERMINAL, PredictionJob, instant

# Only fixed authored validation messages may enter operator logs.
# Wrapped parser/data errors fall back rather than echoing retained input.
_AUTHORED_INTEGRITY_MESSAGES = frozenset(
    {
        "Artifact size/checksum mismatch",
        "Cannot read pinned reference dependency",
        "Cannot read retained variant",
        "Cannot read variant reference dependency",
        "Failure on nonfailed job",
        "Incomplete retained registration graph",
        "Invalid operational failure",
        "Invalid publication graph",
        "Mapping registration mismatch",
        "Missing committed publication",
        "Missing operational failure extension",
        "Not a retained success",
        "Operational failure mismatch",
        "Prediction database integrity failure",
        "Prediction database schema/integrity invalid",
        "Publication dependency no longer eligible",
        "Reference repository identity mismatch",
        "Reference repository returned a different ID",
        "Registered artifact changed",
        "Registered record changed",
        "Registration conflict",
        "Retained graph mismatch",
        "Retained operational failure invalid",
        "Retained prediction database missing",
        "Retained prediction database missing/invalid",
        "Retained prediction graph damaged",
        "Retained prediction job invalid",
        "Retained roots mismatch",
        "Symlink database path unsupported",
        "Symlink prediction record",
        "Symlink variant records are unsupported",
        "Variant reference dependency missing",
        "Variant repository identity mismatch",
    }
)


def integrity_message(error: ArchiveIntegrityError) -> str:
    message = str(error)
    return (
        message
        if message in _AUTHORED_INTEGRITY_MESSAGES
        else "Retained archive validation failed"
    )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class SupervisionInterrupted(RuntimeError):
    def __init__(self, reason: FailureReason) -> None:
        self.reason = reason


class PredictionWorker:
    def __init__(
        self,
        service: PredictionService,
        launcher: ChildLauncher,
        staging: Path,
        *,
        lease_seconds: float = 60,
        heartbeat_seconds: float = 5,
        poll_seconds: float = 0.1,
    ) -> None:
        if not 0 < poll_seconds <= heartbeat_seconds < lease_seconds / 2:
            raise ValueError("Invalid supervision budgets")
        self.service, self.launcher, self.staging = service, launcher, staging
        self.lease_seconds, self.heartbeat_seconds, self.poll_seconds = (
            lease_seconds,
            heartbeat_seconds,
            poll_seconds,
        )
        self.worker_id = "worker-" + uuid4().hex
        self.stop = Event()
        self.blocked_reason: str | None = None
        self.block_path = staging / "worker-block.json"

    @property
    def exit_code(self) -> int:
        return {None: 0, "UNCONFIRMED_CLEANUP": 78, "ARCHIVE_INTEGRITY": 65}[
            self.blocked_reason
        ]

    def _retry[T](
        self,
        operation: Callable[[], T],
        *,
        allow_stopping: bool = False,
        retry_conflicts: bool = False,
    ) -> T:
        until, delay = time.monotonic() + min(2, self.lease_seconds / 4), 0.01
        waiter = Event() if allow_stopping else self.stop
        while True:
            try:
                return operation()
            except OrchestrationError as exc:
                retryable = exc.code == "PREDICTION_BUSY" or (
                    retry_conflicts and exc.code == "JOB_CONFLICT"
                )
                if not retryable or time.monotonic() >= until:
                    raise
                if waiter.wait(delay):
                    raise SupervisionInterrupted("SHUTDOWN") from exc
                delay = min(delay * 2, 0.2)

    def _record_cleanup_outcome(self, owner: PredictionJob) -> bool:
        current = self.service.jobs.get(owner.job_id)
        if current.attempt != owner.attempt:
            return False
        if current.state in TERMINAL:
            return (
                current.state == "failed"
                and self.service.jobs.failure(owner.job_id).cause
                == "SUPERVISION_FAILED"
            )
        self.service.jobs.finish(current, "SUPERVISION_FAILED", terminated=False)
        return True

    def _block_cleanup(
        self,
        owner: PredictionJob,
        child: Child,
        error: Exception,
        *,
        child_launched_at: str | None = None,
    ) -> None:
        self.blocked_reason = "UNCONFIRMED_CLEANUP"
        assert owner.attempt is not None
        try:
            value = child.process_id if isinstance(child, IdentifiedChild) else None
            pid = value if type(value) is int and value > 0 else None
            value = (
                child.process_group_id if isinstance(child, IdentifiedChild) else None
            )
            pgid = value if type(value) is int and value > 0 else None
        except Exception:
            pid = pgid = None  # Diagnostics must not prevent outcome recording.
        try:
            host_id: str | None = socket.gethostname()
        except Exception:
            host_id = None  # A diagnostic lookup must not interrupt quarantine.
        record = {
            "schema_version": "neurofold-worker-block/1",
            "reason": self.blocked_reason,
            "worker_id": self.worker_id,
            "job_id": owner.job_id,
            "attempt_id": owner.attempt.attempt_id,
            "process_id": pid,
            "process_group_id": pgid,
            "error_type": type(error).__name__,
            "created_at": _utc_now(),
            "host_id": host_id,
            "child_launched_at": child_launched_at,
        }
        retained = False
        try:
            self.staging.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor = os.open(
                self.block_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
            )
            with os.fdopen(descriptor, "w") as stream:
                json.dump(record, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            folder = os.open(self.staging, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(folder)
            finally:
                os.close(folder)
            retained = True
        except OSError:
            # A partial/existing marker also blocks restart. Never remove it.
            pass
        recorded = False
        try:
            recorded = self._retry(
                partial(self._record_cleanup_outcome, owner),
                allow_stopping=True,
                retry_conflicts=True,
            )
        except Exception:
            pass  # Retained block and nonzero exit require manual reconciliation.
        finally:
            self.stop.set()
            logging.getLogger(__name__).critical(
                "worker blocked reason=%s worker_id=%s job=%s attempt=%s "
                "pid=%s pgid=%s "
                "error_type=%s block_retained=%s outcome_recorded=%s exit_code=78",
                self.blocked_reason,
                self.worker_id,
                owner.job_id,
                owner.attempt.attempt_id,
                pid,
                pgid,
                type(error).__name__,
                retained,
                recorded,
            )

    @staticmethod
    def _read_bundle(directory: Path, checkpoint: Callable[[], None]) -> bytes:
        # Nonblocking open followed by fstat rejects FIFOs/devices before reading.
        folder = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            descriptor = os.open(
                "bundle.json",
                os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
                dir_fd=folder,
            )
        finally:
            os.close(folder)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BUNDLE_BYTES:
                raise ValueError("Output must be a bounded regular file")
            chunks: list[bytes] = []
            size = 0
            while True:
                checkpoint()
                chunk = os.read(descriptor, min(65536, MAX_BUNDLE_BYTES + 1 - size))
                if not chunk:
                    return b"".join(chunks)
                size += len(chunk)
                if size > MAX_BUNDLE_BYTES:
                    raise ValueError("Oversized output")
                chunks.append(chunk)
        finally:
            os.close(descriptor)

    def once(self) -> bool:
        if self.blocked_reason is not None:
            self.stop.set()
            return False
        if self.stop.is_set():
            return False
        marker_present, check_errno = True, "NONE"
        try:
            os.lstat(self.block_path)
        except FileNotFoundError:
            marker_present = False
        except OSError as exc:
            check_errno = errno.errorcode.get(exc.errno or 0, "UNKNOWN")
        if marker_present:
            self.blocked_reason = "UNCONFIRMED_CLEANUP"
            self.stop.set()
            logging.getLogger(__name__).critical(
                "worker blocked reason=UNCONFIRMED_CLEANUP "
                "retained_record=worker-block.json manual_recovery_required=true "
                "check_errno=%s exit_code=78",
                check_errno,
            )
            return False
        jobs = self.service.jobs
        self._retry(jobs.recover)
        job = self._retry(lambda: jobs.claim(self.worker_id, self.lease_seconds))
        if job is None:
            return False
        child: Child | None = None
        reason: FailureReason = "SUPERVISION_FAILED"
        confirmed = True  # No process exists until launch succeeds.
        cleanup_uncertain = False
        child_launched_at = None
        deadline = time.monotonic() + job.spec.profile.limits.max_seconds

        def checkpoint() -> None:
            if self.stop.is_set():
                raise SupervisionInterrupted("SHUTDOWN")
            assert job is not None and job.started_at is not None
            if (
                time.monotonic() >= deadline
                or (
                    instant(self.service.clock()) - instant(job.started_at)
                ).total_seconds()
                >= job.spec.profile.limits.max_seconds
            ):
                raise SupervisionInterrupted("TIMEOUT")

        try:
            assert job.attempt is not None
            directory = self.staging / job.attempt.attempt_id
            directory.mkdir(parents=True, exist_ok=False, mode=0o700)
            job = self._retry(partial(jobs.stage, job, "inference"))
            job = self._retry(partial(jobs.get, job.job_id))
            if job.state == "cancelling":
                raise SupervisionInterrupted("SUPERVISION_FAILED")
            checkpoint()
            launch = job
            child_launched_at = _utc_now()
            child = self.launcher.launch(directory, job)
            confirmed = False
            heartbeat = time.monotonic() + self.heartbeat_seconds
            while True:
                current = self._retry(partial(jobs.get, job.job_id))
                if current.attempt != job.attempt or current.state in TERMINAL:
                    # Includes fencing/recovery; never mutate from this old owner.
                    return True
                job = current  # Cancellation may advance version, not identity.
                if job.state == "cancelling":
                    break
                checkpoint()
                if time.monotonic() >= heartbeat:
                    job = self._retry(partial(jobs.renew, job, self.lease_seconds))
                    heartbeat = time.monotonic() + self.heartbeat_seconds
                code = child.poll()
                if code is not None:
                    child.reap()
                    confirmed = True
                    if code != 0:
                        reason = "CHILD_FAILED"
                        break
                    reason = "INVALID_OUTPUT"
                    data = self._read_bundle(directory, checkpoint)
                    bundle = ChildBundle.from_json(data)
                    reason = "SUPERVISION_FAILED"
                    checkpoint()
                    # Reserve ownership through the remaining bounded publication
                    # budget. Recovery cannot fence a live publishing owner.
                    job = self._retry(
                        partial(
                            jobs.renew,
                            job,
                            max(0, deadline - time.monotonic()) + self.lease_seconds,
                        )
                    )
                    job = self._retry(partial(jobs.stage, job, "validating"))
                    reason = "PUBLICATION_FAILED"
                    try:
                        self.service.publish(job, bundle, launch, checkpoint=checkpoint)
                    except (PredictionError, InvalidChildOutput):
                        reason = "INVALID_OUTPUT"
                        raise
                    return True
                self.stop.wait(self.poll_seconds)
        except LaunchCleanupError as exc:
            child, confirmed = exc.child, False
            reason = "SUPERVISION_FAILED"
        except SupervisionInterrupted as exc:
            reason = exc.reason
        except Exception:
            # Classify the cause, including deadline/shutdown during publication.
            try:
                checkpoint()
            except SupervisionInterrupted as exc:
                reason = exc.reason
        finally:
            if child is not None and not confirmed:
                try:
                    child.terminate_and_reap()
                    confirmed = True
                except Exception as exc:
                    reason = "SUPERVISION_FAILED"
                    cleanup_uncertain = True
                    self._block_cleanup(
                        job, child, exc, child_launched_at=child_launched_at
                    )
        if cleanup_uncertain:
            return True
        # Re-read only to observe cancellation; never adopt another lease/attempt.
        current = self._retry(partial(jobs.get, job.job_id))
        if current.state not in TERMINAL and current.attempt == job.attempt:
            try:
                jobs.finish(current, reason, terminated=confirmed)
            except Exception:
                # Lost lease/IO uncertainty: leave durable recovery to fence it.
                pass
        return True

    def run(self) -> None:
        delay = 0.05
        while not self.stop.is_set():
            try:
                if not self.once():
                    self.stop.wait(1)
                delay = 0.05
            except SupervisionInterrupted:
                if self.stop.is_set():
                    return
            except OrchestrationError as exc:
                if exc.code != "PREDICTION_BUSY":
                    raise
                logging.getLogger(__name__).warning("worker contention; retrying")
                self.stop.wait(delay)
                delay = min(delay * 2, 1)
            except ArchiveIntegrityError as exc:
                # Fail closed for the whole queue. Preserve every corrupt byte;
                # an operator must inspect/restore storage and restart explicitly.
                self.blocked_reason = "ARCHIVE_INTEGRITY"
                logging.getLogger(__name__).critical(
                    "worker blocked reason=ARCHIVE_INTEGRITY exit_code=65 "
                    "error_type=%s message=%s; operator recovery and restart required",
                    type(exc).__name__,
                    integrity_message(exc),
                )
                while not self.stop.wait(1):
                    pass

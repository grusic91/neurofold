"""Single-capacity supervisor. Child lifetime is independent of HTTP awaiters."""

import time
from pathlib import Path
from threading import Event
from uuid import uuid4

from neurofold.application.predictions import PredictionService
from neurofold.core.orchestration import Child, ChildLauncher, FailureReason
from neurofold.core.prediction_bundle import MAX_BUNDLE_BYTES, ChildBundle
from neurofold.core.prediction_jobs import TERMINAL


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

    def once(self) -> bool:
        if self.stop.is_set():
            return False
        jobs = self.service.jobs
        jobs.recover()
        job = jobs.claim(self.worker_id, self.lease_seconds)
        if job is None:
            return False
        child: Child | None = None
        reason: FailureReason = "SUPERVISION_FAILED"
        confirmed = False
        try:
            assert job.attempt is not None
            directory = self.staging / job.attempt.attempt_id
            directory.mkdir(parents=True, exist_ok=False, mode=0o700)
            job = jobs.stage(job, "inference")
            launch = job
            child = self.launcher.launch(directory, job)
            deadline = time.monotonic() + job.spec.profile.limits.max_seconds
            heartbeat = time.monotonic() + self.heartbeat_seconds
            while True:
                current = jobs.get(job.job_id)
                if current.attempt != job.attempt or current.state in TERMINAL:
                    # Includes fencing/recovery; never mutate from this old owner.
                    return True
                job = current  # Cancellation may advance version, not identity.
                if job.state == "cancelling":
                    break
                if self.stop.is_set():
                    reason = "SHUTDOWN"
                    break
                if time.monotonic() >= deadline:
                    reason = "TIMEOUT"
                    break
                if time.monotonic() >= heartbeat:
                    job = jobs.renew(job, self.lease_seconds)
                    heartbeat = time.monotonic() + self.heartbeat_seconds
                code = child.poll()
                if code is not None:
                    child.reap()
                    confirmed = True
                    if code != 0:
                        reason = "CHILD_FAILED"
                        break
                    reason = "INVALID_OUTPUT"
                    path = directory / "bundle.json"
                    if path.is_symlink():
                        raise ValueError("Symlink output")
                    with path.open("rb") as source:
                        data = source.read(MAX_BUNDLE_BYTES + 1)
                    if len(data) > MAX_BUNDLE_BYTES:
                        raise ValueError("Oversized output")
                    bundle = ChildBundle.from_json(data)
                    job = jobs.stage(job, "validating")
                    reason = "PUBLICATION_FAILED"
                    self.service.publish(job, bundle, launch)
                    return True
                self.stop.wait(self.poll_seconds)
        except Exception:
            # Public failure contains only enumerated status, never child logs.
            pass
        finally:
            if child is not None and not confirmed:
                child.terminate_and_reap()
                confirmed = True
        # Re-read only to observe cancellation; never adopt another lease/attempt.
        current = jobs.get(job.job_id)
        if current.state not in TERMINAL and current.attempt == job.attempt:
            try:
                jobs.finish(current, reason, terminated=confirmed)
            except Exception:
                # Lost lease/IO uncertainty: leave durable recovery to fence it.
                pass
        return True

    def run(self) -> None:
        while not self.stop.is_set():
            if not self.once():
                self.stop.wait(1)

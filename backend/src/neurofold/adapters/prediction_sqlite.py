"""Durable local job metadata. No SQL or sqlite dependency escapes this adapter."""

import fcntl
import os
import sqlite3
import tempfile
import time
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from neurofold.core.canonical import canonical_json, sha256_bytes
from neurofold.core.errors import ArchiveIntegrityError
from neurofold.core.orchestration import (
    Clock,
    FailureReason,
    OrchestrationError,
    Publication,
)
from neurofold.core.prediction_base import PredictionErrorCode as E
from neurofold.core.prediction_base import ValidationStage as S
from neurofold.core.prediction_failure import OperationalFailure
from neurofold.core.prediction_inputs import PredictionSpec
from neurofold.core.prediction_jobs import (
    TERMINAL,
    PredictionAttempt,
    PredictionFailure,
    PredictionJob,
    instant,
    validate_heartbeat,
    validate_retry,
    validate_success_eligibility,
    validate_transition,
)
from neurofold.core.provenance import ContentReference


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def after(now: str, seconds: float) -> str:
    return (
        (instant(now) + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")
    )


SCHEMA = (
    "CREATE TABLE jobs (id TEXT PRIMARY KEY, state TEXT NOT NULL, "
    "version INTEGER NOT NULL, "
    "body BLOB NOT NULL, sha TEXT NOT NULL, reason TEXT)",
    "CREATE TABLE attempts (id TEXT PRIMARY KEY, "
    "job TEXT UNIQUE NOT NULL REFERENCES jobs(id), "
    "fence INTEGER UNIQUE NOT NULL, body BLOB NOT NULL)",
    "CREATE TABLE idempotency (key TEXT PRIMARY KEY, "
    "job TEXT NOT NULL REFERENCES jobs(id), "
    "spec BLOB NOT NULL, retry TEXT)",
    "CREATE TABLE registrations (kind TEXT NOT NULL, "
    "id TEXT NOT NULL, sha TEXT NOT NULL, "
    "size INTEGER NOT NULL, PRIMARY KEY(kind,id))",
    "CREATE TABLE publications (id TEXT PRIMARY KEY, "
    "job TEXT UNIQUE NOT NULL REFERENCES jobs(id), "
    "owner BLOB NOT NULL, body BLOB, status TEXT NOT NULL)",
    "CREATE TRIGGER immutable_registration_update BEFORE UPDATE ON registrations "
    "BEGIN SELECT RAISE(ABORT, 'immutable registration'); END",
    "CREATE TRIGGER immutable_registration_delete BEFORE DELETE ON registrations "
    "BEGIN SELECT RAISE(ABORT, 'retained registration'); END",
)


FAILURE_SCHEMA = (
    "CREATE TABLE legacy_failures (job TEXT PRIMARY KEY REFERENCES jobs(id))",
    "CREATE TABLE failures (job TEXT PRIMARY KEY REFERENCES jobs(id), "
    "body BLOB NOT NULL, sha TEXT NOT NULL)",
    "CREATE TRIGGER immutable_failure_update BEFORE UPDATE ON failures "
    "BEGIN SELECT RAISE(ABORT, 'immutable failure'); END",
    "CREATE TRIGGER immutable_failure_delete BEFORE DELETE ON failures "
    "BEGIN SELECT RAISE(ABORT, 'retained failure'); END",
)


class SQLiteJobs:
    def __init__(
        self, path: Path, *, clock: Clock = utc_now, max_queued: int = 100
    ) -> None:
        path = path.absolute()
        self.path, self.clock, self.max_queued = path, clock, max_queued
        self.initialized = False
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ArchiveIntegrityError("Symlink database path unsupported")
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Serialize first creation including WAL selection and marker publication.
        with path.with_suffix(".init-lock").open("a+b") as lock:
            deadline = time.monotonic() + 1
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise OrchestrationError("PREDICTION_BUSY") from None
                    time.sleep(0.01)
            marker = path.with_suffix(".identity")
            retained = marker.exists() or marker.is_symlink()
            if retained and (
                marker.is_symlink()
                or marker.read_bytes() != b"neurofold-prediction-sqlite/1"
                or not path.is_file()
            ):
                raise ArchiveIntegrityError(
                    "Retained prediction database missing/invalid"
                )
            fresh = not path.exists() and not retained
            if not fresh:
                self.initialized = True  # rw mode must never recreate retained history.
            with self._connection() as connection:
                if fresh:
                    connection.execute("PRAGMA journal_mode=WAL")
                    connection.execute("BEGIN IMMEDIATE")
                    for statement in SCHEMA:
                        connection.execute(statement)
                    connection.execute("PRAGMA user_version=1")
                    connection.commit()
                self._validate_database(connection)
                if connection.execute("PRAGMA user_version").fetchone() == (1,):
                    connection.execute("BEGIN IMMEDIATE")
                    for statement in FAILURE_SCHEMA:
                        connection.execute(statement)
                    connection.execute(
                        "INSERT INTO legacy_failures SELECT id FROM jobs "
                        "WHERE state='failed'"
                    )
                    connection.execute("PRAGMA user_version=2")
                    connection.commit()
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                try:
                    stream.write(b"neurofold-prediction-sqlite/1")
                    stream.flush()
                    os.fsync(stream.fileno())
                    try:
                        os.link(temporary, marker)
                    except FileExistsError:
                        pass  # Already validated under the initialization lock.
                    directory = os.open(path.parent, os.O_RDONLY)
                    try:
                        os.fsync(directory)
                    finally:
                        os.close(directory)
                finally:
                    temporary.unlink()
        self.initialized = True

    @staticmethod
    def _validate_database(connection: sqlite3.Connection) -> None:
        with closing(sqlite3.connect(":memory:")) as expected:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            for statement in (*SCHEMA, *(FAILURE_SCHEMA if version == 2 else ())):
                expected.execute(statement)
            query = "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY name"
            if (
                version not in (1, 2)
                or connection.execute(query).fetchall()
                != expected.execute(query).fetchall()
                or connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]
                or connection.execute("PRAGMA foreign_key_check").fetchall()
            ):
                raise ArchiveIntegrityError(
                    "Prediction database schema/integrity invalid"
                )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection: sqlite3.Connection | None = None
        if self.initialized and not self.path.is_file():
            raise ArchiveIntegrityError("Retained prediction database missing")
        try:
            connection = sqlite3.connect(
                self.path.as_uri() + "?mode=rw" if self.initialized else self.path,
                uri=self.initialized,
                timeout=1,
                isolation_level=None,
            )
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA synchronous=FULL")
            yield connection
        except sqlite3.OperationalError as exc:
            if getattr(exc, "sqlite_errorcode", None) in (
                sqlite3.SQLITE_BUSY,
                sqlite3.SQLITE_LOCKED,
            ):
                raise OrchestrationError("PREDICTION_BUSY") from exc
            raise OrchestrationError("PREDICTION_UNAVAILABLE") from exc
        except sqlite3.DatabaseError as exc:
            raise ArchiveIntegrityError(
                "Prediction database integrity failure"
            ) from exc
        finally:
            if connection is not None:
                if connection.in_transaction:
                    connection.rollback()
                connection.close()

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            try:
                connection.commit()
            except sqlite3.DatabaseError as exc:
                if getattr(exc, "sqlite_errorcode", None) in (
                    sqlite3.SQLITE_BUSY,
                    sqlite3.SQLITE_LOCKED,
                ):
                    raise OrchestrationError("PREDICTION_BUSY") from exc
                raise OrchestrationError("PREDICTION_MUTATION_UNCERTAIN") from exc

    def _get(self, connection: sqlite3.Connection, job_id: str) -> PredictionJob:
        row = connection.execute(
            "SELECT state,version,body,sha FROM jobs WHERE id=?", (job_id,)
        ).fetchone()
        if row is None:
            raise KeyError(job_id)
        try:
            job = PredictionJob.from_json(row[2])
            if (
                job.job_id != job_id
                or job.state != row[0]
                or job.version != row[1]
                or sha256_bytes(row[2]) != row[3]
            ):
                raise ValueError("Job checksum/index mismatch")
            if job.attempt is not None:
                attempt = connection.execute(
                    "SELECT body,fence FROM attempts WHERE id=? AND job=?",
                    (job.attempt.attempt_id, job_id),
                ).fetchone()
                if attempt != (job.attempt.to_json(), job.attempt.fence):
                    raise ValueError("Attempt mismatch")
            return job
        except (ValueError, TypeError) as exc:
            raise ArchiveIntegrityError("Retained prediction job invalid") from exc

    def get(self, job_id: str) -> PredictionJob:
        with self._connection() as connection:
            connection.execute("BEGIN")
            return self._get(connection, job_id)

    def reason(self, job_id: str) -> FailureReason | None:
        return self.snapshot(job_id)[1]

    def snapshot(self, job_id: str) -> tuple[PredictionJob, FailureReason | None]:
        with self._connection() as connection:
            connection.execute("BEGIN")
            job = self._get(connection, job_id)
            reason = connection.execute(
                "SELECT reason FROM jobs WHERE id=?", (job_id,)
            ).fetchone()[0]
            allowed: tuple[FailureReason, ...] = (
                "WORKER_LOST",
                "TIMEOUT",
                "SHUTDOWN",
                "CHILD_FAILED",
                "INVALID_OUTPUT",
                "PUBLICATION_FAILED",
                "SUPERVISION_FAILED",
            )
            row = connection.execute(
                "SELECT body,sha FROM failures WHERE job=?", (job_id,)
            ).fetchone()
            if row is not None:
                failure = self._failure(job, row)
                if failure.cause != reason:
                    raise ArchiveIntegrityError("Operational failure mismatch")
            elif (
                job.state == "failed"
                and not connection.execute(
                    "SELECT 1 FROM legacy_failures WHERE job=?", (job_id,)
                ).fetchone()
            ):
                raise ArchiveIntegrityError("Missing operational failure extension")
            if reason is None:
                return job, None
            if job.state != "failed":
                raise ArchiveIntegrityError("Failure on nonfailed job")
            for value in allowed:
                if reason == value:
                    return job, value
            raise ArchiveIntegrityError("Invalid operational failure")

    @staticmethod
    def _failure(job: PredictionJob, row: tuple[bytes, str]) -> OperationalFailure:
        try:
            value = OperationalFailure.from_json(row[0])
            if (
                sha256_bytes(row[0]) != row[1]
                or value.job
                != ContentReference(record_id=job.job_id, content_hash=job.content_hash)
                or job.attempt is None
                or value.attempt_id != job.attempt.attempt_id
                or value.ended_at != job.ended_at
                or job.state != "failed"
            ):
                raise ValueError("Failure linkage mismatch")
            return value
        except (ValueError, TypeError) as exc:
            raise ArchiveIntegrityError("Retained operational failure invalid") from exc

    def failure(self, job_id: str) -> OperationalFailure:
        with self._connection() as connection:
            connection.execute("BEGIN")
            job = self._get(connection, job_id)
            row = connection.execute(
                "SELECT body,sha FROM failures WHERE job=?", (job_id,)
            ).fetchone()
            if row is None:
                if (
                    job.state == "failed"
                    and not connection.execute(
                        "SELECT 1 FROM legacy_failures WHERE job=?", (job_id,)
                    ).fetchone()
                ):
                    raise ArchiveIntegrityError("Missing operational failure extension")
                raise OrchestrationError("JOB_CONFLICT")
            return self._failure(job, row)

    def _save(
        self,
        connection: sqlite3.Connection,
        job: PredictionJob,
        reason: FailureReason | None = None,
    ) -> None:
        body = job.to_json()
        if reason is not None:
            assert job.attempt is not None and job.ended_at is not None
            failure = OperationalFailure(
                job=ContentReference(
                    record_id=job.job_id, content_hash=job.content_hash
                ),
                attempt_id=job.attempt.attempt_id,
                cause=reason,
                ended_at=job.ended_at,
            ).to_json()
            connection.execute(
                "INSERT INTO failures VALUES(?,?,?)",
                (job.job_id, failure, sha256_bytes(failure)),
            )
        connection.execute(
            "UPDATE jobs SET state=?,version=?,body=?,sha=?,reason=? WHERE id=?",
            (job.state, job.version, body, sha256_bytes(body), reason, job.job_id),
        )
        if job.attempt is not None:
            connection.execute(
                "INSERT INTO attempts VALUES(?,?,?,?) ON CONFLICT(id) "
                "DO UPDATE SET body=excluded.body",
                (
                    job.attempt.attempt_id,
                    job.job_id,
                    job.attempt.fence,
                    job.attempt.to_json(),
                ),
            )

    def submit(
        self, spec: PredictionSpec, key: str, retry: str | None, *, available: bool
    ) -> PredictionJob:
        import re

        if type(key) is not str or re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", key) is None:
            raise OrchestrationError("INVALID_IDEMPOTENCY_KEY")
        with self._write() as connection:
            retained = connection.execute(
                "SELECT job,spec,retry FROM idempotency WHERE key=?", (key,)
            ).fetchone()
            if retained is not None:
                if retained[1:] != (spec.to_json(), retry):
                    raise OrchestrationError("IDEMPOTENCY_CONFLICT")
                return self._get(connection, retained[0])
            job = PredictionJob(
                job_id="job-" + uuid4().hex,
                spec=spec,
                spec_hash=spec.content_hash,
                state="queued",
                version=0,
                submitted_at=self.clock(),
                started_at=None,
                ended_at=None,
                attempt=None,
                cancellation_requested=False,
                termination_confirmed=False,
                retry_of_job_id=retry,
                stage="queued",
                progress_basis_points=None,
                failure=None,
                result=None,
                manifest=None,
            )
            if retry is not None:
                validate_retry(self._get(connection, retry), job)
            if not available:
                raise OrchestrationError("PROFILE_UNAVAILABLE")
            count = connection.execute(
                "SELECT count(*) FROM jobs WHERE state='queued'"
            ).fetchone()[0]
            if count >= self.max_queued:
                raise OrchestrationError("PREDICTION_QUEUE_FULL")
            body = job.to_json()
            connection.execute(
                "INSERT INTO jobs VALUES(?,?,?,?,?,NULL)",
                (job.job_id, job.state, job.version, body, sha256_bytes(body)),
            )
            connection.execute(
                "INSERT INTO idempotency VALUES(?,?,?,?)",
                (key, job.job_id, spec.to_json(), retry),
            )
            return job

    def _transition(
        self,
        connection: sqlite3.Connection,
        current: PredictionJob,
        proposed: PredictionJob,
        now: str,
        reason: FailureReason | None = None,
    ) -> PredictionJob:
        validate_transition(
            current,
            proposed,
            expected_version=current.version,
            attempt_id=current.attempt.attempt_id if current.attempt else None,
            fence=current.attempt.fence if current.attempt else None,
            now=now,
        )
        self._save(connection, proposed, reason)
        return proposed

    def claim(self, worker_id: str, lease_seconds: float = 60) -> PredictionJob | None:
        with self._write() as connection:
            if connection.execute(
                "SELECT 1 FROM jobs WHERE state IN ('running','cancelling') LIMIT 1"
            ).fetchone():
                return None
            row = connection.execute(
                "SELECT id FROM jobs WHERE state='queued' ORDER BY rowid LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            job, now = self._get(connection, row[0]), self.clock()
            fence = connection.execute(
                "SELECT coalesce(max(fence),0)+1 FROM attempts"
            ).fetchone()[0]
            return self._transition(
                connection,
                job,
                replace(
                    job,
                    state="running",
                    version=job.version + 1,
                    started_at=now,
                    stage="preparing",
                    attempt=PredictionAttempt(
                        attempt_id="attempt-" + uuid4().hex,
                        worker_id=worker_id,
                        lease_id="lease-" + uuid4().hex,
                        fence=fence,
                        started_at=now,
                        heartbeat_at=now,
                        lease_expires_at=after(now, lease_seconds),
                        fenced=False,
                    ),
                ),
                now,
            )

    def _owner(
        self, connection: sqlite3.Connection, owner: PredictionJob, *, live: bool = True
    ) -> PredictionJob:
        current = self._get(connection, owner.job_id)
        if (
            current.version != owner.version
            or current.state not in ("running", "cancelling")
            or current.attempt != owner.attempt
            or current.attempt is None
            or current.attempt.fenced
        ):
            raise OrchestrationError("JOB_CONFLICT")
        if live and not instant(current.attempt.heartbeat_at) <= instant(
            self.clock()
        ) < instant(current.attempt.lease_expires_at):
            raise OrchestrationError("JOB_CONFLICT")
        return current

    def cancel(self, job_id: str) -> PredictionJob:
        with self._write() as connection:
            job, now = self._get(connection, job_id), self.clock()
            if job.state in ("cancelled", "cancelling"):
                return job
            if job.state in TERMINAL:
                raise OrchestrationError("JOB_CONFLICT")
            queued = job.state == "queued"
            return self._transition(
                connection,
                job,
                replace(
                    job,
                    state="cancelled" if queued else "cancelling",
                    version=job.version + 1,
                    cancellation_requested=True,
                    termination_confirmed=queued,
                    ended_at=now if queued else None,
                    stage="finished" if queued else job.stage,
                ),
                now,
            )

    def renew(self, owner: PredictionJob, lease_seconds: float = 60) -> PredictionJob:
        with self._write() as connection:
            job, now = self._owner(connection, owner), self.clock()
            assert job.attempt is not None
            proposed = replace(
                job,
                version=job.version + 1,
                attempt=replace(
                    job.attempt,
                    heartbeat_at=now,
                    lease_expires_at=max(
                        job.attempt.lease_expires_at,
                        after(now, lease_seconds),
                        key=instant,
                    ),
                ),
            )
            validate_heartbeat(job, proposed, expected_version=job.version)
            self._save(connection, proposed)
            return proposed

    def stage(self, owner: PredictionJob, stage: str) -> PredictionJob:
        # Decode through the strict codec rather than weakening the stage vocabulary.
        with self._write() as connection:
            job = self._owner(connection, owner)
            proposed = PredictionJob.from_dict(
                job.to_dict() | {"stage": stage, "version": job.version + 1}
            )
            self._save(connection, proposed)
            return proposed

    def finish(
        self, owner: PredictionJob, reason: FailureReason | None, *, terminated: bool
    ) -> PredictionJob:
        with self._write() as connection:
            job, now = self._owner(connection, owner), self.clock()
            cancelled = job.state == "cancelling" and terminated
            if not cancelled and reason is None:
                reason = "SUPERVISION_FAILED"
            proposed = replace(
                job,
                version=job.version + 1,
                state="cancelled" if cancelled else "failed",
                ended_at=now,
                stage="finished",
                termination_confirmed=cancelled,
                failure=None
                if cancelled
                else PredictionFailure(
                    code=E.ILLEGAL_TRANSITION, stage=S.LIFECYCLE, retryable=False
                ),
            )
            return self._transition(
                connection, job, proposed, now, None if cancelled else reason
            )

    def recover(self) -> int:
        with self._write() as connection:
            now, count = self.clock(), 0
            for (job_id,) in connection.execute(
                "SELECT id FROM jobs WHERE state IN ('running','cancelling')"
            ).fetchall():
                job = self._get(connection, job_id)
                assert job.attempt is not None
                if instant(now) < instant(job.attempt.lease_expires_at):
                    continue
                proposed = replace(
                    job,
                    state="failed",
                    version=job.version + 1,
                    stage="finished",
                    ended_at=now,
                    attempt=replace(job.attempt, fenced=True),
                    failure=PredictionFailure(
                        code=E.ILLEGAL_TRANSITION, stage=S.LIFECYCLE, retryable=False
                    ),
                )
                self._transition(connection, job, proposed, now, "WORKER_LOST")
                connection.execute(
                    "UPDATE publications SET status='abandoned' "
                    "WHERE job=? AND status!='committed'",
                    (job_id,),
                )
                count += 1
            return count

    def begin_publication(self, owner: PredictionJob) -> str:
        with self._write() as connection:
            job = self._owner(connection, owner)
            if job.state != "running":
                raise OrchestrationError("JOB_CONFLICT")
            identity = "publication-" + uuid4().hex
            connection.execute(
                "INSERT INTO publications VALUES(?,?,?,NULL,'pending')",
                (identity, job.job_id, job.to_json()),
            )
            return identity

    @staticmethod
    def _publication_bytes(publication: Publication) -> bytes:
        return canonical_json(
            {
                "result": publication.result.to_dict(),
                "manifest": publication.manifest.to_dict(),
                "graph": [
                    [r.kind, r.record_id, r.sha256, r.byte_size]
                    for r in publication.graph
                ],
                "validated_at": publication.validated_at,
            }
        )

    def ready(self, publication: Publication) -> None:
        with self._write() as connection:
            self._owner(connection, publication.job)
            for r in publication.graph:
                row = connection.execute(
                    "SELECT sha,size FROM registrations WHERE kind=? AND id=?",
                    (r.kind, r.record_id),
                ).fetchone()
                if row is not None and row != (r.sha256, r.byte_size):
                    raise ArchiveIntegrityError("Registration conflict")
                connection.execute(
                    "INSERT OR IGNORE INTO registrations VALUES(?,?,?,?)",
                    (r.kind, r.record_id, r.sha256, r.byte_size),
                )
            updated = connection.execute(
                "UPDATE publications SET body=?,status='ready' "
                "WHERE id=? AND owner=? AND status='pending'",
                (
                    self._publication_bytes(publication),
                    publication.intent_id,
                    publication.job.to_json(),
                ),
            )
            if updated.rowcount != 1:
                raise OrchestrationError("JOB_CONFLICT")

    def succeed(self, publication: Publication) -> PredictionJob:
        with self._write() as connection:
            job = self._owner(connection, publication.job)
            assert job.attempt is not None
            validate_success_eligibility(
                job,
                expected_version=publication.job.version,
                attempt_id=job.attempt.attempt_id,
                fence=job.attempt.fence,
                now=self.clock(),
            )
            assert job.started_at is not None
            if (
                instant(self.clock()) - instant(job.started_at)
            ).total_seconds() > job.spec.profile.limits.max_seconds:
                raise OrchestrationError("JOB_CONFLICT")
            row = connection.execute(
                "SELECT body,status,owner FROM publications WHERE id=? AND job=?",
                (publication.intent_id, job.job_id),
            ).fetchone()
            if row != (self._publication_bytes(publication), "ready", job.to_json()):
                raise OrchestrationError("JOB_CONFLICT")
            for r in publication.graph:
                retained = connection.execute(
                    "SELECT sha,size FROM registrations WHERE kind=? AND id=?",
                    (r.kind, r.record_id),
                ).fetchone()
                if retained != (r.sha256, r.byte_size):
                    raise ArchiveIntegrityError(
                        "Publication dependency no longer eligible"
                    )
            proposed = replace(
                job,
                state="succeeded",
                version=job.version + 1,
                stage="finished",
                ended_at=publication.validated_at,
                result=publication.result,
                manifest=publication.manifest,
            )
            self._transition(connection, job, proposed, publication.validated_at)
            connection.execute(
                "UPDATE publications SET status='committed' WHERE id=?",
                (publication.intent_id,),
            )
            return proposed

    def graph(self, job_id: str) -> tuple[tuple[str, str, str, int], ...]:
        from neurofold.core.canonical import parse_json

        with self._connection() as connection:
            job = self._get(connection, job_id)
            row = connection.execute(
                "SELECT body,status FROM publications WHERE job=?", (job_id,)
            ).fetchone()
            if job.state != "succeeded" or row is None or row[1] != "committed":
                raise ArchiveIntegrityError("Missing committed publication")
            assert job.result is not None and job.manifest is not None
            try:
                body = parse_json(row[0])
                if type(body) is not dict or set(body) != {
                    "result",
                    "manifest",
                    "graph",
                    "validated_at",
                }:
                    raise ValueError
                if (
                    body["result"] != job.result.to_dict()
                    or body["manifest"] != job.manifest.to_dict()
                ):
                    raise ValueError
                graph = body["graph"]
                if type(graph) is not list or not graph:
                    raise ValueError
                result: list[tuple[str, str, str, int]] = []
                for item in graph:
                    if (
                        type(item) is not list
                        or len(item) != 4
                        or any(type(x) is not str for x in item[:3])
                        or type(item[3]) is not int
                    ):
                        raise ValueError
                    kind, identity, sha, size = item
                    if connection.execute(
                        "SELECT sha,size FROM registrations WHERE kind=? AND id=?",
                        (kind, identity),
                    ).fetchone() != (sha, size):
                        raise ValueError
                    result.append((kind, identity, sha, size))
                return tuple(result)
            except (ValueError, TypeError, AttributeError) as exc:
                raise ArchiveIntegrityError("Invalid publication graph") from exc

"""Round-7 diagnostics and bounded retry contract regressions; synthetic only."""

import json
import socket
import sqlite3
from pathlib import Path

import httpx
import pytest
from prediction_test_retries import retry_busy, retry_busy_response
from test_prediction_cleanup_closure import RefusedChild
from test_prediction_durable import claimed

from neurofold.application.prediction_worker import PredictionWorker
from neurofold.core.errors import ArchiveIntegrityError
from neurofold.core.orchestration import OrchestrationError


def test_integrity_log_does_not_echo_non_authored_detail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    service, _, _ = claimed(tmp_path)
    worker = PredictionWorker(service, object(), tmp_path / "staging")  # type: ignore[arg-type]

    def damaged() -> int:
        worker.stop.set()
        raise ArchiveIntegrityError("PRIVATE_SEQUENCE_MACAG")

    monkeypatch.setattr(service.jobs, "recover", damaged)
    worker.run()
    assert worker.exit_code == 65
    assert "error_type=ArchiveIntegrityError" in caplog.text
    assert "message=Retained archive validation failed" in caplog.text
    assert "PRIVATE" not in caplog.text and "MACAG" not in caplog.text
    assert "Traceback" not in caplog.text


@pytest.mark.parametrize("error", [OSError("PRIVATE"), RuntimeError("PRIVATE")])
def test_hostname_failure_cannot_prevent_marker_or_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
) -> None:
    service, _, owner = claimed(tmp_path)
    worker = PredictionWorker(service, object(), tmp_path / "staging")  # type: ignore[arg-type]

    def unavailable() -> str:
        raise error

    monkeypatch.setattr(socket, "gethostname", unavailable)
    worker._block_cleanup(owner, RefusedChild(), PermissionError("PRIVATE"))
    marker = json.loads(worker.block_path.read_bytes())
    assert marker["host_id"] is None
    assert marker["process_id"] == marker["process_group_id"] == 4242
    assert marker["created_at"].endswith("Z")
    assert service.get(owner.job_id).state == "failed"
    assert service.jobs.failure(owner.job_id).cause == "SUPERVISION_FAILED"
    assert not service.get(owner.job_id).termination_confirmed
    assert worker.stop.is_set() and worker.exit_code == 78
    assert "block_retained=True outcome_recorded=True" in caplog.text
    assert "PRIVATE" not in caplog.text and "PRIVATE" not in json.dumps(marker)


@pytest.mark.parametrize(
    "error",
    [
        OrchestrationError("PREDICTION_BUSY"),
        sqlite3.OperationalError("database is locked"),
    ],
)
def test_busy_retry_is_bounded_and_preserves_original_error(error: Exception) -> None:
    calls = 0
    waits: list[float] = []

    def unavailable() -> None:
        nonlocal calls
        calls += 1
        raise error

    with pytest.raises(type(error)) as raised:
        retry_busy(unavailable, attempts=3, wait=waits.append)
    assert raised.value is error and calls == 3 and waits == [0.05, 0.05]


@pytest.mark.parametrize(
    "error",
    [OrchestrationError("JOB_CONFLICT"), sqlite3.OperationalError("syntax error")],
)
def test_busy_retry_never_retries_other_errors(error: Exception) -> None:
    waits: list[float] = []

    def rejected() -> None:
        raise error

    with pytest.raises(type(error)) as raised:
        retry_busy(rejected, wait=waits.append)
    assert raised.value is error and waits == []


def test_http_busy_retry_respects_retry_after_and_exhaustion() -> None:
    busy = httpx.Response(
        503,
        headers={"Retry-After": "2"},
        json={"error": {"code": "PREDICTION_BUSY", "retryable": True}},
    )
    success = httpx.Response(202, json={"job": {"job_id": "synthetic-job"}})
    replies = iter([busy, busy, success])
    waits: list[float] = []
    assert retry_busy_response(lambda: next(replies), wait=waits.append) is success
    assert waits == [2, 2]
    waits.clear()
    assert retry_busy_response(lambda: busy, attempts=3, wait=waits.append) is busy
    assert waits == [2, 2]


@pytest.mark.parametrize(
    "code", ["PREDICTION_UNAVAILABLE", "PREDICTION_MUTATION_UNCERTAIN"]
)
def test_http_busy_retry_does_not_hide_other_503_errors(code: str) -> None:
    response = httpx.Response(503, json={"error": {"code": code}})
    waits: list[float] = []
    assert retry_busy_response(lambda: response, wait=waits.append) is response
    assert waits == []

"""Bounded client-side busy recovery for storage/concurrency assertions only."""

import time
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from neurofold.core.orchestration import OrchestrationError


def retry_busy[T](
    operation: Callable[[], T],
    *,
    attempts: int = 8,
    wait: Callable[[float], None] = time.sleep,
) -> T:
    for index in range(attempts):
        try:
            return operation()
        except OrchestrationError as exc:
            if exc.code != "PREDICTION_BUSY" or index == attempts - 1:
                raise
        wait(0.05)
    raise AssertionError("Retry attempts must be positive")


class RetryResponse(Protocol):
    @property
    def status_code(self) -> int: ...

    @property
    def headers(self) -> Mapping[str, str]: ...

    def json(self) -> Any: ...


def retry_busy_response[T: RetryResponse](
    operation: Callable[[], T],
    *,
    attempts: int = 8,
    wait: Callable[[float], None] = time.sleep,
) -> T:
    for index in range(attempts):
        response = operation()
        if (
            response.status_code != 503
            or response.json()["error"]["code"] != "PREDICTION_BUSY"
            or index == attempts - 1
        ):
            return response
        assert response.json()["error"]["retryable"] is True
        delay = int(response.headers["Retry-After"])
        assert 0 <= delay <= 10, "Unexpected test-server Retry-After"
        wait(delay)
    raise AssertionError("Retry attempts must be positive")

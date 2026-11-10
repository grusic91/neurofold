"""Deterministic injectable time/retry controls and bounded replaceable indexes."""

import random
import secrets
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from threading import RLock

from neurofold.core.lookup import CursorError


@dataclass(frozen=True)
class Clock:
    monotonic: Callable[[], float] = time.monotonic
    utcnow: Callable[[], datetime] = lambda: datetime.now(UTC)
    sleep: Callable[[float], None] = time.sleep

    def stamp(self) -> str:
        return self.utcnow().astimezone(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class RetryPolicy:
    retries: int = 2
    budget: float = 15.0
    jitter: Callable[[], float] = random.random

    def __post_init__(self) -> None:
        if not 0 <= self.retries <= 2 or not 0 < self.budget <= 15:
            raise ValueError("Retries/budget exceed provider policy")

    def delay(self, attempt: int, retry_after: str | None, clock: Clock) -> float:
        backoff = min(
            2.0, 0.25 * 2.0**attempt + min(1.0, max(0.0, self.jitter())) * 0.25
        )
        if retry_after:
            try:
                seconds = float(retry_after)
                if not seconds >= 0:  # Also reject NaN.
                    seconds = 0.0
            except ValueError:
                try:
                    seconds = (
                        parsedate_to_datetime(retry_after) - clock.utcnow()
                    ).total_seconds()
                except (ValueError, TypeError, OverflowError):
                    seconds = 0.0
            return max(backoff, min(5.0, max(0.0, seconds)))
        return backoff


@dataclass
class BoundedCache[T]:
    max_entries: int = 128
    max_bytes: int = 32 * 1024 * 1024
    entries: OrderedDict[str, tuple[T, int]] = field(default_factory=OrderedDict)
    lock: RLock = field(default_factory=RLock)

    def __post_init__(self) -> None:
        if (
            not 1 <= self.max_entries <= 128
            or not 1 <= self.max_bytes <= 32 * 1024 * 1024
        ):
            raise ValueError("Cache exceeds policy bounds")

    def get(self, key: str) -> T | None:
        with self.lock:
            value = self.entries.get(key)
            if value is None:
                return None
            self.entries.move_to_end(key)
            return value[0]

    def put(self, key: str, value: T, size: int) -> None:
        with self.lock:
            self.entries.pop(key, None)
            if size > self.max_bytes:
                return
            self.entries[key] = value, size
            while (
                len(self.entries) > self.max_entries
                or sum(v[1] for v in self.entries.values()) > self.max_bytes
            ):
                self.entries.popitem(last=False)


@dataclass(frozen=True)
class Cursor:
    binding: str
    url: str
    expires: float
    page: int
    previous: str


class Cursors:
    """Opaque capabilities; clients cannot supply provider URLs or queries."""

    def __init__(
        self, clock: Clock, token: Callable[[], str] = lambda: secrets.token_urlsafe(24)
    ) -> None:
        self.clock, self.token = clock, token
        self.cache: BoundedCache[Cursor] = BoundedCache()

    def issue(
        self, binding: str, url: str, page: int, previous: str, expires: float
    ) -> str:
        token = self.token()
        if not token or len(token) > 2048 or self.cache.get(token) is not None:
            raise ValueError("Cursor token generator collision/invalid token")
        self.cache.put(
            token,
            Cursor(binding, url, expires, page, previous),
            len(url) + len(binding) + 256,
        )
        return token

    def resolve(self, token: str, binding: str) -> Cursor:
        if not 1 <= len(token) <= 2048:
            raise CursorError("Invalid cursor")
        value = self.cache.get(token)
        if value is None:
            raise CursorError("Unknown or evicted cursor")
        if value.expires <= self.clock.monotonic():
            raise CursorError("Expired cursor")
        if value.binding != binding:
            raise CursorError("Cursor provider, query or ordering mismatch")
        return value

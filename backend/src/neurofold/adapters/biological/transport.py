"""Bounded raw HTTP with an actual async deadline, behind a synchronous seam."""

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

import httpx

from neurofold.core.lookup import ProviderValidationError

MAX_DOWNLOAD = 2 * 1024 * 1024
MAX_EXPANDED = 8 * 1024 * 1024
MAX_HEADERS = 16 * 1024


class TransportFailure(RuntimeError):
    pass


class TransportTimeout(TransportFailure):
    pass


@dataclass(frozen=True)
class Response:
    status: int
    headers: Mapping[str, str]
    body: bytes = b""


class Transport(Protocol):
    def request(
        self, url: str, headers: Mapping[str, str], *, timeout: float
    ) -> Response: ...


class HttpxTransport:
    """Construct only when selected. No redirects, proxies, cookies or startup IO.

    The sync catalog must run outside an event loop (e.g. a future sync route).
    asyncio.timeout covers connect, all body chunks and cleanup per attempt;
    HTTPX's individual inactivity timeouts alone are not a whole-call deadline.
    """

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.transport = transport

    def request(
        self, url: str, headers: Mapping[str, str], *, timeout: float
    ) -> Response:
        return asyncio.run(self._request(url, headers, timeout))

    async def _request(
        self, url: str, headers: Mapping[str, str], timeout: float
    ) -> Response:
        try:
            async with asyncio.timeout(timeout):
                async with httpx.AsyncClient(
                    transport=self.transport,
                    trust_env=False,
                    follow_redirects=False,
                    timeout=httpx.Timeout(timeout, connect=min(3.0, timeout)),
                    limits=httpx.Limits(max_connections=2),
                ) as client:
                    async with client.stream("GET", url, headers=headers) as response:
                        received = dict(response.headers)
                        if (
                            sum(len(k) + len(v) for k, v in received.items())
                            > MAX_HEADERS
                        ):
                            raise ProviderValidationError(
                                "Response headers exceed limit"
                            )
                        chunks: list[bytes] = []
                        size = 0
                        async for chunk in response.aiter_raw():
                            size += len(chunk)
                            if size > MAX_DOWNLOAD:
                                raise ProviderValidationError("Download exceeds limit")
                            chunks.append(chunk)
                        return Response(
                            response.status_code, received, b"".join(chunks)
                        )
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise TransportTimeout("HTTP deadline exceeded") from exc
        except httpx.TransportError as exc:
            raise TransportFailure(
                "HTTP transport failed or deadline exceeded"
            ) from exc

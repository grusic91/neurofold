"""Prove accidental network use fails while in-process ASGI remains usable."""

import asyncio
import socket
import urllib.request

import pytest
from pytest_socket import SocketBlockedError


@pytest.mark.parametrize("family", [socket.AF_INET, socket.AF_INET6])
@pytest.mark.parametrize("kind", [socket.SOCK_STREAM, socket.SOCK_DGRAM])
def test_internet_sockets_are_disabled(family: int, kind: int) -> None:
    with (
        pytest.warns(UserWarning, match="socket.socket"),
        pytest.raises(SocketBlockedError),
    ):
        socket.socket(family, kind)


def test_dns_is_disabled() -> None:
    with pytest.raises(RuntimeError, match="DNS is disabled"):
        socket.getaddrinfo("example.invalid", 443)
    with pytest.raises(RuntimeError, match="DNS is disabled"):
        socket.gethostbyname("example.invalid")
    with pytest.raises(RuntimeError, match="DNS is disabled"):
        socket.gethostbyname_ex("example.invalid")
    with pytest.raises(RuntimeError, match="DNS is disabled"):
        socket.gethostbyaddr("192.0.2.1")


def test_http_cannot_escape_guard() -> None:
    # Disable environment proxies; use a numeric loopback address to avoid DNS.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with pytest.raises((SocketBlockedError, RuntimeError)):
        opener.open("http://127.0.0.1:9/", timeout=0.1)


def test_async_connections_are_disabled() -> None:
    async def connect() -> None:
        with (
            pytest.warns(UserWarning, match="socket.socket"),
            pytest.raises(SocketBlockedError),
        ):
            await asyncio.open_connection("127.0.0.1", 9)

    asyncio.run(connect())

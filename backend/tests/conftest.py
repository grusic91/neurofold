"""Ordinary tests are offline, including DNS lookups before socket creation."""

import socket
from typing import NoReturn

import pytest


def deny_dns(*args: object, **kwargs: object) -> NoReturn:
    raise RuntimeError("DNS is disabled in offline tests; inject a fake transport.")


@pytest.fixture(autouse=True)
def offline_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    # pytest-socket blocks INET sockets; resolvers can otherwise use native DNS.
    for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
        monkeypatch.setattr(socket, name, deny_dns)

"""Local-server entry points: accept HTTP, deny outbound connections and DNS."""

import socket
from typing import NoReturn

from offline_app import services

from neurofold.api.main import create_app


def deny(*args: object, **kwargs: object) -> NoReturn:
    raise RuntimeError("Outbound network is disabled in the synthetic API server")


# Listening/accepted TCP sockets are necessary for real local HTTP acceptance.
# Provider clients must not connect anywhere, including numeric-IP destinations.
for method in ("connect", "connect_ex", "sendto"):
    setattr(socket.socket, method, deny)
for resolver in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
    setattr(socket, resolver, deny)

app = create_app(service_factory=services)
compressed_app = create_app(service_factory=lambda: services(compressed=True))

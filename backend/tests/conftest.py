"""Shared fixtures.

Every test in this suite relies on this: no test may open a network
connection. Tests run in CI and in cloud sessions, where external data
sources are not reachable (docs/adr/0002-testaufteilung.md). A test that
tries anyway must fail loudly instead of hanging until a timeout.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator

import pytest

_ALLOWED_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", ""})


class NetworkAccessError(RuntimeError):
    """Raised when a test tries to reach the network."""


def _host_of(address: object) -> str:
    if isinstance(address, tuple) and address:
        return str(address[0])
    return str(address)


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fail any attempt to open a non-local socket or resolve a hostname."""
    real_connect = socket.socket.connect

    def guarded_connect(self: socket.socket, address: object) -> None:
        host = _host_of(address)
        if host not in _ALLOWED_HOSTS:
            raise NetworkAccessError(f"network access to {host!r} is not allowed in tests")
        real_connect(self, address)

    def guarded_getaddrinfo(host: object, *args: object, **kwargs: object) -> None:
        raise NetworkAccessError(f"DNS lookup for {host!r} is not allowed in tests")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    yield

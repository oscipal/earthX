"""Shared fixtures.

Every test in this suite relies on this: no test may open a network
connection. Tests run in CI and in cloud sessions, where external data
sources are not reachable (docs/adr/0002-testaufteilung.md). A test that
tries anyway must fail loudly instead of hanging until a timeout.
"""

from __future__ import annotations

import logging
import socket
from collections.abc import Iterator

import pytest

from earthx.logging import JsonFormatter

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


class _JsonLineCapture(logging.Handler):
    """Formats each record immediately, the way the real `StreamHandler` from
    `earthx.logging.configure_logging` does — unlike `caplog`, which stores the raw
    `LogRecord` and only formats it when a test inspects it later. `RequestIdMiddleware`
    unbinds the request ID right after it logs (M3-16), so a record formatted late would
    read `get_request_id()` back as `None` instead of the value that was actually bound
    while the request was being handled.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(JsonFormatter())
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


@pytest.fixture
def access_log_lines() -> Iterator[list[str]]:
    """Every line `earthx.request` (`RequestIdMiddleware`'s access log) writes during
    the test, rendered through the real `JsonFormatter` at emit time."""
    handler = _JsonLineCapture()
    logger = logging.getLogger("earthx.request")
    logger.addHandler(handler)
    previous_level = logger.level
    logger.setLevel(logging.INFO)
    try:
        yield handler.lines
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)

"""The network guard from conftest.py works — otherwise every other test lies."""

from __future__ import annotations

import socket

import httpx
import pytest

from tests.conftest import NetworkAccessError


def test_dns_lookup_is_blocked() -> None:
    with pytest.raises(NetworkAccessError):
        socket.getaddrinfo("example.org", 443)


def test_socket_connect_to_a_foreign_host_is_blocked() -> None:
    with pytest.raises(NetworkAccessError):
        socket.socket().connect(("93.184.216.34", 80))


def test_an_outgoing_http_request_fails_instead_of_hanging() -> None:
    with pytest.raises((NetworkAccessError, httpx.HTTPError)):
        httpx.get("https://example.org", timeout=1.0)

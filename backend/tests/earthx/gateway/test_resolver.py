"""What DNS answers, and which of those answers we may connect to."""

from __future__ import annotations

import socket

import pytest

from earthx.gateway.errors import AddressRejected
from earthx.gateway.resolver import check_addresses, is_public, resolve_host

HOST = "earth-search.aws.element84.com"


@pytest.mark.parametrize("address", ["8.8.8.8", "93.184.216.34", "2001:4860:4860::8888", "::ffff:8.8.8.8"])
def test_a_globally_routable_address_is_public(address: str) -> None:
    assert is_public(address) is True


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",  # loopback
        "10.0.0.1",  # private
        "192.168.1.1",  # private
        "172.16.0.1",  # private
        "169.254.169.254",  # link-local, the cloud metadata service
        "100.64.0.1",  # shared address space, RFC 6598
        "0.0.0.0",
        "224.0.0.1",  # multicast
        "::1",
        "fe80::1",
        "fe80::1%eth0",
        "fc00::1",
        "::ffff:127.0.0.1",  # a loopback address wrapped as IPv6
        "2002:7f00:1::",  # a loopback address wrapped as 6to4
        "not-an-address",
    ],
)
def test_an_address_we_must_not_reach_is_not_public(address: str) -> None:
    assert is_public(address) is False


def test_addresses_pass_through_when_every_one_of_them_is_public() -> None:
    assert check_addresses(HOST, ("8.8.8.8", "2001:4860:4860::8888")) == ("8.8.8.8", "2001:4860:4860::8888")


def test_one_bad_address_refuses_the_whole_host() -> None:
    with pytest.raises(AddressRejected) as raised:
        check_addresses(HOST, ("93.184.216.34", "127.0.0.1"))
    assert raised.value.address == "127.0.0.1"


def _getaddrinfo(*addresses: str):
    def fake(host: str, port: int, *args: object, **kwargs: object) -> list[tuple]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port)) for address in addresses]

    return fake


def test_every_address_of_a_name_is_returned_once_and_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _getaddrinfo("93.184.216.34", "8.8.8.8", "93.184.216.34"))
    assert resolve_host(HOST) == ("93.184.216.34", "8.8.8.8")


def test_a_name_that_does_not_resolve_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise socket.gaierror("Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", fail)
    with pytest.raises(AddressRejected):
        resolve_host(HOST)


def test_a_name_that_resolves_to_nothing_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _getaddrinfo())
    with pytest.raises(AddressRejected):
        resolve_host(HOST)

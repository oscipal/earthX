"""DNS resolution, and the judgement on what comes back.

One name can carry several addresses. A single address we must not reach
refuses the whole host: a name that answers with a public address next to
``127.0.0.1`` is exactly the trick this is here to stop.
"""

from __future__ import annotations

import ipaddress
import socket

from earthx.gateway.errors import AddressRejected

IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


def resolve_host(host: str, port: int = 443) -> tuple[str, ...]:
    """Return every address the resolver knows for the host, in its order."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise AddressRejected("host does not resolve", host=host) from exc
    addresses = tuple(dict.fromkeys(str(info[4][0]) for info in infos))
    if not addresses:
        raise AddressRejected("host resolves to nothing", host=host)
    return addresses


def _unwrap(address: IpAddress) -> IpAddress:
    """Return the IPv4 address an IPv6 address carries inside it, if any."""
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped:
            return address.ipv4_mapped
        if address.sixtofour:
            return address.sixtofour
        if address.teredo:
            return address.teredo[1]
    return address


def is_public(address: str) -> bool:
    """True only for an address that is globally routable.

    ``is_global`` already covers loopback, private, link-local and the shared
    address space of RFC 6598; multicast is named separately because it is
    global and still not a host we may talk to.
    """
    try:
        parsed = _unwrap(ipaddress.ip_address(address))
    except ValueError:
        return False
    return parsed.is_global and not parsed.is_multicast


def check_addresses(host: str, addresses: tuple[str, ...]) -> tuple[str, ...]:
    """Return the addresses unchanged, or refuse the host because of one of them."""
    for address in addresses:
        if not is_public(address):
            raise AddressRejected("address is not globally routable", host=host, address=address)
    return addresses

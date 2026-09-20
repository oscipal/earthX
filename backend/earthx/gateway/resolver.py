"""DNS resolution, and the judgement on what comes back.

One name can carry several addresses. A single address we must not reach
refuses the whole host: a name that answers with a public address next to
``127.0.0.1`` is exactly the trick this is here to stop.

:class:`CachingResolver` is the resolution with a short memory, for the callers
that ask for the same name again and again. It caches only what the system
resolver answered — never the judgement on it, which :func:`check_addresses`
passes afresh on every hit.
"""

from __future__ import annotations

import ipaddress
import socket
import threading
import time
from collections import OrderedDict
from collections.abc import Callable

from earthx.gateway.errors import AddressRejected

IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

Resolver = Callable[[str, int], tuple[str, ...]]

# Short on purpose. The Sentinel-2 asset host answers with a record TTL of 5 s
# (measured 2026-09-20), so this holds an address no longer than the source says
# it holds, while still covering a whole batch of tiles with one resolution.
CACHE_TTL_S = 5.0

# The allowlist is short and a process sees a handful of hosts; the cap is here so
# the cache cannot grow with the names it is asked about, not because it is tight.
CACHE_MAX_ENTRIES = 256


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


class CachingResolver:
    """:func:`resolve_host` with a short memory. A value, held by the process.

    Handed to :func:`earthx.gateway.check_url` and to
    :class:`~earthx.gateway.client.Gateway` through their ``resolve`` argument, the
    seam that was put there for exactly this. Without it the tiler resolves the
    asset host once per tile and once per statistics request — measured at 17-40 ms
    each, synchronously on the event loop — although the host never changes between
    the tiles of one item (M2-14, from the "Ladeverhalten" section of #47).

    **What is cached is the answer, not the verdict.** ``check_url`` runs
    :func:`check_addresses` over the tuple it gets back every time, cache hit or
    not, so a name that starts answering with ``127.0.0.1`` is refused just the
    same. What a hit skips is the call to the system resolver, nothing else.

    **The addresses are kept whole and replaced whole.** A host that answers
    round-robin hands out a different set on every call; within one entry's life the
    variation is deliberately lost — the client connects to ``addresses[0]`` and GDAL
    never sees an address at all — and on expiry the fresh answer replaces the old
    one entirely. Old and new are never merged: that would keep an address alive
    that the name no longer names.

    **Only a success is remembered**, so a resolver that failed once is asked again
    rather than refusing the host for the rest of the entry's life.
    """

    def __init__(
        self,
        *,
        ttl_s: float = CACHE_TTL_S,
        max_entries: int = CACHE_MAX_ENTRIES,
        resolve: Resolver = resolve_host,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_s <= 0:
            raise ValueError("ttl_s must be positive; a cache that holds nothing is no cache")
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self._ttl_s = ttl_s
        self._max_entries = max_entries
        self._resolve = resolve
        self._now = now
        # Ordered so the oldest entry is the one that goes when the cap is reached.
        self._entries: OrderedDict[tuple[str, int], tuple[float, tuple[str, ...]]] = OrderedDict()
        # `check_url` is called from the event loop and from the thread pool that
        # renders; the lock costs nothing and keeps the dict from being read mid-write.
        self._lock = threading.Lock()

    def __call__(self, host: str, port: int = 443) -> tuple[str, ...]:
        """The addresses for the host, from the memory or from the system resolver."""
        key = (host, port)
        now = self._now()
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and entry[0] > now:
                self._entries.move_to_end(key)
                return entry[1]
            # Dropped before the resolution rather than after it: if the resolver
            # raises, no expired answer is left behind to be handed out later.
            self._entries.pop(key, None)
        addresses = self._resolve(host, port)
        with self._lock:
            self._entries[key] = (now + self._ttl_s, addresses)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)
        return addresses

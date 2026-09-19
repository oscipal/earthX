"""The allowlist, the limits, and every check that needs no network.

The host rules here answer the weakness the prototype still carries as an
``xfail`` (``backend/tests/test_config.py``): a plain ``endswith`` lets
``evilmaap.eo.esa.int`` through. A match is exact or ends at a dot, and the
host is normalized before it is compared at all.
"""

from __future__ import annotations

import ipaddress
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import urlsplit

from earthx.gateway.errors import UrlRejected, UrlTooLong

ALLOWED_HOSTS_ENV = "EARTHX_ALLOWED_HOSTS"

_LABEL = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
_DIGITS = re.compile(r"^[0-9]+$")


def normalize_host(host: str) -> str:
    """Return the host in the one spelling everything else compares against.

    Lower case, IDNA-encoded, without a trailing root dot — and never an IP
    address: the allowlist holds names, so an IP literal has no entry it could
    ever match. That closes the decimal and hexadecimal spellings of
    ``127.0.0.1`` and the cloud metadata address along with it.
    """
    host = host.strip().lower()
    if not host:
        raise UrlRejected("empty host")
    if host.startswith("[") or ":" in host:
        raise UrlRejected("IPv6 literal, the allowlist holds names", host=host)
    if host.endswith("."):
        host = host[:-1]
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise UrlRejected("IP literal, the allowlist holds names", host=host)
    if any(ord(char) > 127 for char in host):
        try:
            host = host.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise UrlRejected("host is not encodable as IDNA", host=host) from exc
    labels = host.split(".")
    if len(labels) < 2 or not all(_LABEL.match(label) for label in labels):
        raise UrlRejected("host is not a valid domain name", host=host)
    if _DIGITS.match(labels[-1]):
        raise UrlRejected("last label is all digits, so this is an address, not a name", host=host)
    return host


@dataclass(frozen=True)
class Policy:
    """Allowlist and limits. A value, handed in by the caller.

    Until M1-04 the caller is :func:`policy_from_env`; from M1-04 on it is the
    dataset registry. The gateway never looks the allowlist up itself — it runs
    in the local runner too, where there is no platform service (KLAERUNGEN B9).
    """

    allowed_hosts: frozenset[str]
    max_url_bytes: int = 8192  # adr/0004 §3.4: upstream answers 414 somewhere above 5.4 kB
    max_response_bytes: int = 8 * 1024 * 1024  # adr/0005 §6
    max_connections_per_host: int = 6  # adr/0005 §6
    max_redirects: int = 3
    connect_timeout_s: float = 5.0
    read_timeout_s: float = 15.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed_hosts", frozenset(normalize_host(h) for h in self.allowed_hosts))

    def allows_host(self, host: str) -> bool:
        """True for the host itself and for its real subdomains, nothing else."""
        return any(host == allowed or host.endswith("." + allowed) for allowed in self.allowed_hosts)


def policy_from_env(environ: dict[str, str] | None = None, **limits: object) -> Policy:
    """Build a policy from ``EARTHX_ALLOWED_HOSTS`` (comma separated).

    An unset or empty variable allows nothing, which is the safe end of the
    range: the gateway then refuses every request instead of every host.
    """
    raw = (environ if environ is not None else os.environ).get(ALLOWED_HOSTS_ENV, "")
    hosts: Iterable[str] = (part.strip() for part in raw.split(",") if part.strip())
    return Policy(allowed_hosts=frozenset(hosts), **limits)  # type: ignore[arg-type]


@dataclass(frozen=True)
class UrlParts:
    """A URL that passed every check that works without a network."""

    url: str
    host: str
    port: int


def inspect_url(url: str, policy: Policy) -> UrlParts:
    """Check scheme, credentials, port, host and length; resolve nothing.

    The order is deliberate: a URL we would never call is refused whatever its
    length, and the length limit only means something for a host that would
    otherwise be called.
    """
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise UrlRejected(f"scheme {parts.scheme or '(none)'!r} is not https")
    if parts.username or parts.password:
        raise UrlRejected("credentials in the URL")
    host = normalize_host(parts.hostname or "")
    try:
        port = parts.port or 443
    except ValueError as exc:
        raise UrlRejected("port is not a number", host=host) from exc
    if port != 443:
        raise UrlRejected(f"port {port} is not 443", host=host)
    if not policy.allows_host(host):
        raise UrlRejected("host is not on the allowlist", host=host)
    length = len(url.encode("utf-8"))
    if length > policy.max_url_bytes:
        raise UrlTooLong(length, policy.max_url_bytes)
    return UrlParts(url=url, host=host, port=port)

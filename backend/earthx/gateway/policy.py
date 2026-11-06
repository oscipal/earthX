"""The allowlist, the limits, and every check that needs no network.

The host rules here answer a weakness the BIOMASS prototype's allowlist once
carried as an ``xfail``, removed with the prototype (adr/0008): a plain
``endswith`` let ``evilmaap.eo.esa.int`` through. A match is exact or ends at
a dot, and the host is normalized before it is compared at all.
"""

from __future__ import annotations

import ipaddress
import math
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from urllib.parse import urlsplit

from earthx.gateway.errors import UrlRejected, UrlTooLong

ALLOWED_HOSTS_ENV = "EARTHX_ALLOWED_HOSTS"
USER_AGENT_ENV = "EARTHX_USER_AGENT"
# Project name and repository, no person's mail address (adr/0025 F9).
DEFAULT_USER_AGENT = "EarthX/0.1 (+https://github.com/oscipal/earthX)"
MAX_USER_AGENT_CHARS = 256
# A spacing above this is a typo, not courtesy: one request every five minutes stalls a run.
MAX_INTERVAL_S = 300.0

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


def check_user_agent(value: str) -> str:
    """Return ``value`` if it may go out as the ``User-Agent``, else raise ``ValueError``.

    Printable ASCII only, so no line break can smuggle a header in; no ``@``, so no
    mail address of a person goes to every source (adr/0025 F9). The message never
    repeats the value: it may come from the environment.
    """
    if not value or value != value.strip():
        raise ValueError("the User-Agent is empty or has leading or trailing spaces")
    if len(value) > MAX_USER_AGENT_CHARS:
        raise ValueError(f"the User-Agent is longer than {MAX_USER_AGENT_CHARS} characters")
    if any(not (32 <= ord(char) < 127) for char in value):
        raise ValueError("the User-Agent holds a character that is not printable ASCII")
    if "@" in value:
        raise ValueError("the User-Agent holds an '@'; a mail address does not belong in it")
    return value


def user_agent_from_env(environ: Mapping[str, str] | None = None) -> str:
    """The instance's one ``User-Agent``: ``EARTHX_USER_AGENT``, or the default if unset or empty.

    Every process calls this at start, so a bad value stops it there (M5-18 §3.1); the
    error names the variable, never the value.
    """
    raw = (environ if environ is not None else os.environ).get(USER_AGENT_ENV, "")
    if not raw.strip():
        return DEFAULT_USER_AGENT
    try:
        return check_user_agent(raw)
    except ValueError as error:
        raise ValueError(f"{USER_AGENT_ENV}: {error}") from None


def product_token(user_agent: str) -> str:
    """The name ``robots.txt`` groups are matched against: the text before the first ``/`` or space."""
    return re.split(r"[/ ]", user_agent, maxsplit=1)[0]


def _check_interval(seconds: float) -> float:
    if not isinstance(seconds, (int, float)) or math.isnan(seconds) or not 0 <= seconds <= MAX_INTERVAL_S:
        raise ValueError(f"an interval per host lies between 0 and {MAX_INTERVAL_S:g} seconds")
    return float(seconds)


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
    # On every request, never set by a caller (adr/0025 F9). The instance's value unless a test names one.
    user_agent: str = field(default_factory=user_agent_from_env)
    # The least time between the starts of two requests to one host (adr/0025 §6.2). 0 waits never.
    min_interval_s: float = 0.0
    # Per host, overriding ``min_interval_s``; a subdomain takes its parent's value, as in the allowlist.
    host_intervals: Mapping[str, float] = field(default_factory=dict, hash=False)
    # Ask robots.txt before a host is fetched (RFC 9309). Only the harvester's catalogue fetch sets it.
    obey_robots: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed_hosts", frozenset(normalize_host(h) for h in self.allowed_hosts))
        check_user_agent(self.user_agent)
        object.__setattr__(self, "min_interval_s", _check_interval(self.min_interval_s))
        intervals = {normalize_host(host): _check_interval(value) for host, value in self.host_intervals.items()}
        object.__setattr__(self, "host_intervals", MappingProxyType(intervals))

    def interval_for(self, host: str) -> float:
        """The spacing for ``host``: its own entry, the nearest parent's, else ``min_interval_s``."""
        labels = host.split(".")
        for start in range(len(labels) - 1):
            value = self.host_intervals.get(".".join(labels[start:]))
            if value is not None:
                return value
        return self.min_interval_s

    def allows_host(self, host: str) -> bool:
        """True for the host itself and for its real subdomains, nothing else."""
        return any(host == allowed or host.endswith("." + allowed) for allowed in self.allowed_hosts)


def host_of(url: str) -> str:
    """The normalized host of a URL that is already trusted (M1-07).

    Not one of the request-time checks: those trust nothing until ``inspect_url``
    has looked at it. This is how ``api`` turns the registry's own, already-known
    source endpoints into the gateway's allowlist without importing ``urllib``
    itself (KLAERUNGEN B8) — the parsing stays in the one module allowed to do it.
    """
    return normalize_host(urlsplit(url).hostname or "")


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

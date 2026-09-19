"""What the gateway refuses, and why.

Every error names the reason without repeating the URL: the query string of an
outgoing request carries the AOI, and that must not end up in a log or a
traceback (projektplan.md 7, point 6).
"""

from __future__ import annotations


class GatewayError(RuntimeError):
    """Base class for everything the gateway refuses or cannot deliver."""


class UrlRejected(GatewayError):
    """The URL is not allowed: scheme, credentials, port, host or allowlist."""

    def __init__(self, reason: str, *, host: str | None = None) -> None:
        super().__init__(f"{reason} (host {host!r})" if host else reason)
        self.reason = reason
        self.host = host


class AddressRejected(GatewayError):
    """The host does not resolve, or resolves to an address we must not connect to."""

    def __init__(self, reason: str, *, host: str, address: str | None = None) -> None:
        super().__init__(f"{reason}: host {host!r}" + (f", address {address!r}" if address else ""))
        self.reason = reason
        self.host = host
        self.address = address


class UrlTooLong(GatewayError):
    """The assembled URL exceeds the limit that upstream answers with 414.

    Carries both numbers so the caller can simplify its AOI and say so in its
    own answer instead of failing (adr/0004 §3.4).
    """

    def __init__(self, length: int, limit: int) -> None:
        super().__init__(f"URL is {length} bytes, the limit is {limit}")
        self.length = length
        self.limit = limit


class ResponseTooLarge(GatewayError):
    """The body exceeds the limit, either as announced or as counted while reading."""

    def __init__(self, size: int, limit: int) -> None:
        super().__init__(f"response body is at least {size} bytes, the limit is {limit}")
        self.size = size
        self.limit = limit


class TooManyRedirects(GatewayError):
    """The source kept redirecting past the limit."""

    def __init__(self, limit: int) -> None:
        super().__init__(f"more than {limit} redirects")
        self.limit = limit


class UpstreamError(GatewayError):
    """The source answered, and the answer is not one we pass on.

    The status code survives unchanged: an adapter has to tell ``400``, ``404``
    and ``429`` apart (adr/0005 §3.5, §3.8).
    """

    def __init__(self, status_code: int, excerpt: str = "") -> None:
        super().__init__(f"upstream answered {status_code}" + (f": {excerpt}" if excerpt else ""))
        self.status_code = status_code
        self.excerpt = excerpt


class UpstreamUnreachable(GatewayError):
    """The source did not answer at all."""


class UpstreamTimeout(UpstreamUnreachable):
    """The source did not answer in time."""

"""The one function that clears a URL for use.

Everything that goes out — the gateway's own client, and every URL handed to
GDAL or rasterio — passes through here first (KLAERUNGEN B8).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from earthx.gateway.policy import Policy, inspect_url
from earthx.gateway.resolver import check_addresses, resolve_host


@dataclass(frozen=True)
class CheckedUrl:
    """A URL that passed every check, with the addresses it is allowed to reach."""

    url: str
    host: str
    port: int
    addresses: tuple[str, ...]

    @property
    def address(self) -> str:
        """The address to connect to, so the name is not resolved a second time."""
        return self.addresses[0]


def check_url(
    url: str,
    policy: Policy,
    *,
    resolve: Callable[[str, int], tuple[str, ...]] = resolve_host,
) -> CheckedUrl:
    """Clear a URL, or raise the reason why not.

    ``resolve`` is handed in so tests, and later a caching resolver, can take
    the place of the system resolver.
    """
    parts = inspect_url(url, policy)
    addresses = check_addresses(parts.host, resolve(parts.host, parts.port))
    return CheckedUrl(url=parts.url, host=parts.host, port=parts.port, addresses=addresses)

"""What a worker needs before it reads anything: policy, GDAL options, resolver (adr/0014 §8).

`processing` reads the sources a recipe names, but may not import `gateway`, not
even as a type (architekturplan.md 3.1, KLAERUNGEN B9). This module may, so it is
the one factory that turns the addresses of a recipe into what the readers need:

* :func:`process_gdal_options` — the GDAL settings from `gateway` plus
  ``GDAL_CACHEMAX``. They depend only on the policy's time limits, never on its
  allowlist (``gateway.gdal.gdal_options``), so a process can enter them once at
  start, in its main thread, before it knows which job it runs (§7.3 point 2).
* :func:`read_access_for` — one job's :class:`ReadAccess`: an allowlist of exactly
  the hosts its addresses name (KLAERUNGEN B9, word for word), the same GDAL
  options, and one :class:`~earthx.gateway.CachingResolver` for the whole run.

Whether those hosts belong to the dataset at all is checked when `api` accepts the
recipe (adr/0014 §8); here an address only has to name a host.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from earthx.gateway import CachingResolver, Policy, Resolver, UrlRejected, host_of, resolve_host
from earthx.gateway.gdal import gdal_options
from earthx.readers.errors import AssetRejected

__all__ = ["GDAL_CACHEMAX_BYTES", "ReadAccess", "process_gdal_options", "read_access_for"]

#: GDAL's block cache for one worker process. Set rather than left at its default
#: of 5 % of RAM, which cost a worker several hundred MB in the measurement; 64 MB
#: is the measured value (148 MB peak for 1024 px blocks over an 8192² scene,
#: adr/0014 §3.5 and the addendum to §7.2). In bytes and as an integer, because
#: that is what ``rasterio.Env`` takes for this one option (it calls
#: ``GDALSetCacheMax64``); GDAL itself would read a small number as MB.
GDAL_CACHEMAX_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ReadAccess:
    """Everything one run needs to open its inputs: whom to ask, how, and through what."""

    policy: Policy
    gdal_options: Mapping[str, str | int]
    resolve: Resolver


def process_gdal_options() -> Mapping[str, str | int]:
    """The GDAL settings every read of a worker runs under, independent of the job."""
    options: dict[str, str | int] = dict(gdal_options(Policy(allowed_hosts=frozenset())))
    options["GDAL_CACHEMAX"] = GDAL_CACHEMAX_BYTES
    return MappingProxyType(options)


def read_access_for(hrefs: Iterable[str]) -> ReadAccess:
    """A :class:`ReadAccess` whose allowlist holds exactly the hosts of ``hrefs``.

    Raises :class:`~earthx.readers.errors.AssetRejected` for an address without a
    valid host; the text names the reason, never the address.
    """
    hosts: set[str] = set()
    for href in hrefs:
        try:
            hosts.add(host_of(href))
        except UrlRejected as error:
            raise AssetRejected(f"an input address names no valid host ({error.reason})") from None
    if not hosts:
        raise AssetRejected("a run needs at least one input address")
    return ReadAccess(
        policy=Policy(allowed_hosts=frozenset(hosts)),
        gdal_options=process_gdal_options(),
        resolve=CachingResolver(resolve=resolve_host),
    )

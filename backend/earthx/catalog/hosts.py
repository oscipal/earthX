"""The limits per host, for all instances of the platform together (M5-36 §3.1, G1, G2).

One file, ``backend/catalog/hosts.yaml``, one entry per host: a limit is a rule of the source, and a host serves
several datasets. Read as strictly as the entries; whether every host of the registry has an entry, and every entry a
host, is checked where both meet (:class:`~earthx.catalog.registry.DatasetRegistry`). `gateway` never reads the file;
the shells turn it into a :class:`~earthx.gateway.Policy`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from earthx.catalog.entry_files import EntryFileError, read_yaml
from earthx.gateway import UrlRejected, normalize_host
from earthx.gateway.policy import MAX_CONNECTIONS_PER_HOST, MAX_INTERVAL_S

__all__ = ["HOSTS_FILE", "HostLimit", "load_host_limits"]

HOSTS_FILE = "hosts.yaml"
_FIELDS = {"connections", "interval_s", "reason"}


@dataclass(frozen=True, slots=True)
class HostLimit:
    """What one host bears from the whole platform at once.

    ``connections``: requests or GDAL readers at the same time. ``interval_s``: the least time between the starts of
    two requests, ``None`` where the source sets no rule (the caller's own default then holds). ``reason``: why.
    """

    connections: int
    interval_s: float | None
    reason: str


def load_host_limits(path: Path) -> Mapping[str, HostLimit]:
    """The limits of ``path`` by host, or :class:`EntryFileError` naming the file, the host and the field."""
    data = read_yaml(path)
    if not isinstance(data, dict) or set(data) != {"hosts"} or not isinstance(data["hosts"], dict) or not data["hosts"]:
        raise EntryFileError(f"{path.name}: one key 'hosts', a mapping of host names to their limits")
    return MappingProxyType({host: _limit(path.name, host, value) for host, value in data["hosts"].items()})


def _limit(name: str, host: str, value: object) -> HostLimit:
    where = f"{name}: {host}"
    try:
        spelled = normalize_host(host)
    except UrlRejected as error:
        raise EntryFileError(f"{where}: not a host name ({error.reason})") from None
    if spelled != host:
        raise EntryFileError(f"{where}: write the host as {spelled}")
    if not isinstance(value, dict) or not {"connections", "reason"} <= set(value) <= _FIELDS:
        raise EntryFileError(f"{where}: needs connections and reason, may have interval_s, nothing else")
    connections, interval, reason = value["connections"], value.get("interval_s"), value["reason"]
    if (
        isinstance(connections, bool)
        or not isinstance(connections, int)
        or not 1 <= connections <= MAX_CONNECTIONS_PER_HOST
    ):
        raise EntryFileError(f"{where}: connections is a whole number from 1 to {MAX_CONNECTIONS_PER_HOST}")
    if interval is not None and (
        isinstance(interval, bool)
        or not isinstance(interval, (int, float))
        or math.isnan(interval)
        or not 0 <= interval <= MAX_INTERVAL_S
    ):
        raise EntryFileError(f"{where}: interval_s is a number of seconds from 0 to {MAX_INTERVAL_S:g}")
    if not isinstance(reason, str) or not reason.strip():
        raise EntryFileError(f"{where}: reason is text")
    return HostLimit(connections, None if interval is None else float(interval), reason)

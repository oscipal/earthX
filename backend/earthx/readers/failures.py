"""How a failed read of a source is named (adr/0013 §5.6, plan M4-08a F1).

`processing` and `jobs` may not import `gateway` or look at what rasterio raises
(architekturplan.md 3.1), yet `jobs` must decide from the failure alone whether a
second attempt can help. So this module, which may, turns a failure into one short
name and nothing else; no message, no address, no status line leaves it.

Two families reach it. A read through ``Gateway`` (Zarr, the ``HEAD`` of the
acceptance) raises the classes of ``gateway/errors.py`` with the status attached.
A read through GDAL raises ``RasterioIOError`` for every cause alike and puts the
status only in the text (adr/0013 M10, GDAL 3.12.2); two patterns of that text are
matched, any other text names nothing. ``test_failures.py`` holds both against a
local server, so a GDAL release that words them differently breaks a test rather
than the retry rule.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from rasterio.errors import RasterioIOError

from earthx.gateway import GatewayError, UpstreamError, UpstreamTimeout, UpstreamUnreachable

__all__ = ["SOURCE_KINDS", "source_failure_kind"]

#: Everything :func:`source_failure_kind` can return.
SOURCE_KINDS = frozenset({"source_timeout", "source_5xx", "source_429", "source_4xx", "source_unreachable", "rejected"})

_GDAL_STATUS = re.compile(r"HTTP response code: (\d{3})\b")
_GDAL_TIMEOUT = "CURL error: Operation timed out"
_MAX_DEPTH = 8


def _chain(error: BaseException) -> Iterator[BaseException]:
    """``error`` and what it was raised from or while handling, nearest first, each once."""
    seen: set[int] = set()
    pending: list[BaseException | None] = [error]
    while pending and len(seen) < _MAX_DEPTH:
        current = pending.pop(0)
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        yield current
        pending.extend((current.__cause__, current.__context__))


def _by_status(status: int) -> str | None:
    if status >= 500:
        return "source_5xx"
    if status == 429:
        return "source_429"
    if 400 <= status < 500:
        return "source_4xx"
    return None


def source_failure_kind(error: BaseException) -> str | None:
    """The name of a failed read of a source, or ``None`` when this is not one."""
    for current in _chain(error):
        if isinstance(current, UpstreamTimeout):
            return "source_timeout"
        if isinstance(current, UpstreamUnreachable):
            return "source_unreachable"
        if isinstance(current, UpstreamError):
            return _by_status(current.status_code)
        if isinstance(current, GatewayError):
            return "rejected"
        if isinstance(current, RasterioIOError):
            text = str(current)
            if _GDAL_TIMEOUT in text:
                return "source_timeout"
            match = _GDAL_STATUS.search(text)
            if match is not None:
                return _by_status(int(match[1]))
    return None

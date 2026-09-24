"""Checks on what a caller hands a tool, before anything goes out.

The caller will one day be a language model, so every argument is untrusted: a
wrong type, a swapped interval or a path in a collection id must come back as a
reason the model can act on, never as a request.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone

MAX_QUERY_CHARS = 200
MAX_LIMIT = 50

# STAC ids in practice: letters, digits, dot, dash, underscore. Anything else — a
# slash above all — would change the path the id is placed into.
_COLLECTION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

_OPEN = ".."
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class InvalidArgument(ValueError):
    """An argument a tool refuses, with the reason in words a model can act on."""


def collection_id(value: object) -> str:
    if not isinstance(value, str) or not _COLLECTION_ID.match(value) or ".." in value:
        raise InvalidArgument("collection_id must be a STAC id: letters, digits, '.', '-' or '_'")
    return value


def query(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise InvalidArgument("query must be text")
    value = " ".join(value.split())
    if len(value) > MAX_QUERY_CHARS:
        raise InvalidArgument(f"query is longer than {MAX_QUERY_CHARS} characters")
    return value


def limit(value: object, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidArgument("limit must be a whole number")
    if not 1 <= value <= MAX_LIMIT:
        raise InvalidArgument(f"limit must be between 1 and {MAX_LIMIT}")
    return value


def bbox(value: object) -> tuple[float, float, float, float] | None:
    """A 2D box in WGS84 as ``[west, south, east, north]``.

    A box across the antimeridian (west > east) is refused rather than guessed at:
    STAC allows it, but a swapped pair is the far likelier mistake, and the model
    can split the box in two if it really meant it.
    """
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise InvalidArgument("bbox must be four numbers: [west, south, east, north]")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in value):
        raise InvalidArgument("bbox must be four finite numbers")
    west, south, east, north = (float(v) for v in value)
    if not (-180 <= west <= 180 and -180 <= east <= 180):
        raise InvalidArgument("bbox longitudes must lie within -180..180")
    if not (-90 <= south <= 90 and -90 <= north <= 90):
        raise InvalidArgument("bbox latitudes must lie within -90..90")
    if west > east:
        raise InvalidArgument("bbox west is greater than east; boxes across the antimeridian are not supported")
    if south > north:
        raise InvalidArgument("bbox south is greater than north")
    return west, south, east, north


def parse_instant(text: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise InvalidArgument(f"{text!r} is not an ISO 8601 date or date-time") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _stac_instant(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def interval(value: object) -> tuple[datetime | None, datetime | None] | None:
    """A STAC datetime: one instant, or ``start/end`` with ``..`` for an open end."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise InvalidArgument("datetime must be text such as '2024-06-01/2024-06-30'")
    parts = value.strip().split("/")
    if len(parts) == 1:
        instant = parse_instant(parts[0])
        return instant, instant
    if len(parts) != 2:
        raise InvalidArgument("datetime must be one instant or 'start/end'")
    start = None if parts[0] in ("", _OPEN) else parse_instant(parts[0])
    end = None if parts[1] in ("", _OPEN) else parse_instant(parts[1])
    if end is not None and _DATE_ONLY.match(parts[1]):
        # "2024-06-01/2024-06-30" means the whole of 30 June, not its first instant.
        end += timedelta(days=1, microseconds=-1)
    if start is None and end is None:
        raise InvalidArgument("datetime must bound at least one end")
    if start is not None and end is not None and start > end:
        raise InvalidArgument("datetime starts after it ends")
    return start, end


def stac_datetime(bounds: tuple[datetime | None, datetime | None]) -> str:
    """The interval in the spelling the STAC API reads."""
    start, end = bounds
    if start is not None and start == end:
        return _stac_instant(start)
    return f"{_OPEN if start is None else _stac_instant(start)}/{_OPEN if end is None else _stac_instant(end)}"

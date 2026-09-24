"""STAC answers cut down to what a tool hands back.

Only named fields are copied, each only if it has the expected type, and every
text is shortened; the few ``earthx:`` fields pass whole or not at all. What comes back is data for a model to read, so nothing here
may pass on a whole document or a field nobody chose — a description can carry
text written to look like an instruction (projektuebersicht.md, security section).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from earthx.chatbot.validation import InvalidArgument, parse_instant

SEARCH_DESCRIPTION_CHARS = 300
DETAIL_DESCRIPTION_CHARS = 2000
MAX_KEYWORDS = 20
MAX_PROVIDERS = 10

# The earthx: fields a user choosing a dataset needs. `earthx:source` stays out:
# it names upstream endpoints, which are no business of the answer (CLAUDE.md).
_EARTHX_FIELDS = ("earthx:data_class", "earthx:capabilities", "earthx:license_flags", "earthx:maturity")

# Our own API writes these fields small; another STAC API may put anything there.
# A field whose JSON is longer than this is dropped rather than cut, since a cut
# JSON value is no value at all.
MAX_EARTHX_FIELD_CHARS = 4000


def _text(value: object, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _texts(value: object, limit: int, count: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for text in (_text(v, limit) for v in value[:count]) if text]


def _bbox(collection: dict[str, Any]) -> list[float] | None:
    try:
        box = collection["extent"]["spatial"]["bbox"][0]
    except (KeyError, IndexError, TypeError):
        return None
    if isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box):
        return [float(v) for v in box]
    return None


def _interval(collection: dict[str, Any]) -> list[str | None] | None:
    try:
        pair = collection["extent"]["temporal"]["interval"][0]
    except (KeyError, IndexError, TypeError):
        return None
    if isinstance(pair, list) and len(pair) == 2 and all(v is None or isinstance(v, str) for v in pair):
        return list(pair)
    return None


def _providers(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    names = (_text(p.get("name"), 100) for p in value[:MAX_PROVIDERS] if isinstance(p, dict))
    return [name for name in names if name]


def collection_brief(collection: dict[str, Any]) -> dict[str, Any]:
    """One hit of ``search_collections``."""
    return {
        "id": collection.get("id"),
        "title": _text(collection.get("title"), 200),
        "description": _text(collection.get("description"), SEARCH_DESCRIPTION_CHARS),
        "license": _text(collection.get("license"), 100),
        "bbox": _bbox(collection),
        "interval": _interval(collection),
    }


def collection_detail(collection: dict[str, Any]) -> dict[str, Any]:
    """The answer of ``get_collection``."""
    detail = collection_brief(collection)
    detail["description"] = _text(collection.get("description"), DETAIL_DESCRIPTION_CHARS)
    detail["keywords"] = _texts(collection.get("keywords"), 60, MAX_KEYWORDS)
    detail["providers"] = _providers(collection.get("providers"))
    for field in _EARTHX_FIELDS:
        if field in collection and len(json.dumps(collection[field], default=str)) <= MAX_EARTHX_FIELD_CHARS:
            detail[field] = collection[field]
    return detail


def matches(
    collection: dict[str, Any],
    words: list[str],
    bbox: tuple[float, float, float, float] | None,
    bounds: tuple[datetime | None, datetime | None] | None,
) -> bool:
    """Every word somewhere in the text, and an extent that overlaps the filters.

    A collection that does not state an extent is kept: it cannot be ruled out,
    and the availability check answers the question properly.
    """
    haystack = " ".join(
        filter(
            None,
            [
                _text(collection.get("id"), 200),
                _text(collection.get("title"), 200),
                _text(collection.get("description"), 10_000),
                *_texts(collection.get("keywords"), 60, MAX_KEYWORDS),
                *_providers(collection.get("providers")),
            ],
        )
    ).lower()
    if not all(word in haystack for word in words):
        return False
    box = _bbox(collection)
    if bbox is not None and box is not None:
        west, south, east, north = bbox
        if box[0] > east or box[2] < west or box[1] > north or box[3] < south:
            return False
    pair = _interval(collection)
    if bounds is not None and pair is not None:
        start, end = bounds
        try:
            first = None if pair[0] is None else parse_instant(pair[0])
            last = None if pair[1] is None else parse_instant(pair[1])
        except InvalidArgument:
            return True
        if end is not None and first is not None and first > end:
            return False
        if start is not None and last is not None and last < start:
            return False
    return True


def _item_instant(item: object) -> str | None:
    if not isinstance(item, dict) or not isinstance(item.get("properties"), dict):
        return None
    properties = item["properties"]
    value = properties.get("datetime") or properties.get("start_datetime")
    return value if isinstance(value, str) else None


def availability(collection_id: str, page: dict[str, Any]) -> dict[str, Any]:
    """How many items a search found, and the dates the sample spans.

    ``numberMatched`` is optional in STAC and our own API leaves it out when the
    source gave no checked total (api/federating_client.py). Without it the count
    is a lower bound, and the answer says so instead of passing the page size off
    as the total.
    """
    features = page.get("features")
    features = features if isinstance(features, list) else []
    matched = page.get("numberMatched")
    exact = isinstance(matched, int) and not isinstance(matched, bool) and matched >= 0
    links = page.get("links")
    has_more = isinstance(links, list) and any(isinstance(link, dict) and link.get("rel") == "next" for link in links)
    instants = sorted(filter(None, (_item_instant(item) for item in features)))
    return {
        "collection_id": collection_id,
        "count": matched if exact else len(features),
        "count_is_exact": exact or not has_more,
        "sample_size": len(features),
        "earliest_in_sample": instants[0] if instants else None,
        "latest_in_sample": instants[-1] if instants else None,
    }

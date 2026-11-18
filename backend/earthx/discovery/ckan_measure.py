"""How large a page of a CKAN listing is, and how much ``fl`` would save (Otto, 18.11.2026; M5-19 plan §12.5).

    python -m earthx.discovery.harvest <ckan source> --measure

Two requests through the gateway, nothing written: the first page of the listing as the harvest asks it, and the same
page with ``fl`` naming only the Solr fields the extract reads (:data:`EXTRACT_FIELDS`). CKAN answers ``fl`` with the
flat fields of its search index instead of the package dict (``ckan/logic/action/get.py``, ``package_search``), so the
report also says which of these fields come back filled: whether an extractor on them could give the same intermediate
form. Sizes as the gateway hands them over (decoded) and as gzip would carry them; shares by field of the package and
of its resources. No address, no key and no value of a package is printed (plan A6).
"""

from __future__ import annotations

import gzip
import json
from collections import Counter
from collections.abc import Awaitable, Callable
from typing import Any

from earthx.catalog.sources import CkanFilter, SourceConfig
from earthx.discovery.extract import ShapeError
from earthx.gateway import GatewayResponse

__all__ = ["EXTRACT_FIELDS", "measure_page"]

ROWS = 100
#: The Solr fields that hold what the CKAN extract reads; ``extras_<key>`` comes back as ``<key>``.
EXTRACT_FIELDS = (
    "id",
    "name",
    "title",
    "notes",
    "url",
    "license_id",
    "organization",
    "groups",
    "tags",
    "res_url",
    "res_format",
    "res_name",
    "res_type",
    "extras_spatial",
    "extras_publisher_name",
    "extras_temporal_start",
    "extras_temporal_end",
    "extras_theme",
    "extras_access_rights",
)
_TOP = 12

Fetch = Callable[..., Awaitable[GatewayResponse]]


def _size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


def _results(response: GatewayResponse) -> list[Any]:
    if response.status_code != 200:
        raise ShapeError(f"the listing answered {response.status_code}")
    try:
        body = response.json()
    except (ValueError, RecursionError):
        raise ShapeError("the page is no JSON") from None
    result = body.get("result") if isinstance(body, dict) else None
    results = result.get("results") if isinstance(result, dict) else None
    if not isinstance(results, list):
        raise ShapeError("the page has no list of packages")
    return results


def _shares(counter: Counter[str], whole: int) -> list[str]:
    return [f"    {key:<28} {size / 1e3:9.1f} KB  {100 * size / max(whole, 1):5.1f} %" for key, size in counter.most_common(_TOP)]


def _filled(value: Any) -> bool:
    return value not in (None, "", [], {})


async def measure_page(fetch: Fetch, source: SourceConfig) -> str:
    """The report of one measurement of ``source``'s first page."""
    assert isinstance(source.filter, CkanFilter)
    url = f"{source.endpoint}/package_search"
    base: dict[str, str | int] = {"rows": ROWS, "start": 0, "sort": "id asc"}
    if source.filter.fq is not None:
        base["fq"] = f"({source.filter.fq})"
    full = await fetch(url, params=base)
    packages = [p for p in _results(full) if isinstance(p, dict)]
    narrow = await fetch(url, params={**base, "fl": ",".join(EXTRACT_FIELDS)})
    rows = [r for r in _results(narrow) if isinstance(r, dict)]

    by_field: Counter[str] = Counter()
    by_resource_field: Counter[str] = Counter()
    for package in packages:
        for key, value in package.items():
            by_field[str(key)] += _size(value)
        resources = package.get("resources")
        for resource in resources if isinstance(resources, list) else ():
            if isinstance(resource, dict):
                for key, value in resource.items():
                    by_resource_field[str(key)] += _size(value)
    filled = Counter(key for row in rows for key, value in row.items() if _filled(value))
    whole, small = len(full.content), len(narrow.content)
    lines = [
        f"{source.source_id}: Messung einer Seite mit {len(packages)} Paketen (nichts gespeichert)",
        f"  wie der Harvest fragt: {whole / 1e6:.2f} MB, gzip {len(gzip.compress(full.content)) / 1e6:.2f} MB"
        f" (die Quelle sendet {full.headers.get('content-encoding') or 'ohne Kompression'})",
        f"  mit fl ({len(EXTRACT_FIELDS)} Felder): {small / 1e6:.2f} MB, gzip"
        f" {len(gzip.compress(narrow.content)) / 1e6:.2f} MB, {100 * small / max(whole, 1):.0f} % der vollen Seite",
        "  größte Felder der Pakete:",
        *_shares(by_field, whole),
        "  größte Felder der Ressourcen (Anteil an der Seite):",
        *_shares(by_resource_field, whole),
        f"  mit fl gefüllt (von {len(rows)} Treffern):",
        *(f"    {field:<28} {filled.get(_returned_as(field), 0):5d}" for field in EXTRACT_FIELDS),
    ]
    return "\n".join(lines)


def _returned_as(field: str) -> str:
    """CKAN hands ``extras_<key>`` back as ``<key>`` (``ckan/lib/search/query.py``)."""
    return field.removeprefix("extras_")

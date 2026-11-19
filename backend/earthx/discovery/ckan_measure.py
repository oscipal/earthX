"""How large and how slow a page of a CKAN listing is, and how much ``fl`` would save (Otto, 18./19.11.2026; M5-19 plan
§12.5, §12.8).

    python -m earthx.discovery.harvest <ckan source> --measure

Six requests through the gateway, nothing written: the first page of the listing as the harvest asks it; the second
page twice by offset (``start``) and twice by key (``fq`` with the ids after the last one of the first page),
alternating, with the time of each, to see whether the keyset query itself is the slow one; and the first page with
``fl`` naming only the Solr fields the extract reads (:data:`EXTRACT_FIELDS`). CKAN answers ``fl`` with the flat fields
of its search index instead of the package dict (``ckan/logic/action/get.py``, ``package_search``), so the report also
says which of these fields come back filled. Times are the gateway's own, without the waits for spacing; sizes as the
gateway hands them over (decoded) and as gzip would carry them. No address, no key and no value of a package is
printed (plan A6).
"""

from __future__ import annotations

import gzip
import json
from collections import Counter
from collections.abc import Awaitable, Callable
from typing import Any

from earthx.catalog.sources import CkanFilter, SourceConfig
from earthx.discovery.ckan import package_key, search_params
from earthx.discovery.extract import ShapeError
from earthx.gateway import GatewayResponse

__all__ = ["EXTRACT_FIELDS", "measure_page"]

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
    """The report of one measurement of ``source``: its first page as the harvest asks it, the same second page twice
    by offset and twice by key, alternating (Otto, 19.11.2026: is the keyset query itself the slow one?), and the first
    page with ``fl``. Times are the gateway's own, without the waits for spacing and crawl delay."""
    assert isinstance(source.filter, CkanFilter)
    url = f"{source.endpoint}/package_search"
    first_params = search_params(source, None, None)
    rows = int(first_params["rows"])
    full = await fetch(url, params=first_params)
    packages = [p for p in _results(full) if isinstance(p, dict)]
    keys = [key for p in packages if (key := package_key(p)) is not None]
    offset_params = {**first_params, "start": rows}
    keyset_params = search_params(source, keys[-1], None) if keys else None
    timings: list[tuple[str, float, list[str | None]]] = []
    for _ in range(2):
        for label, params in (("Versatz", offset_params), ("Keyset", keyset_params)):
            if params is None:
                continue
            response = await fetch(url, params=params)
            ids = [package_key(p) for p in _results(response)]
            timings.append((label, response.elapsed_s, ids))
    narrow = await fetch(url, params={**first_params, "fl": ",".join(EXTRACT_FIELDS)})
    narrow_rows = [r for r in _results(narrow) if isinstance(r, dict)]

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
    filled = Counter(key for row in narrow_rows for key, value in row.items() if _filled(value))
    whole, small = len(full.content), len(narrow.content)
    pages_by = {label: [ids for name, _, ids in timings if name == label] for label in ("Versatz", "Keyset")}
    same = bool(timings) and all(ids == pages_by["Versatz"][0] for ids in pages_by["Versatz"] + pages_by["Keyset"])
    lines = [
        f"{source.source_id}: Messung, Seiten mit {rows} Paketen (nichts gespeichert)",
        f"  erste Seite wie der Harvest: {full.elapsed_s:.1f} s, {whole / 1e6:.2f} MB, gzip"
        f" {len(gzip.compress(full.content)) / 1e6:.2f} MB (die Quelle sendet"
        f" {full.headers.get('content-encoding') or 'ohne Kompression'})",
        f"  zweite Seite, abwechselnd per Versatz (start={rows}) und per Keyset (fq id nach dem letzten Schlüssel):",
        *(f"    {label:<8} {elapsed:6.1f} s" for label, elapsed, _ in timings),
        f"    dieselben Pakete: {'ja' if same else 'nein'}",
        f"  mit fl ({len(EXTRACT_FIELDS)} Felder): {narrow.elapsed_s:.1f} s, {small / 1e6:.2f} MB, gzip"
        f" {len(gzip.compress(narrow.content)) / 1e6:.2f} MB, {100 * small / max(whole, 1):.0f} % der vollen Seite",
        "  größte Felder der Pakete:",
        *_shares(by_field, whole),
        "  größte Felder der Ressourcen (Anteil an der Seite):",
        *_shares(by_resource_field, whole),
        f"  mit fl gefüllt (von {len(narrow_rows)} Treffern):",
        *(f"    {field:<28} {filled.get(_returned_as(field), 0):5d}" for field in EXTRACT_FIELDS),
    ]
    return "\n".join(lines)


def _returned_as(field: str) -> str:
    """CKAN hands ``extras_<key>`` back as ``<key>`` (``ckan/lib/search/query.py``)."""
    return field.removeprefix("extras_")

"""The measurement of one page of a CKAN listing with and without ``fl`` (Otto, 18.11.2026; plan §12.5)."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import pytest

from earthx.catalog.registry import Maturity
from earthx.catalog.sources import CkanFilter, SourceConfig, SourceProtocol
from earthx.discovery.ckan_measure import EXTRACT_FIELDS, measure_page
from earthx.discovery.extract import ShapeError
from earthx.discovery.harvest import main
from earthx.gateway import GatewayResponse

pytestmark = pytest.mark.anyio

SOURCE = SourceConfig(
    source_id="example-ckan",
    protocol=SourceProtocol.CKAN,
    endpoint="https://ckan.example.org/api/3/action",
    catalog_page=None,
    filter=CkanFilter("res_format:GeoTIFF", "organization"),
    max_requests_per_run=20,
    max_pages_per_run=None,
    rows_per_page=None,
    full_every_days=7,
    robots_exception=None,
    maturity=Maturity.STABLE,
    enabled=True,
    country=None,
    dedupe_rank=1,
)

PACKAGE = {
    "id": "secret-id-1",
    "title": "Geheimer Titel",
    "notes": "x" * 5000,
    "resources": [{"url": "https://files.example.org/a.tif", "description": "y" * 3000, "format": "GeoTIFF"}],
}
ROW = {"id": "secret-id-1", "title": "Geheimer Titel", "res_url": ["https://files.example.org/a.tif"], "spatial": ""}


def _page(results: list[Any], elapsed: float = 0.5) -> GatewayResponse:
    body = {"success": True, "result": {"count": len(results), "results": results}}
    return GatewayResponse(200, {"content-encoding": "gzip"}, json.dumps(body).encode(), elapsed)


def _package(key: str) -> dict[str, Any]:
    return {**PACKAGE, "id": key}


FIRST = [_package(f"secret-id-{i}") for i in (1, 2, 3)]
SECOND = [_package(f"secret-id-{i}") for i in (4, 5)]


async def test_sizes_times_by_offset_and_by_key_and_the_fields_that_come_back() -> None:
    asked: list[dict[str, Any]] = []

    async def fetch(url: str, *, params: dict[str, Any]) -> GatewayResponse:
        asked.append(params)
        if "fl" in params:
            return _page([ROW] * 3, 0.2)
        if params["start"]:
            return _page(SECOND, 1.0)
        if "id:{" in params["fq"]:
            return _page(SECOND, 9.5)
        return _page(FIRST, 0.4)

    text = await measure_page(fetch, replace(SOURCE, rows_per_page=50))
    # The first page, the second by offset and by key twice, alternating, then fl.
    assert [(p["start"], "id:{" in p["fq"], p.get("fl")) for p in asked] == [
        (0, False, None),
        (50, False, None),
        (0, True, None),
        (50, False, None),
        (0, True, None),
        (0, False, ",".join(EXTRACT_FIELDS)),
    ]
    assert asked[2]["fq"] == '(res_format:GeoTIFF) AND id:{"secret-id-3" TO *]'
    assert all(p["rows"] == 50 and p["sort"] == "id asc" for p in asked)
    assert "Seiten mit 50 Paketen" in text and "die Quelle sendet gzip" in text
    assert [line.split() for line in text.splitlines() if line.strip().startswith(("Versatz", "Keyset"))] == [
        ["Versatz", "1.0", "s"],
        ["Keyset", "9.5", "s"],
        ["Versatz", "1.0", "s"],
        ["Keyset", "9.5", "s"],
    ]
    assert "dieselben Pakete: ja" in text
    assert "notes" in text and "description" in text
    filled = {line.split()[0]: int(line.split()[1]) for line in text.splitlines()[-len(EXTRACT_FIELDS) :]}
    assert (filled["id"], filled["res_url"], filled["extras_spatial"], filled["notes"]) == (3, 3, 0, 0)
    # Never an address, a key or a value of a package.
    assert not any(word in text for word in ("secret", "Geheim", "example.org", "xxxx"))


async def test_different_pages_by_offset_and_by_key_are_named() -> None:
    async def fetch(url: str, *, params: dict[str, Any]) -> GatewayResponse:
        if "fl" in params:
            return _page([ROW])
        if params["start"]:
            return _page(SECOND[:1])
        return _page(SECOND if "id:{" in params["fq"] else FIRST)

    assert "dieselben Pakete: nein" in await measure_page(fetch, SOURCE)


async def test_an_answer_that_is_no_listing_stops_the_measurement() -> None:
    async def fetch(url: str, *, params: dict[str, Any]) -> GatewayResponse:
        return GatewayResponse(200, {}, b"<html>")

    with pytest.raises(ShapeError):
        await measure_page(fetch, SOURCE)


def test_measure_is_for_a_ckan_source(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["fsdi-stac", "--measure"]) == 1
    assert "--measure is for a ckan source" in capsys.readouterr().err

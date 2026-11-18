"""The measurement of one page of a CKAN listing with and without ``fl`` (Otto, 18.11.2026; plan §12.5)."""

from __future__ import annotations

import json
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
    full_every_days=7,
    robots_exception=None,
    maturity=Maturity.STABLE,
    enabled=True,
)

PACKAGE = {
    "id": "secret-id-1",
    "title": "Geheimer Titel",
    "notes": "x" * 5000,
    "resources": [{"url": "https://files.example.org/a.tif", "description": "y" * 3000, "format": "GeoTIFF"}],
}
ROW = {"id": "secret-id-1", "title": "Geheimer Titel", "res_url": ["https://files.example.org/a.tif"], "spatial": ""}


def _page(results: list[Any]) -> GatewayResponse:
    body = {"success": True, "result": {"count": len(results), "results": results}}
    return GatewayResponse(200, {"content-encoding": "gzip"}, json.dumps(body).encode())


async def test_the_two_pages_their_sizes_and_the_fields_that_come_back() -> None:
    asked: list[dict[str, Any]] = []

    async def fetch(url: str, *, params: dict[str, Any]) -> GatewayResponse:
        asked.append(params)
        return _page([ROW] * 3 if "fl" in params else [PACKAGE] * 3)

    text = await measure_page(fetch, SOURCE)
    assert [p.get("fl") for p in asked] == [None, ",".join(EXTRACT_FIELDS)]
    assert all(p["fq"] == "(res_format:GeoTIFF)" and p["rows"] == 100 for p in asked)
    assert "Messung einer Seite mit 3 Paketen" in text and "die Quelle sendet gzip" in text
    assert "notes" in text and "description" in text
    filled = {line.split()[0]: int(line.split()[1]) for line in text.splitlines()[-len(EXTRACT_FIELDS) :]}
    assert (filled["id"], filled["res_url"], filled["extras_spatial"], filled["notes"]) == (3, 3, 0, 0)
    # Never an address, a key or a value of a package.
    assert not any(word in text for word in ("secret", "Geheim", "example.org", "xxxx"))


async def test_an_answer_that_is_no_listing_stops_the_measurement() -> None:
    async def fetch(url: str, *, params: dict[str, Any]) -> GatewayResponse:
        return GatewayResponse(200, {}, b"<html>")

    with pytest.raises(ShapeError):
        await measure_page(fetch, SOURCE)


def test_measure_is_for_a_ckan_source(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["fsdi-stac", "--measure"]) == 1
    assert "--measure is for a ckan source" in capsys.readouterr().err

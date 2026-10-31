"""The live smoke tests, replayed without the network (M4-27).

``backend/tests_live`` never runs in a pull request (adr/0002 §2), so a call there that
no longer fits a signature only showed up in the daily run: ``search_items`` lost its
default for ``adapters=`` in M4-01b and the smoke was red for five days. This file runs
every test of that directory against a transport double that answers from the recorded
fixtures in ``tests/fixtures``.

What it catches: a signature, an import or an attribute that moved. What it cannot
catch, and is not meant to: the source changing. The fixtures are synthetic, so the
replay stays green when Earth Search changes; the scheduled run is what notices that.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import numpy
import pytest

from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.catalog.registry import FilterKind
from earthx.gateway import Gateway

pytestmark = pytest.mark.anyio

TESTS = Path(__file__).resolve().parent
LIVE = TESTS.parent / "tests_live"
SMOKE_FILES = sorted(LIVE.glob("test_*.py"))

# A minimal TIFF header and a bucket listing, written by hand: there is no recording of
# the DEM bucket (plans/m3/m3-11b-dem-adapter.md §2 measured it by hand).
TIFF_HEADER = b"II*\x00\x08\x00\x00\x00" + b"\x00" * 8
BUCKET_LISTING = b"<ListBucketResult><Prefix></Prefix><CommonPrefixes><Prefix>Copernicus_DSM_COG_10_N00_00_E006_00_DEM/</Prefix></CommonPrefixes></ListBucketResult>"


def _fixture(directory: str, name: str) -> dict[str, Any]:
    return json.loads((TESTS / "fixtures" / directory / f"{name}.json").read_text(encoding="utf-8"))


def _json(payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json=payload)


def _stac_double(directory: str) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path.endswith("/search"):
            return _json(_fixture(directory, "search_page_1"))
        if request.method == "GET" and "/items/" in path:
            # The live test asks for the id the search just returned; the recorded item has its own.
            return _json({**_fixture(directory, "item"), "id": path.rsplit("/", 1)[-1]})
        raise AssertionError(f"the double has no answer for {request.method} {request.url}")

    return handler


def _coverage_double(request: httpx.Request) -> httpx.Response:
    if request.method == "GET" and request.url.path.endswith("/aggregate"):
        return _json(_fixture("earth_search", "aggregate_complete"))
    raise AssertionError(f"the double has no answer for {request.method} {request.url}")


def _dem_double(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/tileList.txt"):
        return httpx.Response(304, headers={"etag": request.headers.get("if-none-match", "")})
    if path.endswith(".tif"):
        return httpx.Response(206, content=TIFF_HEADER[:16])
    if request.url.params.get("list-type"):
        return httpx.Response(200, content=BUCKET_LISTING)
    raise AssertionError(f"the double has no answer for {request.method} {request.url}")


def _filtered_items() -> list[dict[str, Any]]:
    """Three synthetic scenes per filter: a range at 10, 40 and 90 % of its span, the values in turn."""
    items: list[dict[str, Any]] = []
    for index, share in enumerate((0.1, 0.4, 0.9)):
        properties: dict[str, Any] = {"datetime": "2024-06-01T10:00:00Z"}
        for search_filter in SENTINEL_2_L2A.search_filters:
            if search_filter.kind is FilterKind.RANGE:
                low, high = search_filter.minimum or 0.0, search_filter.maximum or 0.0
                properties[search_filter.property] = low + share * (high - low)
            else:
                properties[search_filter.property] = search_filter.values[index % len(search_filter.values)].value
        items.append({**_fixture("earth_search", "item"), "id": f"SYNTH_FILTERED_{index}", "properties": properties})
    return items


def _keeps(item: dict[str, Any], query: dict[str, dict[str, Any]]) -> bool:
    for name, operators in query.items():
        value = item["properties"].get(name)
        if "in" in operators and value not in operators["in"]:
            return False
        if "gte" in operators and not value >= operators["gte"]:
            return False
        if "lte" in operators and not value <= operators["lte"]:
            return False
    return True


def _filtering_double(request: httpx.Request) -> httpx.Response:
    """Applies the query extension to synthetic scenes, in a search and an aggregation, as the source does (plan §6.2)."""
    if request.method == "POST" and request.url.path.endswith("/search"):
        body = json.loads(request.content)
        kept = [item for item in _filtered_items() if _keeps(item, body.get("query", {}))]
        return _json({"type": "FeatureCollection", "numberMatched": len(kept), "features": kept[: body["limit"]], "links": []})
    if request.method == "GET" and request.url.path.endswith("/aggregate"):
        kept = [item for item in _filtered_items() if _keeps(item, json.loads(request.url.params.get("query", "{}")))]
        cells = [{"key": "4/8/5", "frequency": len(kept)}] if kept else []
        return _json({"aggregations": [
            {"name": "total_count", "value": len(kept)},
            {"name": "grid_geotile_frequency", "buckets": cells},
            {"name": "datetime_frequency", "buckets": []},
        ]})
    if request.method == "GET" and request.url.path.endswith("/queryables"):
        return _json({"type": "object", "properties": {"eo:cloud_cover": {"$ref": "https://example.invalid/eo"}}})
    raise AssertionError(f"the double has no answer for {request.method} {request.url}")


def _scl_scenes() -> list[dict[str, Any]]:
    """Six synthetic scenes with a classification asset on an allowed asset host and a footprint, 50 % clouds and 20 % no data each."""
    host = SENTINEL_2_L2A.source.asset_hosts[0]
    footprint = {"type": "Polygon", "coordinates": [[[10.0, 47.0], [11.0, 47.0], [11.0, 48.0], [10.0, 48.0], [10.0, 47.0]]]}
    return [
        {
            **_fixture("earth_search", "item"),
            "id": f"SYNTH_SCL_{index}",
            "geometry": footprint,
            "properties": {"datetime": "2024-06-01T10:00:00Z", "eo:cloud_cover": 50.0, "s2:nodata_pixel_percentage": 20.0},
            "assets": {"scl": {"href": f"https://{host}/synth/{index}/SCL.tif"}},
        }
        for index in range(6)
    ]


def _scl_double(request: httpx.Request) -> httpx.Response:
    if request.method == "POST" and request.url.path.endswith("/search"):
        return _json({"type": "FeatureCollection", "features": _scl_scenes(), "links": []})
    raise AssertionError(f"the double has no answer for {request.method} {request.url}")


def _replay_rasters(module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    """The reading of a raster does not go through the gateway: stand a synthetic classification in its place."""
    from earthx.access.aoi_clouds import AoiClouds
    from earthx.api import aoi_cloud_filter

    def counts(path: Any, aoi: Any, classes: Any) -> AoiClouds:
        # The whole tile (east edge at 11.1 E) has 20 % no data like the scene, as the five pixels below have. The whole
        # footprint of a scene (west edge at 10 E, east edge at 11 E) is 50 % clouds like the scene; any AOI 10 %.
        if aoi["coordinates"][0][1] == [11.1, 46.9]:
            return AoiClouds(cloud_pixels=40, data_pixels=80, aoi_pixels=100, resolution=320.0)
        on_footprint = aoi["coordinates"][0][1] == [11.0, 47.0]
        return AoiClouds(cloud_pixels=50 if on_footprint else 10, data_pixels=100, aoi_pixels=100, resolution=80.0)

    tile = {"type": "Polygon", "coordinates": [[[9.9, 46.9], [11.1, 46.9], [11.1, 48.1], [9.9, 48.1], [9.9, 46.9]]]}
    monkeypatch.setattr(module, "tile_polygon", lambda scene: tile)
    # Four valid pixels, two of them in a cloud class (8 and 9): the share of the scenes above, 50 %.
    monkeypatch.setattr(module, "RESOLVER", lambda host, port: ("93.184.216.34",))
    monkeypatch.setattr(module, "read_whole_file", lambda scene: (numpy.array([8, 9, 4, 5, 0], dtype="uint8"), 0))
    monkeypatch.setattr(module, "measure_aoi_clouds", counts)
    monkeypatch.setattr(aoi_cloud_filter, "measure_aoi_clouds", counts)
    monkeypatch.setattr(module, "open_asset_ref", lambda ref, policy, resolver, **kwargs: str(ref.href))


# Where a smoke test also reads a raster, the replay patches that step as well.
RASTER_REPLAYS: dict[str, Callable[[ModuleType, pytest.MonkeyPatch], None]] = {
    "test_aoi_cloud_filter_live": _replay_rasters,
}

DOUBLES: dict[str, Callable[[httpx.Request], httpx.Response]] = {
    "test_earth_search_smoke": _stac_double("earth_search"),
    "test_coverage_smoke": _coverage_double,
    "test_cop_dem_smoke": _dem_double,
    "test_search_filters_live": _filtering_double,
    "test_aoi_cloud_filter_live": _scl_double,
}


def _load(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"tests_live_dry_run.{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _smoke_tests(module: ModuleType) -> list[Callable[..., Any]]:
    return [
        function
        for name, function in inspect.getmembers(module, inspect.iscoroutinefunction)
        if name.startswith("test_") and function.__module__ == module.__name__
    ]


def _replaying(module: ModuleType, handler: Callable[[httpx.Request], httpx.Response]) -> None:
    """Make the module's own ``open_gateway`` build a gateway over the double."""

    async def no_sleep(seconds: float) -> None:
        return None

    def gateway(policy: Any) -> Gateway:
        return Gateway(
            policy,
            transport=httpx.MockTransport(handler),
            resolve=lambda host, port: ("93.184.216.34",),
            sleep=no_sleep,
        )

    module.Gateway = gateway


def test_every_smoke_file_has_a_double() -> None:
    """A new file in ``tests_live`` without a double would run unchecked in every PR."""
    assert SMOKE_FILES, "no live smoke file found"
    assert {path.stem for path in SMOKE_FILES} == set(DOUBLES)


@pytest.mark.parametrize("path", SMOKE_FILES, ids=lambda path: path.stem)
async def test_the_live_smoke_replays_against_the_recorded_fixtures(
    path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load(path)
    tests = _smoke_tests(module)
    assert tests, f"{path.name} holds no smoke test"
    _replaying(module, DOUBLES[path.stem])
    if path.stem in RASTER_REPLAYS:
        RASTER_REPLAYS[path.stem](module, monkeypatch)

    for smoke in tests:
        assert list(inspect.signature(smoke).parameters) == ["gateway"], (
            f"{smoke.__name__} takes more than the gateway; teach this replay how to supply it"
        )
        async with module.open_gateway() as gateway:
            await smoke(gateway=gateway)


async def _replay_filters(handler: Callable[[httpx.Request], httpx.Response]) -> None:
    path = next(path for path in SMOKE_FILES if path.stem == "test_search_filters_live")
    module = _load(path)
    _replaying(module, handler)
    async with module.open_gateway() as gateway:
        await module.test_the_registry_filters_still_fit_their_source(gateway=gateway)


async def test_the_filter_smoke_fails_when_the_source_ignores_a_filter() -> None:
    """A source that answers every `query` as if there were none is what the test is there to find (DS-02c)."""

    def ignoring(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/search"):
            body = json.loads(request.content)
            body.pop("query", None)
            return _filtering_double(httpx.Request("POST", request.url, content=json.dumps(body)))
        if request.url.path.endswith("/aggregate"):
            return _filtering_double(httpx.Request("GET", request.url.copy_remove_param("query")))
        return _filtering_double(request)

    with pytest.raises(AssertionError, match="the sample says|does not narrow"):
        await _replay_filters(ignoring)


async def test_the_filter_smoke_names_a_value_the_registry_lacks() -> None:
    """A new processing baseline in the last 30 days is one the registry has no line for yet (DS-02c)."""

    def newer(request: httpx.Request) -> httpx.Response:
        response = _filtering_double(request)
        if request.method == "POST" and request.url.path.endswith("/search"):
            if not json.loads(request.content)["datetime"].startswith("2024"):
                document = json.loads(response.content)
                for item in document["features"]:
                    item["properties"]["s2:processing_baseline"] = "99.99"
                return _json(document)
        return response

    with pytest.raises(AssertionError, match="a new value of s2:processing_baseline"):
        await _replay_filters(newer)

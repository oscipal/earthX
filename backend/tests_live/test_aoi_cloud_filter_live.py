"""T-D, DS-03: does the cloud share in the AOI still fit the real classification? (plan §6.13)

Two things only the source can answer, through the gateway and a real read of the classification:

* the classes of the registry (``mask.cloud_classes``) count the same pixels as the source's own ``eo:cloud_cover``:
  over the whole file the share is equal to a few thousandths (plan §6.2.5);
* the filter of the search works against the real thing: a search with a range on the share inside an AOI keeps
  scenes whose measured share lies in it, and a second response goes on where the first stopped;
* the second measure, no data in the AOI (``earthx:aoi_nodata``, Otto 31.10.2026), is the share of the pixels of class 0
  over the whole file, close to the item's own ``s2:nodata_pixel_percentage``, and a search with both ranges keeps
  what meets both while it reads each scene once.

* DS-03c (Otto, 05.11.2026): a pass whose scenes are read together has shares between those of its scenes, the coverage of
  the AOI by the outlines of the source's scenes is what an independent computation in UTM gives, and a search per pass keeps
  or drops whole passes by the area-weighted value of their scenes, again computed independently.

Small on purpose (adr/0005 §3.6, K5): one scene read whole (about a megabyte), two searches of two responses at most; the
pass test reads one pass of two or three scenes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import numpy
import numpy.typing
import pytest
import rasterio
from rasterio.warp import transform_geom
from shapely.geometry import Polygon, box, mapping, shape
from shapely.ops import unary_union

from earthx.access.aoi_clouds import measure_aoi_clouds, measure_aoi_pass
from earthx.access.crop_rules import mosaic_order
from earthx.access.outlines import AoiOutlines, outline_of
from earthx.access.resolve import open_asset_ref, resolve_asset
from earthx.adapters import ADAPTER_SPECS, SearchParams, search_items
from earthx.api import aoi_cloud_filter
from earthx.api.aoi_cloud_filter import AoiMeasurer, SceneMeasure, read_aoi_request, run_filter
from earthx.api.dependencies import policy_from_registry
from earthx.api.pass_filter import day_of, mosaic_ordered, pass_key_of, run_pass_filter
from earthx.catalog.datasets import registry
from earthx.catalog.registry import AoiMeasure, group_by_overpass
from earthx.catalog.search_filters import RangeCondition
from earthx.gateway import CachingResolver, Gateway, ReadSlots, Resolver
from earthx.gateway.gdal import gdal_options

REGISTRY = registry()
SENTINEL_2_L2A = registry().get("sentinel-2-c1-l2a")

pytestmark = [pytest.mark.anyio, pytest.mark.live_dataset("sentinel-2-c1-l2a")]

# The box and month of the plan's measurement (DS-02 §6.2): 42 scenes of mixed sky, in a window long closed.
BBOX = (10.0, 47.0, 11.0, 48.0)
WINDOW = (datetime(2024, 6, 1, tzinfo=timezone.utc), datetime(2024, 6, 30, 23, 59, 59, tzinfo=timezone.utc))
PERIOD = "2024-06-01T00:00:00Z/2024-06-30T23:59:59Z"
# 10 km by 10 km inside the box.
AOI = {
    "type": "Polygon",
    "coordinates": [[[10.4, 47.4], [10.55, 47.4], [10.55, 47.5], [10.4, 47.5], [10.4, 47.4]]],
}
CONFIG = SENTINEL_2_L2A


# What the replay of `tests/test_live_smoke_dry_run.py` puts a double in place of: the resolver and the reading of a
# raster, neither of which goes through the gateway's transport.
RESOLVER: Resolver = CachingResolver()


@asynccontextmanager
async def open_gateway() -> AsyncIterator[Gateway]:
    async with Gateway(policy_from_registry(REGISTRY)) as gateway:
        yield gateway


@pytest.fixture
async def gateway() -> AsyncIterator[Gateway]:
    async with open_gateway() as gateway:
        yield gateway


def read_whole_file(scene: dict) -> tuple[numpy.typing.NDArray, float | None]:
    """The classification of ``scene`` at full resolution, and its nodata value."""
    policy = policy_from_registry(REGISTRY)
    path = open_asset_ref(resolve_asset(scene, CONFIG, CONFIG.mask.asset), policy, RESOLVER)
    with rasterio.Env(**gdal_options(policy)), rasterio.open(path) as source:
        return source.read(1), source.nodata


def tile_polygon(scene: dict) -> dict:
    """The whole file of the classification as an AOI: its bounds in EPSG:4326, so every pixel of the tile is in it."""
    policy = policy_from_registry(REGISTRY)
    path = open_asset_ref(resolve_asset(scene, CONFIG, CONFIG.mask.asset), policy, RESOLVER)
    with rasterio.Env(**gdal_options(policy)), rasterio.open(path) as source:
        return transform_geom(source.crs, "EPSG:4326", mapping(box(*source.bounds)))


async def _sample(gateway: Gateway, limit: int) -> list[dict]:
    params = SearchParams(bbox=BBOX, start=WINDOW[0], end=WINDOW[1], limit=limit)
    page = await search_items(CONFIG, params, adapters=ADAPTER_SPECS, gateway=gateway)
    return list(page.items)


def _mixed_sky(items: list[dict]) -> dict:
    scene = next((item for item in items if 20 <= item["properties"]["eo:cloud_cover"] <= 80), None)
    assert scene is not None, "no scene of the sample has between 20 and 80 % clouds"
    return scene


async def test_the_classes_of_the_registry_count_what_the_source_calls_cloud(gateway: Gateway) -> None:
    items = await _sample(gateway, 20)
    scene = _mixed_sky(items)
    values, nodata = read_whole_file(scene)
    valid = values != nodata
    share = 100 * numpy.isin(values, list(CONFIG.mask.cloud_classes))[valid].sum() / valid.sum()
    assert share == pytest.approx(scene["properties"]["eo:cloud_cover"], abs=0.05)


async def test_a_search_with_a_range_on_the_share_in_the_aoi_keeps_what_it_measures(gateway: Gateway) -> None:
    request = read_aoi_request(
        CONFIG.dataset_id,
        {AoiMeasure.CLOUD_SHARE: RangeCondition(None, 50.0)},
        datetime_value=PERIOD,
        bbox=None,
        intersects=AOI,
        earthx_aoi=None,
    )
    policy = policy_from_registry(REGISTRY)
    measurer = AoiMeasurer(
        CONFIG,
        request.aoi,
        policy=policy,
        resolver=RESOLVER,
        gdal_options=gdal_options(policy),
        slots=ReadSlots(policy),
        cache=None,
    )

    async def fetch_page(marker: str | None):
        params = SearchParams(intersects=AOI, start=WINDOW[0], end=WINDOW[1], limit=100, page_token=marker)
        return await search_items(CONFIG, params, adapters=ADAPTER_SPECS, gateway=gateway)

    first = await run_filter(request, fetch_page=fetch_page, measure=measurer, limit=3, token=None)
    assert first.items, "no scene of the sample is under 50 % clouds in the AOI"
    assert first.unreadable == 0
    for item in first.items:
        assert item["properties"]["earthx:aoi_cloud_cover"] <= 50.0
        assert item["properties"]["earthx:aoi_measure"]["data_pixels"] > 0
    assert first.next_token is not None
    second = await run_filter(request, fetch_page=fetch_page, measure=measurer, limit=3, token=first.next_token)
    assert {item["id"] for item in first.items}.isdisjoint(item["id"] for item in second.items)
    assert second.checked > first.checked


async def test_the_whole_footprint_of_a_scene_is_close_to_its_cloud_cover(gateway: Gateway) -> None:
    items = await _sample(gateway, 20)
    scene = _mixed_sky(items)
    policy = policy_from_registry(REGISTRY)
    path = open_asset_ref(resolve_asset(scene, CONFIG, CONFIG.mask.asset), policy, RESOLVER)
    with rasterio.Env(**gdal_options(policy)):
        counts = measure_aoi_clouds(path, scene["geometry"], CONFIG.mask.cloud_classes)
    # A coarse level of MODE overviews, not the file: the plan's measured error at mixed sky is at most 1.9 points.
    assert counts.cloud_percent == pytest.approx(scene["properties"]["eo:cloud_cover"], abs=2.5)


async def test_no_data_in_the_whole_tile_is_the_share_of_pixels_of_class_zero(gateway: Gateway) -> None:
    items = await _sample(gateway, 20)
    # The scene with the most no data in the sample, so that the count has something to find (an edge of a swath).
    scene = max(items, key=lambda item: item["properties"].get("s2:nodata_pixel_percentage") or 0.0)
    values, nodata = read_whole_file(scene)
    assert nodata == 0, "class 0 of the classification is the nodata value of the file (plan §6.7)"
    class_zero = 100 * float((values == 0).sum()) / values.size

    policy = policy_from_registry(REGISTRY)
    path = open_asset_ref(resolve_asset(scene, CONFIG, CONFIG.mask.asset), policy, RESOLVER)
    with rasterio.Env(**gdal_options(policy)):
        counts = measure_aoi_clouds(path, tile_polygon(scene), CONFIG.mask.cloud_classes)
    # A coarse level of MODE overviews, not the file. The bound is the cloud share's (plan §6.2.4: at most 1.9 points at
    # mixed sky); for no data it was not measured separately.
    assert SceneMeasure.of(counts).nodata_percent == pytest.approx(class_zero, abs=2.5)
    # The item's own figure, where the source gives one; it comes from the product, not from the classification.
    reported = scene["properties"].get("s2:nodata_pixel_percentage")
    if reported is not None:
        assert class_zero == pytest.approx(reported, abs=1.0)


async def test_a_search_with_both_ranges_keeps_what_meets_both_and_reads_each_scene_once(gateway: Gateway) -> None:
    both = {AoiMeasure.CLOUD_SHARE: RangeCondition(None, 50.0), AoiMeasure.NODATA_SHARE: RangeCondition(None, 50.0)}
    request = read_aoi_request(
        CONFIG.dataset_id, both, datetime_value=PERIOD, bbox=None, intersects=AOI, earthx_aoi=None
    )
    policy = policy_from_registry(REGISTRY)
    measurer = AoiMeasurer(
        CONFIG,
        request.aoi,
        policy=policy,
        resolver=RESOLVER,
        gdal_options=gdal_options(policy),
        slots=ReadSlots(policy),
        cache=None,
    )

    async def fetch_page(marker: str | None):
        params = SearchParams(intersects=AOI, start=WINDOW[0], end=WINDOW[1], limit=100, page_token=marker)
        return await search_items(CONFIG, params, adapters=ADAPTER_SPECS, gateway=gateway)

    reads: list[str] = []
    real = aoi_cloud_filter.measure_aoi_clouds

    def counting(path, aoi, classes):
        reads.append(path.item_id)
        return real(path, aoi, classes)

    # The scenes the test before left measuring (a response keeps the ones it did not take) would call `counting` too,
    # whenever their thread gets to run, and be counted as reads of this search.
    await aoi_cloud_filter.settle()
    aoi_cloud_filter.measure_aoi_clouds = counting
    try:
        first = await run_filter(request, fetch_page=fetch_page, measure=measurer, limit=3, token=None)
        await aoi_cloud_filter.settle()
    finally:
        aoi_cloud_filter.measure_aoi_clouds = real
    assert first.items, "no scene of the sample has at most 50 % clouds and at most 50 % no data in the AOI"
    assert first.unreadable == 0
    for item in first.items:
        properties = item["properties"]
        assert properties["earthx:aoi_cloud_cover"] <= 50.0
        assert round(100 - properties["earthx:aoi_measure"]["data_percent"], 1) <= 50.0
    assert len(reads) >= first.checked and len(reads) == len(set(reads)), "each scene is read once, for both ranges"


# -- DS-03c: per pass and the coverage of the AOI ---------------------------------------------------------------------

#: A box of 80 km by 111 km: it reaches over more than one tile, so that a pass has several scenes in it.
WIDE = {"type": "Polygon", "coordinates": [[[10.0, 47.0], [11.0, 47.0], [11.0, 48.0], [10.0, 48.0], [10.0, 47.0]]]}


def _utm(geometry: dict) -> object:
    """``geometry`` in UTM 32 N, which holds 10 to 11 degrees east: a projection other than the one under test."""
    return shape(transform_geom("EPSG:4326", "EPSG:32632", geometry))


async def _passes(gateway: Gateway, aoi: dict) -> dict[tuple[str, ...], list[dict]]:
    """The scenes of the window over ``aoi`` by overpass, as the results list and the mosaic job group them (up to two pages)."""
    items: list[dict] = []
    marker = None
    for _ in range(2):
        params = SearchParams(intersects=aoi, start=WINDOW[0], end=WINDOW[1], limit=100, page_token=marker)
        page = await search_items(CONFIG, params, adapters=ADAPTER_SPECS, gateway=gateway)
        items += [dict(item) for item in page.items]
        marker = page.next_page_token
        if marker is None:
            break
    return {key: [dict(item) for item in group] for key, group in group_by_overpass(items, CONFIG.viewer).items()}


def _independent_coverage(scenes: list[dict], aoi: dict) -> float:
    covered = unary_union([_utm(scene["geometry"]) for scene in scenes]).intersection(_utm(aoi))
    return 100 * covered.area / _utm(aoi).area


async def test_the_coverage_of_the_aoi_is_what_an_independent_computation_in_utm_gives(gateway: Gateway) -> None:
    passes = await _passes(gateway, WIDE)
    outlines = AoiOutlines(WIDE)
    assert passes, "the window holds no scene over the box"
    for scenes in passes.values():
        together = outlines.coverage([_outline(scene) for scene in scenes])
        assert together == pytest.approx(_independent_coverage(scenes, WIDE), abs=1.0)
        for scene in scenes:
            alone = outlines.coverage([_outline(scene)])
            assert alone == pytest.approx(_independent_coverage([scene], WIDE), abs=1.0)
            assert alone <= together + 0.1, "a pass covers at least what each of its scenes does"


def _outline(scene: dict):
    return outline_of(scene)


async def test_a_search_per_pass_keeps_or_drops_whole_passes_by_the_weighted_value(gateway: Gateway) -> None:
    passes = await _passes(gateway, WIDE)
    wanted = RangeCondition(None, 30.0)
    request = read_aoi_request(
        CONFIG.dataset_id, {}, datetime_value=None, bbox=None, intersects=None, earthx_aoi=None,
        evaluate_pass=True, scene_conditions={"eo:cloud_cover": wanted}, filters=CONFIG.search_filters,
    )

    async def fetch_page(marker: str | None):
        params = SearchParams(intersects=WIDE, start=WINDOW[0], end=WINDOW[1], limit=100, page_token=marker)
        return await search_items(CONFIG, params, adapters=ADAPTER_SPECS, gateway=gateway)

    async def never(items):
        raise AssertionError("a search over properties alone reads no raster")

    outcome = await run_pass_filter(
        request, fetch_page=fetch_page, group_of=pass_key_of(CONFIG.viewer), day_of=day_of(CONFIG.viewer), order_of=mosaic_ordered(CONFIG, CONFIG.mask.asset),
        measure_pass=never, limit=1000, token=None,
    )
    kept = {item["id"] for item in outcome.items}
    for key, scenes in passes.items():
        order = mosaic_order({scene["id"]: scene["properties"].get("proj:code") for scene in scenes})
        by_id = {scene["id"]: scene for scene in scenes}
        taken = Polygon()
        total = weighted = 0.0
        for name in order:
            area = _utm(by_id[name]["geometry"]).difference(taken).area
            taken = unary_union([taken, _utm(by_id[name]["geometry"])])
            total += area
            weighted += area * by_id[name]["properties"]["eo:cloud_cover"]
        value = weighted / total
        names = {scene["id"] for scene in scenes}
        if abs(value - 30.0) < 1.0:
            continue  # too close to the bound for two projections to agree
        assert (names <= kept) if value < 30.0 else names.isdisjoint(kept), f"pass {key}: {value:.1f} %"


async def test_the_scenes_of_a_pass_read_together_have_a_share_between_those_read_alone(gateway: Gateway) -> None:
    passes = await _passes(gateway, WIDE)
    scenes = next((group for group in passes.values() if len(group) >= 2), None)
    assert scenes is not None, "no pass of two scenes over the box in the window"
    order = mosaic_ordered(CONFIG, CONFIG.mask.asset)(scenes)
    policy = policy_from_registry(REGISTRY)
    paths = [open_asset_ref(resolve_asset(scene, CONFIG, CONFIG.mask.asset), policy, RESOLVER) for scene in order]
    with rasterio.Env(**gdal_options(policy)):
        together = measure_aoi_pass(paths, WIDE, CONFIG.mask.cloud_classes)
        alone = [measure_aoi_clouds(path, WIDE, CONFIG.mask.cloud_classes) for path in paths]
    shares = [counts.cloud_percent for counts in alone if counts.cloud_percent is not None]
    # Every pixel of the pass is a pixel of one of its scenes, read on one common level: the share lies between theirs,
    # with the room two levels of MODE overviews take (plan §6.2.4: at most 1.9 points at mixed sky).
    assert min(shares) - 3.0 <= together.cloud_percent <= max(shares) + 3.0
    assert together.data_pixels * together.resolution**2 <= sum(c.data_pixels * c.resolution**2 for c in alone) * 1.02
    assert sum(together.class_pixels.values()) == together.data_pixels

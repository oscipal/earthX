"""The fourth adapter capability over a source without aggregation: pull footprints
through the ordinary search, rasterize them ourselves, and never claim more than a
sample (adr/0004 §5 Option 6, M2-09b plan §4.2, §10 F5).

Nothing here reaches the network — the gateway's transport and resolver are under
test control, exactly as in ``test_eopf_stac.py``, whose fixtures this file reuses
for the shapes that do not need to be wrong on purpose. What is checked is what
only exists at this seam: rasterizing a centroid onto the geotile grid, the cap
that bounds how far this way ever pages, the declared-sample completeness, and an
upstream item that cannot be rasterized honestly.
"""

from __future__ import annotations

import functools
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from earthx.adapters.eopf_sample_coverage import SAMPLE_PAGES, sample_coverage
from earthx.adapters.federated_search import UnknownCollection
from earthx.catalog.coverage import (
    Completeness,
    CoverageProviderMismatch,
    CoverageQuery,
    CoverageResult,
    CoverageSource,
    UpstreamCoverageShapeError,
    geotile_key,
)
from earthx.catalog.datasets import SENTINEL_2_L2A, SENTINEL_2_L2A_ZARR3
from earthx.catalog.registry import DatasetRegistry
from earthx.gateway import Policy
from earthx.gateway.client import Gateway

pytestmark = pytest.mark.anyio

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "eopf_stac"
HOST = "stac.core.eopf.eodc.eu"
POLICY = Policy(allowed_hosts=frozenset({HOST}))
DATASET_ID = SENTINEL_2_L2A_ZARR3.dataset_id

# The centroids of `search_page_1.json`'s two rectangles, computed by hand from
# their corners (an axis-aligned rectangle's centroid is the average of its
# corners) — the value the adapter's own shapely computation must agree with.
ITEM_1_CENTROID = (-28.0, 71.6)
ITEM_2_CENTROID = (-29.0, 71.6)


def load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def ok(name: str) -> httpx.Response:
    return httpx.Response(200, json=load(name))


def body_of(request: httpx.Request) -> dict[str, Any]:
    return json.loads(request.content)


def _public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


def gateway_for(handler: Callable[[httpx.Request], httpx.Response]) -> Gateway:
    async def sleep(seconds: float) -> None:
        return None

    return Gateway(POLICY, transport=httpx.MockTransport(handler), resolve=_public, sleep=sleep)


def answering(*responses: httpx.Response) -> tuple[Gateway, list[httpx.Request]]:
    seen: list[httpx.Request] = []
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return gateway_for(handler), seen


def _page(*features: dict[str, Any]) -> dict[str, Any]:
    """A minimal search answer of this source's own shape, for a case that needs a
    feature the fixtures do not carry (a missing geometry, a cloud filter)."""
    return {
        "type": "FeatureCollection",
        "numberReturned": len(features),
        "features": list(features),
        "links": [{"rel": "self", "type": "application/json", "href": "https://stac.core.eopf.eodc.invalid/search"}],
    }


def _feature(feature_id: str, *, geometry: Any, cloud_cover: float | None = None) -> dict[str, Any]:
    properties: dict[str, Any] = {"datetime": "2026-09-21T14:18:21Z"}
    if cloud_cover is not None:
        properties["eo:cloud_cover"] = cloud_cover
    return {
        "type": "Feature",
        "stac_version": "1.1.0",
        "stac_extensions": [],
        "id": feature_id,
        "collection": DATASET_ID,
        "geometry": geometry,
        "bbox": [-1.0, -1.0, 1.0, 1.0],
        "properties": properties,
        "assets": {},
        "links": [],
    }


class FakeCache:
    """A cache in a dict, so a repeat call proves it reused ``search_items``'s own
    per-page cache instead of asking the source again."""

    def __init__(self) -> None:
        self.entries: dict[str, dict[str, Any]] = {}

    async def get(self, key: str) -> dict[str, Any] | None:
        return self.entries.get(key)

    async def set(self, key: str, value: dict[str, Any], *, ttl_s: float, dataset_id: str) -> None:
        self.entries[key] = value


# A bbox to give every query below a spatial filter — without one, `level_for_viewport`
# clamps to `WORLD_LEVEL_CAP` (6, below the dataset's own z8), and the two rectangles
# of `search_page_1.json` collapse into one cell at that coarser level.
AOI = (-30.0, 71.0, -27.0, 72.0)


class TestHappyPath:
    async def test_each_item_lands_in_the_cell_of_its_own_centroid(self) -> None:
        gateway, _ = answering(ok("search_page_1"), ok("search_empty"))

        result = await sample_coverage(
            CoverageQuery(dataset_id=DATASET_ID, level=8, bbox=AOI), SENTINEL_2_L2A_ZARR3, gateway=gateway
        )

        assert {cell.key for cell in result.cells} == {
            geotile_key(*ITEM_1_CENTROID, 8),
            geotile_key(*ITEM_2_CENTROID, 8),
        }
        assert all(cell.count == 1 for cell in result.cells)

    async def test_the_histogram_buckets_by_month(self) -> None:
        gateway, _ = answering(ok("search_page_1"), ok("search_empty"))

        result = await sample_coverage(
            CoverageQuery(dataset_id=DATASET_ID, level=8, bbox=AOI), SENTINEL_2_L2A_ZARR3, gateway=gateway
        )

        assert len(result.histogram) == 1
        assert result.histogram[0].start.isoformat() == "2026-09-01T00:00:00+00:00"
        assert result.histogram[0].count == 2

    async def test_the_answer_is_a_declared_sample_with_no_total(self) -> None:
        gateway, _ = answering(ok("search_page_1"), ok("search_empty"))

        result = await sample_coverage(
            CoverageQuery(dataset_id=DATASET_ID, level=8, bbox=AOI), SENTINEL_2_L2A_ZARR3, gateway=gateway
        )

        assert result.completeness is Completeness.SAMPLE
        assert result.total_count is None
        # A sample must never silently turn into a footprint view — only a checked
        # total does that (M2-07c's replacement rule).
        assert result.footprints_advised is False


class TestTheCap:
    """Otto, plan §10 F5: five pages of a hundred, never more."""

    async def test_a_source_with_endless_pages_is_stopped_at_five(self) -> None:
        # A single response, repeated by `answering` for every request: its own
        # `next` link never runs out, so only the cap can end the loop.
        gateway, seen = answering(ok("search_page_1"))

        result = await sample_coverage(
            CoverageQuery(dataset_id=DATASET_ID, level=8), SENTINEL_2_L2A_ZARR3, gateway=gateway
        )

        assert len(seen) == SAMPLE_PAGES
        assert sum(cell.count for cell in result.cells) == 2 * SAMPLE_PAGES
        assert result.completeness is Completeness.SAMPLE

    async def test_an_empty_answer_is_a_valid_sample_not_an_error(self) -> None:
        gateway, seen = answering(ok("search_empty"))

        result = await sample_coverage(
            CoverageQuery(dataset_id=DATASET_ID, level=8), SENTINEL_2_L2A_ZARR3, gateway=gateway
        )

        assert len(seen) == 1
        assert result.cells == ()
        assert result.histogram == ()
        assert result.completeness is Completeness.SAMPLE


class TestUpstreamMisbehaving:
    async def test_an_item_without_geometry_is_refused_not_silently_dropped(self) -> None:
        page = _page(_feature("SYNTH_NO_GEOM", geometry=None))
        gateway, _ = answering(httpx.Response(200, json=page))

        with pytest.raises(UpstreamCoverageShapeError, match="geometry"):
            await sample_coverage(CoverageQuery(dataset_id=DATASET_ID, level=8), SENTINEL_2_L2A_ZARR3, gateway=gateway)

    async def test_an_item_without_a_datetime_is_refused(self) -> None:
        feature = _feature("SYNTH_NO_DATE", geometry={"type": "Point", "coordinates": [5.0, 45.0]})
        del feature["properties"]["datetime"]
        gateway, _ = answering(httpx.Response(200, json=_page(feature)))

        with pytest.raises(UpstreamCoverageShapeError, match="datetime"):
            await sample_coverage(CoverageQuery(dataset_id=DATASET_ID, level=8), SENTINEL_2_L2A_ZARR3, gateway=gateway)


class TestCloudFilter:
    """This source's search body carries no filter of any kind (plan §4.2) — the
    filter is applied to what came back, not asked of the source."""

    async def test_only_items_under_the_threshold_are_counted(self) -> None:
        clear = _feature(
            "CLEAR",
            geometry={"type": "Point", "coordinates": list(ITEM_1_CENTROID)},
            cloud_cover=5.0,
        )
        cloudy = _feature(
            "CLOUDY",
            geometry={"type": "Point", "coordinates": list(ITEM_2_CENTROID)},
            cloud_cover=80.0,
        )
        gateway, _ = answering(httpx.Response(200, json=_page(clear, cloudy)))

        result = await sample_coverage(
            CoverageQuery(dataset_id=DATASET_ID, level=8, bbox=AOI, max_cloud_cover=20.0),
            SENTINEL_2_L2A_ZARR3,
            gateway=gateway,
        )

        assert sum(cell.count for cell in result.cells) == 1
        assert result.cells[0].key == geotile_key(*ITEM_1_CENTROID, 8)

    async def test_an_item_without_a_reading_is_left_out_under_a_filter(self) -> None:
        """Can't show it would have passed a filter it cannot check — left out, not
        counted on faith."""
        unmeasured = _feature("UNMEASURED", geometry={"type": "Point", "coordinates": list(ITEM_1_CENTROID)})
        gateway, _ = answering(httpx.Response(200, json=_page(unmeasured)))

        result = await sample_coverage(
            CoverageQuery(dataset_id=DATASET_ID, level=8, max_cloud_cover=20.0),
            SENTINEL_2_L2A_ZARR3,
            gateway=gateway,
        )

        assert result.cells == ()


class TestIntersectsBecomesABbox:
    """`federated_search.SearchParams` has no `intersects` field — reduced to its
    bounds before the search goes out (module docstring)."""

    async def test_the_search_carries_the_polygons_bounds_as_a_bbox(self) -> None:
        gateway, seen = answering(ok("search_empty"))
        area = {"type": "Polygon", "coordinates": [[[5.0, 45.0], [15.0, 45.0], [15.0, 55.0], [5.0, 45.0]]]}

        await sample_coverage(
            CoverageQuery(dataset_id=DATASET_ID, level=8, intersects=area), SENTINEL_2_L2A_ZARR3, gateway=gateway
        )

        assert body_of(seen[0])["bbox"] == pytest.approx([5.0, 45.0, 15.0, 55.0])


class TestTheLevelCapHoldsAtTheSeam:
    """adr/0004 §5: the level the answer reports is the level it was allowed to use,
    the same guarantee `earth_search_coverage` gives — it must not depend on the
    route of M2-05b having clamped the viewport zoom already."""

    async def test_a_level_finer_than_the_dataset_cap_is_clamped(self) -> None:
        gateway, _ = answering(ok("search_empty"))

        result = await sample_coverage(
            CoverageQuery(dataset_id=DATASET_ID, level=20, bbox=(5.0, 45.0, 15.0, 55.0)),
            SENTINEL_2_L2A_ZARR3,
            gateway=gateway,
        )

        assert result.level == SENTINEL_2_L2A_ZARR3.coverage.max_geotile_level


class TestDispatchMistakes:
    """Asking the wrong way for a dataset is an error, not an empty map."""

    async def test_an_unknown_dataset_is_the_search_path_s_error(self) -> None:
        gateway, seen = answering(ok("search_empty"))

        with pytest.raises(UnknownCollection):
            await sample_coverage(
                CoverageQuery(dataset_id="no-such-dataset", level=8),
                gateway=gateway,
                registry=DatasetRegistry((SENTINEL_2_L2A_ZARR3,)),
            )

        assert seen == []

    async def test_a_dataset_answered_another_way_is_refused(self) -> None:
        gateway, seen = answering(ok("search_empty"))

        with pytest.raises(CoverageProviderMismatch):
            await sample_coverage(
                CoverageQuery(dataset_id=SENTINEL_2_L2A.dataset_id, level=8), SENTINEL_2_L2A, gateway=gateway
            )

        assert seen == []

    async def test_an_entry_for_another_dataset_is_refused(self) -> None:
        gateway, seen = answering(ok("search_empty"))

        with pytest.raises(CoverageProviderMismatch):
            await sample_coverage(CoverageQuery(dataset_id=DATASET_ID, level=8), SENTINEL_2_L2A, gateway=gateway)

        assert seen == []


class TestTheSearchCacheIsReused:
    """No second cache for the same answer — `search_items`'s own per-page one
    (module docstring)."""

    async def test_a_page_already_seen_is_not_asked_for_again(self) -> None:
        gateway, seen = answering(ok("search_page_1"), ok("search_empty"))
        cache = FakeCache()
        query = CoverageQuery(dataset_id=DATASET_ID, level=8)

        await sample_coverage(query, SENTINEL_2_L2A_ZARR3, gateway=gateway, cache=cache)
        await sample_coverage(query, SENTINEL_2_L2A_ZARR3, gateway=gateway, cache=cache)

        assert len(seen) == 2


async def test_bound_to_its_collaborators_it_fits_the_seam() -> None:
    """The seam of `catalog` asks for `(query, config)` and nothing else — the same
    shape `aggregate_coverage` fits (`test_earth_search_coverage.py`)."""
    gateway, _ = answering(ok("search_empty"))
    source: CoverageSource = functools.partial(sample_coverage, gateway=gateway)

    answer = await source(CoverageQuery(dataset_id=DATASET_ID, level=8), SENTINEL_2_L2A_ZARR3)

    assert isinstance(answer, CoverageResult)
    assert answer.grid == "geotile"
    assert answer.counting == "centroid"

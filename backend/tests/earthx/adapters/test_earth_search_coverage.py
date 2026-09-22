"""The fourth adapter capability: what leaves the house, and what comes back.

Nothing here reaches the network — the gateway's transport and resolver are under test
control, and the answers come from the synthetic fixtures next door. What is checked
is the part that only exists at this seam: the query string of ``GET /aggregate`` as it
was measured on 20.09.2026, the AOI surviving the URL limit or being named as reduced
(adr/0004 §3.4), an upstream that misbehaves, and a cache that may fail (E5).
"""

from __future__ import annotations

import functools
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest

from earthx.adapters.earth_search import UnknownCollection
from earthx.adapters.earth_search_coverage import (
    AGGREGATIONS,
    MAX_AOI_POINTS,
    TTL_WORLD_OVERVIEW_S,
    aggregate_coverage,
)
from earthx.adapters.federated_search import TTL_CLOSED_S, TTL_OPEN_EDGE_S
from earthx.catalog.coverage import (
    WORLD_LEVEL_CAP,
    Completeness,
    CoverageProviderMismatch,
    CoverageQuery,
    CoverageResult,
    CoverageSource,
    UpstreamCoverageShapeError,
)
from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.catalog.registry import CoverageProvider
from earthx.gateway import UpstreamError, UpstreamTimeout

from .conftest import answering, gateway_for, load

pytestmark = pytest.mark.anyio

UTC = timezone.utc
NOW = datetime.now(UTC)


def ok(name: str) -> httpx.Response:
    return httpx.Response(200, json=load(name))


def params_of(request: httpx.Request) -> dict[str, str]:
    return dict(request.url.params)


def ring(points: int) -> list[list[float]]:
    """A closed ring with ``points`` corners, as a client would upload an AOI."""
    corners = [[5.0 + index * 0.001, 45.0 + index * 0.001] for index in range(points - 1)]
    return [*corners, corners[0]]


def polygon(points: int) -> dict[str, Any]:
    return {"type": "Polygon", "coordinates": [ring(points)]}


class FakeCache:
    """A cache in a dict, which records what it kept and for how long."""

    def __init__(self, *, fails: bool = False) -> None:
        self.entries: dict[str, dict[str, Any]] = {}
        self.ttls: dict[str, float] = {}
        self.datasets: dict[str, str] = {}
        self._fails = fails

    async def get(self, key: str) -> dict[str, Any] | None:
        if self._fails:
            raise RuntimeError("the cache is having a bad day")
        return self.entries.get(key)

    async def set(self, key: str, value: dict[str, Any], *, ttl_s: float, dataset_id: str) -> None:
        if self._fails:
            raise RuntimeError("the cache is having a bad day")
        self.entries[key] = value
        self.ttls[key] = ttl_s
        self.datasets[key] = dataset_id


async def test_one_request_carries_cells_total_and_histogram(dataset_id: str) -> None:
    """adr/0004 §3.1: the probe may only compare numbers from the same answer."""
    gateway, seen = answering(ok("aggregate_complete"))

    result = await aggregate_coverage(CoverageQuery(dataset_id=dataset_id, level=8), gateway=gateway)

    assert len(seen) == 1
    assert seen[0].method == "GET"
    assert seen[0].url.path.endswith("/aggregate")
    assert params_of(seen[0])["aggregations"] == ",".join(AGGREGATIONS)
    assert result.counted == 42
    assert result.total_count == 42
    assert len(result.histogram) == 2


async def test_the_query_string_is_the_one_that_was_measured(dataset_id: str) -> None:
    gateway, seen = answering(ok("aggregate_complete"))

    await aggregate_coverage(
        CoverageQuery(
            dataset_id=dataset_id,
            level=8,
            bbox=(5.0, 45.0, 15.0, 55.0),
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 12, 31, tzinfo=UTC),
            max_cloud_cover=20.0,
        ),
        gateway=gateway,
    )

    params = params_of(seen[0])
    assert params["collections"] == SENTINEL_2_L2A.source.source_collection_id
    assert params["grid_geotile_frequency_precision"] == "8"
    assert params["bbox"] == "5.0,45.0,15.0,55.0"
    # Measured 20.09.2026: the source ignores this parameter, so it is not sent.
    assert "datetime_frequency_interval" not in params
    assert params["datetime"] == "2024-01-01T00:00:00Z/2024-12-31T00:00:00Z"
    assert json.loads(params["query"]) == {"eo:cloud_cover": {"lt": 20.0}}


async def test_a_world_query_sends_no_area_at_all(dataset_id: str) -> None:
    gateway, seen = answering(ok("aggregate_complete"))

    await aggregate_coverage(CoverageQuery(dataset_id=dataset_id, level=3), gateway=gateway)

    params = params_of(seen[0])
    assert "bbox" not in params
    assert "intersects" not in params
    assert "datetime" not in params


class TestRuleVOnRealAnswers:
    """The probe, against the two shapes the source actually produces."""

    async def test_equal_sums_are_complete(self, dataset_id: str) -> None:
        gateway, _ = answering(ok("aggregate_complete"))
        result = await aggregate_coverage(CoverageQuery(dataset_id=dataset_id, level=8), gateway=gateway)
        assert result.completeness is Completeness.COMPLETE

    async def test_the_truncation_is_caught_although_overflow_says_zero(self, dataset_id: str) -> None:
        """The fixture is the z8 shape: cells short of the total, ``overflow: 0``."""
        gateway, _ = answering(ok("aggregate_truncated"))
        result = await aggregate_coverage(CoverageQuery(dataset_id=dataset_id, level=8), gateway=gateway)
        assert result.counted == 42
        assert result.total_count == 90
        assert result.completeness is Completeness.TRUNCATED


class TestTheAoiAndTheUrlLimit:
    """adr/0004 §3.4: the AOI fits, or the answer says it was reduced."""

    async def test_a_small_polygon_goes_out_as_it_is(self, dataset_id: str) -> None:
        gateway, seen = answering(ok("aggregate_complete"))
        area = polygon(10)

        result = await aggregate_coverage(
            CoverageQuery(dataset_id=dataset_id, level=8, intersects=area), gateway=gateway
        )

        assert json.loads(params_of(seen[0])["intersects"]) == area
        assert result.completeness is Completeness.COMPLETE

    async def test_a_polygon_too_long_for_the_url_is_reduced_and_said_to_be(self, dataset_id: str) -> None:
        """One request goes out in the end, and it is not the one that was asked."""
        gateway, seen = answering(ok("aggregate_complete"))
        area = polygon(3000)

        result = await aggregate_coverage(
            CoverageQuery(dataset_id=dataset_id, level=8, intersects=area), gateway=gateway
        )

        # The first shape never left the house: `check_url` refused it on length, so
        # the source only ever saw the reduced one (no 414 is ever provoked).
        assert len(seen) == 1
        sent = json.loads(params_of(seen[0])["intersects"])
        assert len(sent["coordinates"][0]) <= MAX_AOI_POINTS + 1
        assert result.completeness is Completeness.TRUNCATED

    async def test_a_polygon_that_does_not_fit_even_thinned_falls_back_to_the_box(self, dataset_id: str) -> None:
        """Plan §7 test 2: the AOI becomes a box, one request goes out, and it says so.

        The coordinates are deliberately long ones — thinning alone still leaves a
        query string over the limit, which is the case the bounding box exists for.
        """
        gateway, seen = answering(ok("aggregate_complete"))
        ring = [[5.000000000000001 + index * 1e-9, 45.000000000000001 + index * 1e-9] for index in range(6000)]
        area = {"type": "Polygon", "coordinates": [[*ring, ring[0]]]}

        result = await aggregate_coverage(
            CoverageQuery(dataset_id=dataset_id, level=8, intersects=area), gateway=gateway
        )

        assert len(seen) == 1
        params = params_of(seen[0])
        assert "bbox" in params
        assert "intersects" not in params
        assert result.completeness is Completeness.TRUNCATED

    async def test_a_small_ring_beside_a_large_one_survives_the_thinning(self, dataset_id: str) -> None:
        """A shared stride would cut a small hole down to two points, which is no ring.

        The source answers a 400 to that, and because only ``UrlTooLong`` makes the
        adapter try the next shape, the bounding-box fallback would never be reached.
        """
        gateway, seen = answering(ok("aggregate_complete"))
        small = [[10.0, 50.0], [10.1, 50.0], [10.1, 50.1], [10.0, 50.0]]
        area = {"type": "MultiPolygon", "coordinates": [[ring(5000)], [small]]}

        await aggregate_coverage(CoverageQuery(dataset_id=dataset_id, level=8, intersects=area), gateway=gateway)

        sent = json.loads(params_of(seen[0])["intersects"])
        assert sent["type"] == "MultiPolygon"
        for shape in sent["coordinates"]:
            for outline in shape:
                assert len(outline) >= 4
                assert outline[0] == outline[-1]

    async def test_the_reduced_outline_is_still_a_closed_ring(self, dataset_id: str) -> None:
        gateway, seen = answering(ok("aggregate_complete"))

        await aggregate_coverage(
            CoverageQuery(dataset_id=dataset_id, level=8, intersects=polygon(3000)), gateway=gateway
        )

        sent = json.loads(params_of(seen[0])["intersects"])["coordinates"][0]
        assert sent[0] == sent[-1]
        assert len(sent) >= 4


class TestUpstreamMisbehaving:
    """Nothing malformed becomes an answer, and nothing malformed is kept."""

    async def test_an_upstream_error_reaches_the_caller(self, dataset_id: str) -> None:
        gateway, _ = answering(httpx.Response(400, json={"code": "BadRequest", "description": "nope"}))
        cache = FakeCache()

        with pytest.raises(UpstreamError):
            await aggregate_coverage(CoverageQuery(dataset_id=dataset_id, level=8), gateway=gateway, cache=cache)

        assert cache.entries == {}

    async def test_a_timeout_reaches_the_caller(self, dataset_id: str) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("too slow", request=request)

        with pytest.raises(UpstreamTimeout):
            await aggregate_coverage(CoverageQuery(dataset_id=dataset_id, level=8), gateway=gateway_for(handler))

    async def test_a_503_is_retried_and_then_reaches_the_caller(self, dataset_id: str) -> None:
        """A read is safe to repeat, so the gateway tries three times before giving up."""
        gateway, seen = answering(httpx.Response(503, text="busy"))
        cache = FakeCache()

        with pytest.raises(UpstreamError) as raised:
            await aggregate_coverage(CoverageQuery(dataset_id=dataset_id, level=8), gateway=gateway, cache=cache)

        assert raised.value.status_code == 503
        assert len(seen) == 3
        assert cache.entries == {}

    async def test_a_malformed_answer_is_not_kept_either(self, dataset_id: str) -> None:
        gateway, _ = answering(httpx.Response(200, json={"aggregations": "nope"}))
        cache = FakeCache()

        with pytest.raises(UpstreamCoverageShapeError):
            await aggregate_coverage(CoverageQuery(dataset_id=dataset_id, level=8), gateway=gateway, cache=cache)

        assert cache.entries == {}

    @pytest.mark.parametrize(
        "payload",
        [
            [],  # not an object
            {"aggregations": "nope"},  # not a list
            {"aggregations": [{"name": "grid_geotile_frequency", "buckets": "nope"}]},
            {"aggregations": [{"name": "grid_geotile_frequency", "buckets": [{"key": "8/1/1"}]}]},  # no count
            {"aggregations": [{"name": "grid_geotile_frequency", "buckets": [{"frequency": 1}]}]},  # no key
            # A key that is not on the grid must not reach a map layer.
            {"aggregations": [{"name": "grid_geotile_frequency", "buckets": [{"key": "3/9/0", "frequency": 1}]}]},
        ],
    )
    async def test_an_answer_that_is_not_an_aggregation_is_refused(self, dataset_id: str, payload: Any) -> None:
        gateway, _ = answering(httpx.Response(200, json=payload))

        with pytest.raises(UpstreamCoverageShapeError):
            await aggregate_coverage(CoverageQuery(dataset_id=dataset_id, level=8), gateway=gateway)

    async def test_a_histogram_bucket_without_an_instant_is_refused(self, dataset_id: str) -> None:
        payload = {
            "aggregations": [
                {"name": "total_count", "value": 1},
                {"name": "grid_geotile_frequency", "buckets": [{"key": "8/1/1", "frequency": 1}]},
                {"name": "datetime_frequency", "buckets": [{"key": "whenever", "frequency": 1}]},
            ]
        }
        gateway, _ = answering(httpx.Response(200, json=payload))

        with pytest.raises(UpstreamCoverageShapeError):
            await aggregate_coverage(CoverageQuery(dataset_id=dataset_id, level=8), gateway=gateway)

    async def test_a_missing_total_is_truncated_rather_than_an_error(self, dataset_id: str) -> None:
        """A source without a total is the M2-09b case, and it is a legitimate answer."""
        payload = {"aggregations": [{"name": "grid_geotile_frequency", "buckets": [{"key": "8/1/1", "frequency": 7}]}]}
        gateway, _ = answering(httpx.Response(200, json=payload))

        result = await aggregate_coverage(CoverageQuery(dataset_id=dataset_id, level=8), gateway=gateway)

        assert result.total_count is None
        assert result.completeness is Completeness.TRUNCATED
        assert result.footprints_advised is False


class TestTheCache:
    """E5: an empty or broken cache makes this slower, never wrong."""

    async def test_the_second_ask_is_answered_without_a_request(self, dataset_id: str) -> None:
        gateway, seen = answering(ok("aggregate_complete"))
        cache = FakeCache()
        query = CoverageQuery(dataset_id=dataset_id, level=8)

        first = await aggregate_coverage(query, gateway=gateway, cache=cache)
        second = await aggregate_coverage(query, gateway=gateway, cache=cache)

        assert len(seen) == 1
        assert first.from_cache is False
        assert second.from_cache is True
        assert second.cells == first.cells
        assert second.completeness is first.completeness

    async def test_a_cache_that_throws_gives_the_same_answer(self, dataset_id: str) -> None:
        gateway, _ = answering(ok("aggregate_complete"))
        query = CoverageQuery(dataset_id=dataset_id, level=8)

        without = await aggregate_coverage(query, gateway=gateway, cache=None)
        broken = await aggregate_coverage(query, gateway=gateway, cache=FakeCache(fails=True))

        assert broken.cells == without.cells
        assert broken.total_count == without.total_count
        assert broken.completeness is without.completeness
        assert broken.from_cache is False

    async def test_a_row_of_an_older_shape_counts_as_a_miss(self, dataset_id: str) -> None:
        gateway, seen = answering(ok("aggregate_complete"), ok("aggregate_complete"))
        cache = FakeCache()
        query = CoverageQuery(dataset_id=dataset_id, level=8)

        await aggregate_coverage(query, gateway=gateway, cache=cache)
        for key in cache.entries:
            cache.entries[key] = {"v": 0, "cells": [], "histogram": []}
        again = await aggregate_coverage(query, gateway=gateway, cache=cache)

        assert len(seen) == 2
        assert again.from_cache is False

    @pytest.mark.parametrize(
        "row",
        [
            {"v": 1, "cells": [{"k": "8/1/1"}], "histogram": []},  # a cell without a count
            {"v": 1, "cells": [{"n": 3}], "histogram": []},  # a count without a cell
            {"v": 1, "cells": [], "histogram": [{"n": 3}]},  # a bucket without an instant
            {"v": 1, "cells": ["8/1/1"], "histogram": []},  # not even a dict
        ],
    )
    async def test_a_damaged_row_of_this_very_version_counts_as_a_miss(self, dataset_id: str, row: Any) -> None:
        """E5: a bad cache row makes the request slower, it does not break it."""
        gateway, seen = answering(ok("aggregate_complete"), ok("aggregate_complete"))
        cache = FakeCache()
        query = CoverageQuery(dataset_id=dataset_id, level=8)

        await aggregate_coverage(query, gateway=gateway, cache=cache)
        for key in cache.entries:
            cache.entries[key] = row
        again = await aggregate_coverage(query, gateway=gateway, cache=cache)

        assert len(seen) == 2
        assert again.from_cache is False
        assert again.counted == 42

    async def test_two_levels_of_the_same_filter_are_two_entries(self, dataset_id: str) -> None:
        gateway, seen = answering(ok("aggregate_complete"), ok("aggregate_complete"))
        cache = FakeCache()
        area = (5.0, 45.0, 15.0, 55.0)

        await aggregate_coverage(CoverageQuery(dataset_id=dataset_id, level=6, bbox=area), gateway=gateway, cache=cache)
        await aggregate_coverage(CoverageQuery(dataset_id=dataset_id, level=8, bbox=area), gateway=gateway, cache=cache)

        assert len(seen) == 2
        assert len(cache.entries) == 2

    async def test_the_key_carries_no_coordinate(self, dataset_id: str) -> None:
        """The key is an opaque hash, so no AOI is stored outside the payload."""
        gateway, _ = answering(ok("aggregate_complete"))
        cache = FakeCache()

        await aggregate_coverage(
            CoverageQuery(dataset_id=dataset_id, level=8, bbox=(5.25, 45.75, 15.25, 55.75)),
            gateway=gateway,
            cache=cache,
        )

        key = next(iter(cache.entries))
        # Otto's answer to F6: a readable prefix in front of an opaque digest, so rows
        # of this kind can be found without decoding anything.
        assert key.startswith("coverage:")
        assert len(key) == len("coverage:") + 64
        for coordinate in ("5.25", "45.75", "15.25", "55.75"):
            assert coordinate not in key

    @pytest.mark.parametrize(
        ("query_kwargs", "expected"),
        [
            # Nothing filtered at all: the world overview, kept for a day (Otto, F3).
            ({}, TTL_WORLD_OVERVIEW_S),
            # A window well behind the moving edge of the archive (adr/0005 rule II).
            ({"end": NOW - timedelta(days=30), "bbox": (5.0, 45.0, 15.0, 55.0)}, TTL_CLOSED_S),
            # Right at the edge, where scenes are still being delivered.
            ({"end": NOW - timedelta(days=1), "bbox": (5.0, 45.0, 15.0, 55.0)}, TTL_OPEN_EDGE_S),
            # An open end is always the edge.
            ({"bbox": (5.0, 45.0, 15.0, 55.0)}, TTL_OPEN_EDGE_S),
        ],
    )
    async def test_the_lifetime_follows_the_window(self, dataset_id: str, query_kwargs: Any, expected: float) -> None:
        gateway, _ = answering(ok("aggregate_complete"))
        cache = FakeCache()

        await aggregate_coverage(
            CoverageQuery(dataset_id=dataset_id, level=6, **query_kwargs), gateway=gateway, cache=cache
        )

        assert list(cache.ttls.values()) == [expected]
        assert list(cache.datasets.values()) == [dataset_id]


class TestTheCapsHoldAtTheSeam:
    """adr/0004 §5: the level the answer reports is the level it was allowed to use.

    The route of M2-05b clamps the viewport zoom as well, but the guarantee may not
    depend on it — if it fell away there, it would fall away without a sound.
    """

    async def test_a_world_query_is_clamped_to_the_world_cap(self, dataset_id: str) -> None:
        gateway, seen = answering(ok("aggregate_complete"))

        result = await aggregate_coverage(CoverageQuery(dataset_id=dataset_id, level=8), gateway=gateway)

        assert params_of(seen[0])["grid_geotile_frequency_precision"] == str(WORLD_LEVEL_CAP)
        assert result.level == WORLD_LEVEL_CAP

    async def test_with_a_bbox_the_dataset_cap_is_what_applies(self, dataset_id: str) -> None:
        gateway, seen = answering(ok("aggregate_complete"))

        result = await aggregate_coverage(
            CoverageQuery(dataset_id=dataset_id, level=14, bbox=(5.0, 45.0, 15.0, 55.0)), gateway=gateway
        )

        assert params_of(seen[0])["grid_geotile_frequency_precision"] == "8"
        assert result.level == 8


class TestDispatchMistakes:
    """Asking the wrong way for a dataset is an error, not an empty map."""

    async def test_an_unknown_dataset_is_the_search_path_s_error(self, dataset_id: str) -> None:
        gateway, _ = answering(ok("aggregate_complete"))

        with pytest.raises(UnknownCollection):
            await aggregate_coverage(CoverageQuery(dataset_id="no-such-dataset", level=8), gateway=gateway)

    async def test_a_dataset_answered_another_way_is_refused(self, dataset_id: str) -> None:
        """``local-sql`` and ``sample`` exist in the registry but not yet in code."""
        gateway, seen = answering(ok("aggregate_complete"))
        config = replace(
            SENTINEL_2_L2A, coverage=replace(SENTINEL_2_L2A.coverage, provider=CoverageProvider.SAMPLE)
        )

        with pytest.raises(CoverageProviderMismatch):
            await aggregate_coverage(CoverageQuery(dataset_id=dataset_id, level=8), config, gateway=gateway)

        assert seen == []

    async def test_an_entry_for_another_dataset_is_refused(self, dataset_id: str) -> None:
        """A handed-in config that does not match the query would answer the wrong thing."""
        gateway, seen = answering(ok("aggregate_complete"))
        other = replace(SENTINEL_2_L2A, dataset_id="something-else")

        with pytest.raises(CoverageProviderMismatch):
            await aggregate_coverage(CoverageQuery(dataset_id=dataset_id, level=8), other, gateway=gateway)

        assert seen == []


async def test_bound_to_its_collaborators_it_fits_the_seam(dataset_id: str) -> None:
    """The seam of ``catalog`` asks for ``(query, config)`` and nothing else.

    That is the shape ``api`` will dispatch through in M2-05b, and the shape the local
    SQL way of adr/0004 §5 has to fit too. Checked by calling it that way rather than
    by trusting the annotation: bind what this way needs, and what is left is the
    question and the dataset.
    """
    gateway, _ = answering(ok("aggregate_complete"))
    source: CoverageSource = functools.partial(aggregate_coverage, gateway=gateway, cache=None)

    answer = await source(CoverageQuery(dataset_id=dataset_id, level=8), SENTINEL_2_L2A)

    assert isinstance(answer, CoverageResult)
    assert answer.grid == "geotile"
    assert answer.counting == "centroid"

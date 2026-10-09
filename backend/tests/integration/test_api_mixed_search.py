"""T-C: the mixed search (M3-13) — fan-out over more than one source, against real
pgstac (two synthetic materialized collections) with a mocked Earth Search transport
(adr/0002: no live network in a PR run).

``test_api_federating.py`` already covers two *federated* sources at once (both real
registry datasets); ``test_api_materialized.py`` covers a lone materialized one. This
file is for the general fan-out itself: paging across the boundary, a source that
fails or times out, the mixed page token's own checks, and the per-source time axis —
none of which either of those files can show with only one materialized collection or
none.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest

from earthx.api import mixed_search
from earthx.api.main import build_app
from earthx.catalog.datasets import REGISTRY, SENTINEL_2_L2A
from earthx.catalog.pgstac import load_collection, upsert_items, use_pgstac_search_path
from earthx.catalog.registry import CoverageProvider, DatasetRegistry, ItemHolding
from earthx.gateway import Gateway, Policy
from tests.conftest import format_without_timestamp

pytestmark = pytest.mark.anyio

EARTH_SEARCH_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "earth_search"
HOST = "earth-search.aws.element84.com"
DATASET_ID = SENTINEL_2_L2A.dataset_id
POLICY = Policy(allowed_hosts=frozenset({HOST}))

# A materialized collection with a time axis, standing in for a future second
# materialized dataset (today there is only the DEM, `time_range=False`) — needed to
# exercise two *native* groups at once (M3-13 §4.2), a combination the real registry
# cannot produce yet.
NATIVE_A = replace(
    SENTINEL_2_L2A,
    dataset_id="earthx-test-mixed-native-a",
    source=replace(
        SENTINEL_2_L2A.source,
        item_holding=ItemHolding.MATERIALIZED,
        source_collection_id="earthx-test-mixed-native-a",
    ),
    coverage=replace(SENTINEL_2_L2A.coverage, provider=CoverageProvider.LOCAL_SQL),
)

# A second materialized collection with a time axis: shares NATIVE_A's source (one
# native group, M3-13 §4.2).
NATIVE_B = replace(
    NATIVE_A,
    dataset_id="earthx-test-mixed-native-b",
    source=replace(NATIVE_A.source, source_collection_id="earthx-test-mixed-native-b"),
)

# The DEM-shaped case: materialized, no time axis (M3-11b F1).
NATIVE_NO_TIME = replace(
    NATIVE_A,
    dataset_id="earthx-test-mixed-native-notime",
    source=replace(NATIVE_A.source, source_collection_id="earthx-test-mixed-native-notime"),
    capabilities=replace(SENTINEL_2_L2A.capabilities, time_range=False),
)

# Routing reads the registry (M4-01a), so the app has to know these collections.
app = build_app(DatasetRegistry((*REGISTRY, NATIVE_A, NATIVE_B, NATIVE_NO_TIME)))


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((EARTH_SEARCH_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _native_item(config: Any, item_id: str, *, datetime_value: str | None = "2026-01-01T00:00:00Z") -> dict[str, Any]:
    properties: dict[str, Any] = {"datetime": datetime_value}
    if datetime_value is None:
        # pgstac needs a valid time shape regardless of `earthx:capabilities.
        # time_range` — the same period-not-instant shape `cop_dem_bucket.py`
        # gives the real DEM (`adr/0009` §10.1).
        properties["start_datetime"] = "2010-01-01T00:00:00Z"
        properties["end_datetime"] = "2015-01-01T00:00:00Z"
    return {
        "id": item_id,
        "type": "Feature",
        "stac_version": "1.0.0",
        "collection": config.dataset_id,
        "bbox": [-1.0, -1.0, 1.0, 1.0],
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0], [-1.0, -1.0]]],
        },
        "properties": properties,
        "assets": {},
        "links": [],
    }


def _load_native(config: Any, item_ids: list[str], **kwargs: Any) -> None:
    with psycopg.connect(autocommit=True) as conn:
        load_collection(conn, config)
        upsert_items(conn, config, [_native_item(config, item_id, **kwargs) for item_id in item_ids])


def _drop_native(config: Any) -> None:
    with psycopg.connect(autocommit=True) as conn:
        use_pgstac_search_path(conn)
        conn.execute("SELECT pgstac.delete_collection(%s)", (config.dataset_id,))


@pytest.fixture
def native_a_loaded(require_postgres_env: None) -> None:
    _load_native(NATIVE_A, ["a0", "a1", "a2"])
    yield
    _drop_native(NATIVE_A)


@pytest.fixture
def native_no_time_loaded(require_postgres_env: None) -> None:
    _load_native(NATIVE_NO_TIME, ["n0", "n1"], datetime_value=None)
    yield
    _drop_native(NATIVE_NO_TIME)


@pytest.fixture
def native_b_loaded(require_postgres_env: None) -> None:
    _load_native(NATIVE_B, ["b0"])
    yield
    _drop_native(NATIVE_B)


@pytest.fixture
def earth_search_collection_loaded(require_postgres_env: None) -> None:
    """Just the real Earth Search collection — not the whole registry
    (``catalog.load``), so a mixed search here always spans exactly the sources a
    test asks for, never the EOPF collection this file's policy does not allow."""
    with psycopg.connect(autocommit=True) as conn:
        load_collection(conn, SENTINEL_2_L2A)
    # The search cache pool commits (`dependencies.cache_pool`, autocommit=True), so
    # a row an earlier run of this file left behind could answer without ever
    # reaching the mocked transport (same reasoning as `test_api_federating.py`).
    with psycopg.connect(autocommit=True) as conn:
        conn.execute("DELETE FROM public.earthx_search_cache")


def _answering(*responses: httpx.Response) -> tuple[Callable[[httpx.Request], httpx.Response], list[httpx.Request]]:
    seen: list[httpx.Request] = []
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return handler, seen


def _public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


def _synthetic_federated_items(n: int) -> list[dict[str, Any]]:
    return [
        {
            "type": "Feature",
            "stac_version": "1.0.0",
            "id": f"synth-{index}",
            "collection": DATASET_ID,
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0], [-1.0, -1.0]]],
            },
            "bbox": [-1.0, -1.0, 1.0, 1.0],
            "properties": {"datetime": f"2026-01-{index + 1:02d}T00:00:00Z"},
            "assets": {},
            "links": [],
        }
        for index in range(n)
    ]


def _paged_earth_search_handler(items: list[dict[str, Any]]) -> Callable[[httpx.Request], httpx.Response]:
    """A minimal stand-in for Earth Search's own keyset paging (`earth_search.py`
    `_search_body`/`_next_marker`) that actually respects the request's own
    ``limit`` — unlike replaying a single canned fixture on every call, which
    hands back the same fixed page size regardless of what was asked for and so
    cannot show a mixed page ever exceeding its own requested size.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        start = 0
        marker = body.get("next")
        if marker is not None:
            start = next(index + 1 for index, item in enumerate(items) if item["id"] == marker)
        limit = body["limit"]
        page = items[start : start + limit]
        links = []
        if start + limit < len(items):
            links.append(
                {
                    "rel": "next",
                    "method": "POST",
                    "href": "https://earth-search.invalid/v1/search",
                    "body": {"next": page[-1]["id"]},
                }
            )
        return httpx.Response(
            200, json={"type": "FeatureCollection", "features": page, "links": links, "numberReturned": len(page)}
        )

    return handler


@asynccontextmanager
async def _client(
    handler: Callable[[httpx.Request], httpx.Response] | Callable[[httpx.Request], Coroutine[Any, Any, httpx.Response]],
) -> AsyncIterator[httpx.AsyncClient]:
    async def sleep(seconds: float) -> None:
        return None

    async with app.router.lifespan_context(app):
        app.state.earthx_gateway = Gateway(POLICY, transport=httpx.MockTransport(handler), resolve=_public, sleep=sleep)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


class TestNativePlusFederated:
    """The primary case: one of this platform's own collections, one federated."""

    async def test_a_mixed_page_carries_items_from_both(
        self, native_a_loaded: None, earth_search_collection_loaded: None
    ) -> None:
        handler, seen = _answering(httpx.Response(200, json=load_fixture("search_page_1")))
        async with _client(handler) as client:
            response = await client.get(
                "/stac/search", params={"collections": f"{NATIVE_A.dataset_id},{DATASET_ID}", "limit": 10}
            )
        assert response.status_code == 200
        body = response.json()
        collections = {item["collection"] for item in body["features"]}
        assert collections == {NATIVE_A.dataset_id, DATASET_ID}
        assert seen[0].headers["host"] == HOST
        assert "incomplete_collections" not in body

    # A "no collections" variant is not repeated here: this file's own fixtures
    # cannot guarantee which real registry collections another test file already
    # left loaded in the shared database (`catalog.load` is idempotent and never
    # deleted) — `test_api_federating.py` already covers that case with the real
    # registry, whose contents that file *does* control.


class TestTwoNativeGroups:
    """Two of this platform's own collections, split by time axis alone — no
    federated source involved. Before M3-13 this went through pgstac in a single
    call sharing one ``datetime``, which was wrong for exactly this combination
    (`_apply_time_axis`'s own docstring); M3-13 fixes it by giving each its own
    group.
    """

    async def test_the_no_time_axis_collection_ignores_datetime_the_other_does_not(
        self, native_a_loaded: None, native_no_time_loaded: None
    ) -> None:
        async with _client(lambda request: httpx.Response(200, json={})) as client:
            response = await client.get(
                "/stac/search",
                params={
                    "collections": f"{NATIVE_A.dataset_id},{NATIVE_NO_TIME.dataset_id}",
                    "datetime": "2030-01-01T00:00:00Z/2030-01-02T00:00:00Z",
                    "limit": 10,
                },
            )
        assert response.status_code == 200
        body = response.json()
        ids_by_collection: dict[str, set[str]] = {}
        for item in body["features"]:
            ids_by_collection.setdefault(item["collection"], set()).add(item["id"])
        assert ids_by_collection.get(NATIVE_A.dataset_id, set()) == set()  # filtered out by the far-off window
        assert ids_by_collection[NATIVE_NO_TIME.dataset_id] == {"n0", "n1"}  # never filtered
        assert body["ignored_filters"] == ["datetime"]
        assert body["ignored_filters_by_collection"] == {NATIVE_NO_TIME.dataset_id: ["datetime"]}


class TestPagingAcrossTheBoundary:
    async def test_the_union_of_every_page_matches_a_single_unbounded_page(
        self, native_a_loaded: None, earth_search_collection_loaded: None
    ) -> None:
        items = _synthetic_federated_items(4)

        async with _client(_paged_earth_search_handler(items)) as client:
            reference = await client.post(
                "/stac/search", json={"collections": [NATIVE_A.dataset_id, DATASET_ID], "limit": 10}
            )
        reference_ids = {(item["collection"], item["id"]) for item in reference.json()["features"]}
        assert reference_ids == {(NATIVE_A.dataset_id, i) for i in ("a0", "a1", "a2")} | {
            (DATASET_ID, item["id"]) for item in items
        }

        seen_ids: set[tuple[str, str]] = set()
        token: str | None = None
        pages = 0
        async with _client(_paged_earth_search_handler(items)) as client:
            while True:
                body_request: dict[str, Any] = {"collections": [NATIVE_A.dataset_id, DATASET_ID], "limit": 2}
                if token:
                    body_request["token"] = token
                response = await client.post("/stac/search", json=body_request)
                assert response.status_code == 200
                body = response.json()
                assert len(body["features"]) <= 2  # never bigger than the requested limit
                for item in body["features"]:
                    key = (item["collection"], item["id"])
                    assert key not in seen_ids, "the same item came back twice across pages"
                    seen_ids.add(key)
                next_link = next((link for link in body["links"] if link["rel"] == "next"), None)
                pages += 1
                if next_link is None or pages > 20:
                    break
                token = next_link["body"]["token"]
        assert seen_ids == reference_ids

    async def test_a_source_that_runs_out_first_frees_its_share_for_the_other(
        self, native_a_loaded: None, earth_search_collection_loaded: None
    ) -> None:
        """The native group (3 items) runs out before Earth Search's own 5; once it
        does, the federated source's own share grows to fill the room the
        finished one no longer needs, instead of staying capped at its old share
        (plan §3, Option 1 over the fixed-share Option 2)."""
        items = _synthetic_federated_items(5)
        counts_per_page: list[dict[str, int]] = []
        token: str | None = None
        async with _client(_paged_earth_search_handler(items)) as client:
            for _ in range(20):
                body_request: dict[str, Any] = {"collections": [NATIVE_A.dataset_id, DATASET_ID], "limit": 2}
                if token:
                    body_request["token"] = token
                response = await client.post("/stac/search", json=body_request)
                assert response.status_code == 200
                body = response.json()
                counts: dict[str, int] = {}
                for item in body["features"]:
                    counts[item["collection"]] = counts.get(item["collection"], 0) + 1
                counts_per_page.append(counts)
                next_link = next((link for link in body["links"] if link["rel"] == "next"), None)
                if next_link is None:
                    break
                token = next_link["body"]["token"]

        native_per_page = [counts.get(NATIVE_A.dataset_id, 0) for counts in counts_per_page]
        federated_per_page = [counts.get(DATASET_ID, 0) for counts in counts_per_page]
        assert sum(native_per_page) == 3
        assert sum(federated_per_page) == 5
        first_page_without_native = next(index for index, count in enumerate(native_per_page) if count == 0)
        assert federated_per_page[first_page_without_native] > federated_per_page[0]


class TestOpenCollections:
    """``open_collections`` (Otto, 30.09.2026, M3-10b): the collections whose source
    still has pages — what the viewer's ±90-day fallback waits on, without reading
    the page token (adr/0005 rule III)."""

    @staticmethod
    async def _pages(client: httpx.AsyncClient, collections: list[str], limit: int) -> list[dict[str, Any]]:
        bodies: list[dict[str, Any]] = []
        token: str | None = None
        for _ in range(20):
            request: dict[str, Any] = {"collections": collections, "limit": limit}
            if token:
                request["token"] = token
            response = await client.post("/stac/search", json=request)
            assert response.status_code == 200
            bodies.append(response.json())
            next_link = next((link for link in bodies[-1]["links"] if link["rel"] == "next"), None)
            if next_link is None:
                return bodies
            token = next_link["body"]["token"]
        raise AssertionError("paging did not end")

    async def test_an_exhausted_source_of_its_own_is_not_open_while_the_other_is(
        self, native_a_loaded: None, earth_search_collection_loaded: None
    ) -> None:
        async with _client(_paged_earth_search_handler(_synthetic_federated_items(20))) as client:
            response = await client.post(
                "/stac/search", json={"collections": [NATIVE_A.dataset_id, DATASET_ID], "limit": 10}
            )
        body = response.json()
        assert sum(item["collection"] == NATIVE_A.dataset_id for item in body["features"]) == 3
        assert body["open_collections"] == [DATASET_ID]

    async def test_collections_sharing_a_source_are_open_while_it_is(
        self, native_a_loaded: None, native_b_loaded: None, earth_search_collection_loaded: None
    ) -> None:
        collections = [NATIVE_A.dataset_id, NATIVE_B.dataset_id, DATASET_ID]
        async with _client(_paged_earth_search_handler(_synthetic_federated_items(20))) as client:
            bodies = await self._pages(client, collections, 4)
        native = {NATIVE_A.dataset_id, NATIVE_B.dataset_id}
        # Page 1: the native group (four items) gave two — both of its collections
        # are open, whichever of them those two came from.
        assert set(bodies[0]["open_collections"]) == native | {DATASET_ID}
        # Once the group has given all four, neither is; the federated one still is.
        group_done = next(
            index
            for index in range(len(bodies))
            if sum(item["collection"] in native for body in bodies[: index + 1] for item in body["features"]) == 4
        )
        assert bodies[group_done]["open_collections"] == [DATASET_ID]
        assert bodies[-1]["open_collections"] == []

    async def test_a_failed_source_is_not_open(self, native_a_loaded: None, earth_search_collection_loaded: None) -> None:
        def unreachable(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        async with _client(unreachable) as client:
            response = await client.post(
                "/stac/search", json={"collections": [NATIVE_A.dataset_id, DATASET_ID], "limit": 2}
            )
        body = response.json()
        assert body["incomplete_collections"] == [{"collection": DATASET_ID, "reason": "unreachable"}]
        assert body["open_collections"] == [NATIVE_A.dataset_id]

    async def test_a_single_source_search_is_open_exactly_while_it_links_a_next_page(
        self, native_a_loaded: None, native_b_loaded: None, earth_search_collection_loaded: None
    ) -> None:
        native = [NATIVE_A.dataset_id, NATIVE_B.dataset_id]
        async with _client(_paged_earth_search_handler(_synthetic_federated_items(5))) as client:
            native_pages = await self._pages(client, native, 2)
            federated_pages = await self._pages(client, [DATASET_ID], 2)
        assert sorted(native_pages[0]["open_collections"]) == sorted(native)
        assert native_pages[-1]["open_collections"] == []
        assert federated_pages[0]["open_collections"] == [DATASET_ID]
        assert federated_pages[-1]["open_collections"] == []


class TestSourceFailure:
    async def test_an_unreachable_source_becomes_incomplete_not_a_500(
        self, native_a_loaded: None, earth_search_collection_loaded: None
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        async with _client(handler) as client:
            response = await client.get(
                "/stac/search", params={"collections": f"{NATIVE_A.dataset_id},{DATASET_ID}", "limit": 10}
            )
        assert response.status_code == 200
        body = response.json()
        assert {item["collection"] for item in body["features"]} == {NATIVE_A.dataset_id}
        assert body["incomplete_collections"] == [{"collection": DATASET_ID, "reason": "unreachable"}]

    async def test_an_upstream_error_becomes_incomplete(
        self, native_a_loaded: None, earth_search_collection_loaded: None
    ) -> None:
        handler, _ = _answering(httpx.Response(503, json={"description": "upstream says no"}))
        async with _client(handler) as client:
            response = await client.get(
                "/stac/search", params={"collections": f"{NATIVE_A.dataset_id},{DATASET_ID}", "limit": 10}
            )
        assert response.status_code == 200
        body = response.json()
        assert body["incomplete_collections"] == [{"collection": DATASET_ID, "reason": "upstream_error"}]

    async def test_an_unrecognised_answer_becomes_incomplete(
        self, native_a_loaded: None, earth_search_collection_loaded: None
    ) -> None:
        handler, _ = _answering(httpx.Response(200, json=["not", "a", "search", "answer"]))
        async with _client(handler) as client:
            response = await client.get(
                "/stac/search", params={"collections": f"{NATIVE_A.dataset_id},{DATASET_ID}", "limit": 10}
            )
        assert response.status_code == 200
        body = response.json()
        assert body["incomplete_collections"] == [{"collection": DATASET_ID, "reason": "unrecognised_answer"}]

    async def test_a_slow_source_times_out_and_becomes_incomplete(
        self, native_a_loaded: None, earth_search_collection_loaded: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mixed_search, "SOURCE_TIMEOUT_S", 0.05)

        async def handler(request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(1.0)
            return httpx.Response(200, json=load_fixture("search_page_1"))  # pragma: no cover - never reached

        async with _client(handler) as client:
            response = await client.get(
                "/stac/search", params={"collections": f"{NATIVE_A.dataset_id},{DATASET_ID}", "limit": 10}
            )
        assert response.status_code == 200
        body = response.json()
        assert body["incomplete_collections"] == [{"collection": DATASET_ID, "reason": "timeout"}]
        assert {item["collection"] for item in body["features"]} == {NATIVE_A.dataset_id}

    async def test_the_failure_is_repeated_on_the_next_page_and_the_source_is_not_asked_again(
        self, native_a_loaded: None, earth_search_collection_loaded: None
    ) -> None:
        # `limit=2` so both sources actually get a nonzero share on every page —
        # with `limit=1` the native group (first in the fixed source order, plan
        # §4.2) would take the only slot until it runs out, and Earth Search
        # would never be asked at all.
        handler, seen = _answering(httpx.Response(503, json={"description": "upstream says no"}))
        async with _client(handler) as client:
            first = await client.post(
                "/stac/search", json={"collections": [NATIVE_A.dataset_id, DATASET_ID], "limit": 2}
            )
            assert first.json()["incomplete_collections"] == [{"collection": DATASET_ID, "reason": "upstream_error"}]
            next_link = next(link for link in first.json()["links"] if link["rel"] == "next")
            second = await client.post(
                "/stac/search",
                json={
                    "collections": [NATIVE_A.dataset_id, DATASET_ID],
                    "limit": 2,
                    "token": next_link["body"]["token"],
                },
            )
        assert second.status_code == 200
        assert second.json()["incomplete_collections"] == [{"collection": DATASET_ID, "reason": "upstream_error"}]
        # The gateway itself retries a failed search (`earth_search.py` asks for
        # `retry=True`) up to its own limit — all of that happens within the
        # *first* page's one call to this source; the point of this assertion is
        # that the count does not grow further on the second page.
        assert len(seen) == 3

    async def test_a_native_group_failure_fails_the_whole_request(
        self,
        native_a_loaded: None,
        earth_search_collection_loaded: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Plan §4.4: our own database has no partial-result story — unlike a
        federated source, a broken native group takes the whole answer down with
        it, exactly as a lone native search already did before this task.
        Simulated with a monkeypatch rather than a genuinely broken row: pgstac's
        own ``collections.id`` is a generated column, so there is no way to write
        a collection this platform's own checks would load but pgstac itself
        chokes on — a fault this deep is exactly the "our own database failing"
        case the plan means, not a shape a real deployment could produce."""

        async def broken(self: Any, group: Any, request: Any, **kwargs: Any) -> Any:
            raise RuntimeError("the database is unavailable")

        monkeypatch.setattr(
            "earthx.api.federating_client.FederatingCoreCrudClient._native_group_page", broken
        )
        handler, _ = _answering(httpx.Response(200, json=load_fixture("search_page_1")))
        # Not a `response.status_code == 500` assertion: `httpx.ASGITransport`
        # re-raises an unhandled server exception into the test instead of
        # turning it into a response the way a real uvicorn process would — this
        # is exactly the propagation the plan asks for, just observed the way
        # this harness surfaces it.
        with pytest.raises(RuntimeError, match="the database is unavailable"):
            async with _client(handler) as client:
                await client.post(
                    "/stac/search", json={"collections": [NATIVE_A.dataset_id, DATASET_ID], "limit": 10}
                )


class TestUnknownCollectionInAMixedList:
    async def test_is_404_before_any_source_is_asked(
        self, native_a_loaded: None, earth_search_collection_loaded: None
    ) -> None:
        handler, seen = _answering(httpx.Response(200, json=load_fixture("search_empty")))
        async with _client(handler) as client:
            response = await client.get(
                "/stac/search", params={"collections": f"{NATIVE_A.dataset_id},{DATASET_ID},does-not-exist"}
            )
        assert response.status_code == 404
        assert seen == []


class TestDisabledExtensionsOnAMixedSearch:
    @pytest.mark.parametrize("key", ["filter", "query", "fields", "sortby"])
    async def test_is_rejected_not_dropped(
        self, native_a_loaded: None, earth_search_collection_loaded: None, key: str
    ) -> None:
        handler, seen = _answering(httpx.Response(200, json=load_fixture("search_empty")))
        async with _client(handler) as client:
            response = await client.get(
                "/stac/search", params={"collections": f"{NATIVE_A.dataset_id},{DATASET_ID}", key: "x"}
            )
        assert response.status_code == 400
        assert seen == []


class TestIntersectsAndIdsOnAMixedSearch:
    async def test_ids_filters_the_native_group_and_reaches_the_federated_one(
        self, native_a_loaded: None, earth_search_collection_loaded: None
    ) -> None:
        handler, seen = _answering(httpx.Response(200, json=load_fixture("search_empty")))
        async with _client(handler) as client:
            response = await client.get(
                "/stac/search", params={"collections": f"{NATIVE_A.dataset_id},{DATASET_ID}", "ids": "a0"}
            )
        assert response.status_code == 200
        assert [item["id"] for item in response.json()["features"]] == ["a0"]
        assert json.loads(seen[0].content)["ids"] == ["a0"]

    async def test_intersects_reaches_both(self, native_a_loaded: None, earth_search_collection_loaded: None) -> None:
        polygon = {
            "type": "Polygon",
            "coordinates": [[[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0], [-1.0, -1.0]]],
        }
        handler, seen = _answering(httpx.Response(200, json=load_fixture("search_page_1")))
        async with _client(handler) as client:
            response = await client.post(
                "/stac/search",
                json={"collections": [NATIVE_A.dataset_id, DATASET_ID], "intersects": polygon, "limit": 10},
            )
        assert response.status_code == 200
        assert json.loads(seen[0].content)["intersects"] == polygon
        assert {item["collection"] for item in response.json()["features"]} == {NATIVE_A.dataset_id, DATASET_ID}


class TestMixedPageTokenValidation:
    """Every request here goes over POST: the mixed page token itself is
    method-agnostic (`_extract_next_marker` reads either shape), but reading it
    back out of the response is far simpler from a POST link's own `body`."""

    async def _mixed_token(self, client: httpx.AsyncClient) -> str:
        response = await client.post(
            "/stac/search", json={"collections": [NATIVE_A.dataset_id, DATASET_ID], "limit": 1}
        )
        next_link = next(link for link in response.json()["links"] if link["rel"] == "next")
        return next_link["body"]["token"]

    async def test_a_token_from_a_different_search_is_refused(
        self, native_a_loaded: None, earth_search_collection_loaded: None
    ) -> None:
        handler, _ = _answering(httpx.Response(200, json=load_fixture("search_page_1")))
        async with _client(handler) as client:
            token = await self._mixed_token(client)
            response = await client.post(
                "/stac/search",
                json={"collections": [NATIVE_A.dataset_id, DATASET_ID], "limit": 1, "ids": ["a1"], "token": token},
            )
        assert response.status_code == 400

    async def test_a_single_collection_adapter_token_is_refused_on_a_mixed_search(
        self, native_a_loaded: None, earth_search_collection_loaded: None
    ) -> None:
        """The reverse of `federated_search`'s own check: an adapter's own
        base64 marker (`{v, d, h, m}`), fed into a search that is mixed this
        time, must not be misread as a mixed token either."""
        foreign = base64.urlsafe_b64encode(
            json.dumps({"v": 2, "d": DATASET_ID, "h": "whatever", "m": "marker"}).encode()
        ).decode("ascii").rstrip("=")
        handler, seen = _answering(httpx.Response(200, json=load_fixture("search_empty")))
        async with _client(handler) as client:
            response = await client.post(
                "/stac/search",
                json={
                    "collections": [NATIVE_A.dataset_id, DATASET_ID],
                    "limit": 1,
                    "token": f"next:{foreign}",
                },
            )
        assert response.status_code == 400
        assert seen == []

    async def test_a_mixed_token_is_refused_once_the_search_is_single_source_again(
        self, native_a_loaded: None, earth_search_collection_loaded: None
    ) -> None:
        handler, _ = _answering(httpx.Response(200, json=load_fixture("search_page_1")))
        async with _client(handler) as client:
            token = await self._mixed_token(client)
            # Same token, but now naming only the native collection — a single
            # source again, which never reads a mixed token.
            response = await client.post(
                "/stac/search", json={"collections": [NATIVE_A.dataset_id], "limit": 1, "token": token}
            )
        assert response.status_code == 400

    async def test_malformed_base64_is_refused(
        self, native_a_loaded: None, earth_search_collection_loaded: None
    ) -> None:
        handler, seen = _answering(httpx.Response(200, json=load_fixture("search_empty")))
        async with _client(handler) as client:
            response = await client.post(
                "/stac/search",
                json={"collections": [NATIVE_A.dataset_id, DATASET_ID], "token": "next:not-valid-base64!!"},
            )
        assert response.status_code == 400
        assert seen == []

    async def test_backward_paging_is_refused(
        self, native_a_loaded: None, earth_search_collection_loaded: None
    ) -> None:
        handler, seen = _answering(httpx.Response(200, json=load_fixture("search_empty")))
        async with _client(handler) as client:
            response = await client.post(
                "/stac/search", json={"collections": [NATIVE_A.dataset_id, DATASET_ID], "token": "prev:whatever"}
            )
        assert response.status_code == 400
        assert seen == []

    async def test_a_token_naming_a_source_outside_this_search_is_refused(
        self, native_a_loaded: None, earth_search_collection_loaded: None, native_no_time_loaded: None
    ) -> None:
        """A token minted for three sources, replayed against a search that now
        names only two — the third source's key does not belong here."""
        handler, _ = _answering(httpx.Response(200, json=load_fixture("search_page_1")))
        async with _client(handler) as client:
            wide = await client.post(
                "/stac/search",
                json={
                    "collections": [NATIVE_A.dataset_id, NATIVE_NO_TIME.dataset_id, DATASET_ID],
                    "limit": 1,
                },
            )
            next_link = next(link for link in wide.json()["links"] if link["rel"] == "next")
            token = next_link["body"]["token"]
            narrower = await client.post(
                "/stac/search",
                json={"collections": [NATIVE_A.dataset_id, DATASET_ID], "limit": 1, "token": token},
            )
        assert narrower.status_code == 400


class TestNoCoordinatesInAFailingMixedSearch:
    def _assert_marker_absent(self, caplog: pytest.LogCaptureFixture, marker: str) -> None:
        assert caplog.records, "the test would prove nothing if nothing was logged"
        for record in caplog.records:
            assert marker not in record.getMessage()
            assert marker not in format_without_timestamp(record)

    async def test_a_failing_source_in_a_mixed_search_logs_no_coordinate(
        self, native_a_loaded: None, earth_search_collection_loaded: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        marker = "13.918279"
        polygon = {
            "type": "Polygon",
            "coordinates": [[[float(marker), 47.0], [12.0, 47.0], [float(marker), 51.0], [float(marker), 47.0]]],
        }
        handler, _ = _answering(httpx.Response(503, json={"description": f"upstream says no near {marker}"}))
        with caplog.at_level(logging.DEBUG):
            async with _client(handler) as client:
                response = await client.post(
                    "/stac/search",
                    json={"collections": [NATIVE_A.dataset_id, DATASET_ID], "intersects": polygon},
                )
        assert response.status_code == 200
        assert response.json()["incomplete_collections"] == [{"collection": DATASET_ID, "reason": "upstream_error"}]
        self._assert_marker_absent(caplog, marker)

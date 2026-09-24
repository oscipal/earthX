"""T-C: the outward STAC API, against real pgstac with Earth Search mocked.

Real Postgres/pgstac (the collection and everything ``FederatingCoreCrudClient``
reads off it), a mocked Earth Search transport (adr/0002: no live network in a PR
run) — the same split M1-06's own tests use, one layer up. ``earthx.catalog.load``
is called directly rather than assumed already run: it is idempotent (M1-04's own
abnahme), so calling it here does not disturb whatever a session already loaded.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest

from earthx.api.main import app
from earthx.catalog.datasets import SENTINEL_2_L2A, SENTINEL_2_L2A_ZARR3
from earthx.catalog.load import main as load_catalog
from earthx.gateway import Gateway, Policy
from earthx.logging import JsonFormatter

pytestmark = pytest.mark.anyio

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "earth_search"
HOST = "earth-search.aws.element84.com"
POLICY = Policy(allowed_hosts=frozenset({HOST}))
DATASET_ID = SENTINEL_2_L2A.dataset_id
ZARR3_DATASET_ID = SENTINEL_2_L2A_ZARR3.dataset_id


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def body_of(request: httpx.Request) -> dict[str, Any]:
    return json.loads(request.content)


def _public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


@pytest.fixture
def require_catalog_loaded(require_postgres_env: None) -> None:
    code = load_catalog()
    assert code == 0
    # The search cache pool commits (autocommit=True, dependencies.cache_pool), so
    # rows outlive one test — and the app's own PG* environment. A row an earlier
    # run of this same file left behind would answer a later test without ever
    # reaching the mocked transport, well within its five-minute open-edge TTL.
    with psycopg.connect(autocommit=True) as conn:
        conn.execute("DELETE FROM public.earthx_search_cache")


@asynccontextmanager
async def _client(handler: Callable[[httpx.Request], httpx.Response]) -> AsyncIterator[httpx.AsyncClient]:
    async def sleep(seconds: float) -> None:
        return None

    async with app.router.lifespan_context(app):
        app.state.earthx_gateway = Gateway(POLICY, transport=httpx.MockTransport(handler), resolve=_public, sleep=sleep)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


def _answering(*responses: httpx.Response) -> tuple[Callable[[httpx.Request], httpx.Response], list[httpx.Request]]:
    seen: list[httpx.Request] = []
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return handler, seen


class TestConformance:
    async def test_landing_page_never_advertises_filter_or_sort(self, require_catalog_loaded: None) -> None:
        """adr/0005 rule VI, and the plan's F2: the federated path cannot honour either."""
        handler, _ = _answering(httpx.Response(200, json=load_fixture("search_empty")))
        async with _client(handler) as client:
            response = await client.get("/stac/")
        assert response.status_code == 200
        classes = " ".join(response.json()["conformsTo"]).lower()
        assert "filter" not in classes
        assert "sort" not in classes

    async def test_stac_version_matches_what_catalog_derives_the_licence_from(
        self, require_catalog_loaded: None
    ) -> None:
        """Otto, on approving the plan: measure the two together, do not assume them.

        ``catalog.collection.STAC_VERSION`` decides the licence word a collection is
        written with (``proprietary`` under 1.0, ``other`` under 1.1); this checks
        that the API's own declared STAC version — which comes from a *different*
        package, ``stac-pydantic``, not from our pin — has not drifted away from it.
        A mismatch here means a served collection's licence value no longer matches
        the STAC version the API claims, and this is where that would first show up.
        """
        from earthx.catalog.collection import STAC_VERSION

        handler, _ = _answering(httpx.Response(200, json=load_fixture("search_empty")))
        async with _client(handler) as client:
            landing = await client.get("/stac/")
            collection = await client.get(f"/stac/collections/{DATASET_ID}")
        assert landing.json()["stac_version"] == STAC_VERSION
        assert collection.json()["stac_version"] == STAC_VERSION

    async def test_a_filter_parameter_is_rejected_not_dropped(self, require_catalog_loaded: None) -> None:
        """The extension being off is not enough on its own — see the client module."""
        handler, _ = _answering(httpx.Response(200, json=load_fixture("search_empty")))
        async with _client(handler) as client:
            get_response = await client.get("/stac/search", params={"collections": DATASET_ID, "filter": "true"})
            post_response = await client.post(
                "/stac/search", json={"collections": [DATASET_ID], "filter": {"op": "=", "args": [1, 1]}}
            )
        assert get_response.status_code == 400
        assert post_response.status_code == 400

    async def test_a_filter_parameter_on_item_collection_is_rejected_too(
        self, require_catalog_loaded: None
    ) -> None:
        """The same gap, one route over: item_collection's own kwargs never carry a
        disabled extension's field at all, so checking them would check nothing."""
        handler, seen = _answering(httpx.Response(200, json=load_fixture("search_empty")))
        async with _client(handler) as client:
            response = await client.get(
                f"/stac/collections/{DATASET_ID}/items", params={"filter": "true"}
            )
        assert response.status_code == 400
        assert seen == []

    async def test_a_sortby_parameter_is_rejected_not_dropped(self, require_catalog_loaded: None) -> None:
        handler, _ = _answering(httpx.Response(200, json=load_fixture("search_empty")))
        async with _client(handler) as client:
            response = await client.get("/stac/search", params={"collections": DATASET_ID, "sortby": "-datetime"})
        assert response.status_code == 400

    async def test_a_get_ids_parameter_reaches_the_source(self, require_catalog_loaded: None) -> None:
        """M3-08: `/search` forwards `ids` now — the M2-17 blanket rejection that
        used to answer this with a plain `400` is gone from this route
        (`TestRejectItemsEndpointKeys` covers where it still applies,
        `/collections/{id}/items`)."""
        handler, seen = _answering(httpx.Response(200, json=load_fixture("search_page_1")))
        async with _client(handler) as client:
            response = await client.get(
                "/stac/search", params={"collections": DATASET_ID, "ids": "SYNTH_T00AAA_20240601T100000_L2A"}
            )
        assert response.status_code == 200
        assert body_of(seen[0])["ids"] == ["SYNTH_T00AAA_20240601T100000_L2A"]

    async def test_a_post_ids_parameter_reaches_the_source(self, require_catalog_loaded: None) -> None:
        handler, seen = _answering(httpx.Response(200, json=load_fixture("search_page_1")))
        async with _client(handler) as client:
            response = await client.post(
                "/stac/search", json={"collections": [DATASET_ID], "ids": ["SYNTH_T00AAA_20240601T100000_L2A"]}
            )
        assert response.status_code == 200
        assert body_of(seen[0])["ids"] == ["SYNTH_T00AAA_20240601T100000_L2A"]

    async def test_a_get_intersects_parameter_reaches_the_source(self, require_catalog_loaded: None) -> None:
        handler, seen = _answering(httpx.Response(200, json=load_fixture("search_page_1")))
        polygon = {"type": "Polygon", "coordinates": [[[1.0, 1.0], [2.0, 1.0], [2.0, 2.0], [1.0, 2.0], [1.0, 1.0]]]}
        async with _client(handler) as client:
            response = await client.get(
                "/stac/search",
                params={"collections": DATASET_ID, "intersects": json.dumps(polygon)},
            )
        assert response.status_code == 200
        assert body_of(seen[0])["intersects"] == polygon

    async def test_a_post_intersects_parameter_reaches_the_source(self, require_catalog_loaded: None) -> None:
        handler, seen = _answering(httpx.Response(200, json=load_fixture("search_page_1")))
        # A different polygon than the GET test above, so the two never collide on
        # the same search-cache row within a shared table (`require_catalog_loaded`
        # only clears it once, at the start of each test).
        polygon = {"type": "Polygon", "coordinates": [[[3.0, 3.0], [4.0, 3.0], [4.0, 4.0], [3.0, 4.0], [3.0, 3.0]]]}
        async with _client(handler) as client:
            response = await client.post(
                "/stac/search", json={"collections": [DATASET_ID], "intersects": polygon}
            )
        assert response.status_code == 200
        assert body_of(seen[0])["intersects"] == polygon

    async def test_an_invalid_intersects_geometry_is_rejected_before_it_reaches_the_source(
        self, require_catalog_loaded: None
    ) -> None:
        """Checked on our side even where the source would take it without a word
        (M3-08 plan §2.2 — a latitude of 999)."""
        handler, seen = _answering(httpx.Response(200, json=load_fixture("search_page_1")))
        bad = {"type": "Point", "coordinates": [10.0, 999.0]}
        async with _client(handler) as client:
            response = await client.post("/stac/search", json={"collections": [DATASET_ID], "intersects": bad})
        assert response.status_code == 400
        assert seen == []

    async def test_malformed_json_in_a_get_intersects_parameter_is_400(self, require_catalog_loaded: None) -> None:
        handler, seen = _answering(httpx.Response(200, json=load_fixture("search_page_1")))
        async with _client(handler) as client:
            response = await client.get("/stac/search", params={"collections": DATASET_ID, "intersects": "{not json"})
        assert response.status_code == 400
        assert seen == []

    async def test_ids_and_intersects_on_item_collection_are_still_rejected(
        self, require_catalog_loaded: None
    ) -> None:
        """M3-08: `GET /collections/{id}/items` is not `item-search` — only
        `/search` forwards either parameter (M2-17's rejection still applies
        here, now for its own reason)."""
        handler, seen = _answering(httpx.Response(200, json=load_fixture("search_empty")))
        async with _client(handler) as client:
            ids_response = await client.get(f"/stac/collections/{DATASET_ID}/items", params={"ids": "some-id"})
            intersects_response = await client.get(
                f"/stac/collections/{DATASET_ID}/items",
                params={"intersects": json.dumps({"type": "Point", "coordinates": [1.0, 1.0]})},
            )
        assert ids_response.status_code == 400
        assert intersects_response.status_code == 400
        assert seen == []


class TestUnknownCollection:
    async def test_get_collection_is_pgstacs_own_404(self, require_catalog_loaded: None) -> None:
        handler, _ = _answering(httpx.Response(200, json=load_fixture("search_empty")))
        async with _client(handler) as client:
            response = await client.get("/stac/collections/does-not-exist")
        assert response.status_code == 404

    async def test_search_on_an_unknown_collection_is_404_not_an_empty_page(
        self, require_catalog_loaded: None
    ) -> None:
        """adr/0005 rule I: a typo must not look like a valid, empty search."""
        handler, seen = _answering(httpx.Response(200, json=load_fixture("search_empty")))
        async with _client(handler) as client:
            response = await client.get("/stac/search", params={"collections": "does-not-exist"})
        assert response.status_code == 404
        assert seen == []  # never asked Earth Search about a collection we do not have


class TestFederatedSearch:
    async def test_get_search_reaches_earth_search_for_the_federated_collection(
        self, require_catalog_loaded: None
    ) -> None:
        handler, seen = _answering(httpx.Response(200, json=load_fixture("search_page_1")))
        async with _client(handler) as client:
            response = await client.get("/stac/search", params={"collections": DATASET_ID, "limit": 2})
        assert response.status_code == 200
        body = response.json()
        assert [item["id"] for item in body["features"]] == [
            "SYNTH_T00AAA_20240601T100000_L2A",
            "SYNTH_T00AAA_20240602T100000_L2A",
        ]
        assert seen[0].headers["host"] == HOST
        assert body_of(seen[0])["collections"] == [SENTINEL_2_L2A.source.source_collection_id]

    async def test_post_search_reaches_earth_search_too(self, require_catalog_loaded: None) -> None:
        handler, seen = _answering(httpx.Response(200, json=load_fixture("search_page_1")))
        async with _client(handler) as client:
            response = await client.post("/stac/search", json={"collections": [DATASET_ID], "limit": 2})
        assert response.status_code == 200
        assert len(response.json()["features"]) == 2
        assert seen[0].headers["host"] == HOST

    async def test_a_missing_collections_argument_is_rejected_with_two_federated_sources(
        self, require_catalog_loaded: None
    ) -> None:
        """adr/0005 rule I says a search without ``collections`` is split per
        collection and merged, but a merge across sources needs a real second
        dataset to build and test against — M2-09b is that second dataset, and a
        search naming no collection now reaches every federated one at once
        (M2-09b plan §10 F3). Nothing is sent upstream: the rejection happens
        before either source is asked."""
        handler, seen = _answering(httpx.Response(200, json=load_fixture("search_empty")))
        async with _client(handler) as client:
            response = await client.get("/stac/search")
        assert response.status_code == 400
        assert seen == []
        detail = response.json()["detail"]
        assert DATASET_ID in detail
        assert ZARR3_DATASET_ID in detail

    async def test_a_search_spanning_more_than_one_source_is_rejected(
        self, require_catalog_loaded: None
    ) -> None:
        """adr/0005 rule I says such a search is split per collection and merged,
        but a merge across heterogeneous sources needs its own task to build and
        test — a best-effort concatenation nobody could verify stayed correct
        would only look tested. Naming both federated datasets explicitly triggers
        the same rejection as leaving ``collections`` out entirely."""
        handler, seen = _answering(httpx.Response(200, json=load_fixture("search_empty")))
        async with _client(handler) as client:
            response = await client.get("/stac/search", params={"collections": f"{DATASET_ID},{ZARR3_DATASET_ID}"})
        assert response.status_code == 400
        assert seen == []

    async def test_the_rejection_message_names_exactly_the_collections_it_saw(
        self, require_catalog_loaded: None
    ) -> None:
        """M2-09b plan §10 F3 (Otto's addition to the recommendation): the sharpened
        message names the collections a caller can choose between, not just that
        there is more than one."""
        handler, seen = _answering(httpx.Response(200, json=load_fixture("search_empty")))
        async with _client(handler) as client:
            response = await client.get("/stac/search", params={"collections": f"{DATASET_ID},{ZARR3_DATASET_ID}"})
        assert seen == []
        detail = response.json()["detail"]
        assert DATASET_ID in detail
        assert ZARR3_DATASET_ID in detail
        assert "name exactly one collection" in detail

    async def test_the_next_link_carries_our_own_marker_not_the_sources(
        self, require_catalog_loaded: None
    ) -> None:
        handler, _ = _answering(httpx.Response(200, json=load_fixture("search_page_1")))
        async with _client(handler) as client:
            response = await client.get("/stac/search", params={"collections": DATASET_ID, "limit": 2})
        next_links = [link for link in response.json()["links"] if link["rel"] == "next"]
        assert len(next_links) == 1
        assert "2024-06-02T10:00:00" not in next_links[0]["href"]

    async def test_the_next_link_pages_through_to_the_second_page(self, require_catalog_loaded: None) -> None:
        handler, seen = _answering(
            httpx.Response(200, json=load_fixture("search_page_1")),
            httpx.Response(200, json=load_fixture("search_page_2")),
        )
        async with _client(handler) as client:
            first = await client.get("/stac/search", params={"collections": DATASET_ID, "limit": 2})
            next_link = next(link for link in first.json()["links"] if link["rel"] == "next")
            second = await client.get(next_link["href"])
        assert second.status_code == 200
        assert len(seen) == 2
        assert body_of(seen[1])["next"] == "2024-06-02T10:00:00.000000Z,SYNTH_T00AAA_20240602T100000_L2A,sentinel-2-c1-l2a"

    async def test_item_collection_of_the_federated_collection(self, require_catalog_loaded: None) -> None:
        handler, seen = _answering(httpx.Response(200, json=load_fixture("search_page_1")))
        async with _client(handler) as client:
            response = await client.get(f"/stac/collections/{DATASET_ID}/items")
        assert response.status_code == 200
        body = response.json()
        assert len(body["features"]) == 2  # a page of the fixture's 3 matched items
        assert body["numberMatched"] == 3
        assert seen[0].headers["host"] == HOST

    async def test_numbermatched_is_left_out_when_the_source_has_no_count(self, require_catalog_loaded: None) -> None:
        """adr/0007 §12.6: EOPF never sends one. Left out, not guessed from the page
        size — `numberMatched` must not look like a checked total that happens to
        equal how many items came back."""
        handler, _ = _answering(httpx.Response(200, json=load_fixture("search_no_count")))
        async with _client(handler) as client:
            response = await client.get(f"/stac/collections/{DATASET_ID}/items")
        assert response.status_code == 200
        assert "numberMatched" not in response.json()

    async def test_each_item_carries_its_own_links_not_the_sources(self, require_catalog_loaded: None) -> None:
        """The source's own self/parent/root/collection links must not survive
        inside a search or item_collection answer — the same rewrite `get_item`
        already does for a single item (M2-09b, found against the real EOPF
        source; the gap is the same for Earth Search, its synthetic search
        fixtures just never carried per-item links before)."""
        handler, _ = _answering(httpx.Response(200, json=load_fixture("search_no_count")))
        async with _client(handler) as client:
            response = await client.get(f"/stac/collections/{DATASET_ID}/items")
        feature = response.json()["features"][0]
        by_rel = {link["rel"]: link["href"] for link in feature["links"]}
        for rel in ("self", "parent", "root", "collection"):
            assert rel in by_rel
            assert "earth-search.invalid" not in by_rel[rel]
            assert by_rel[rel].startswith("http://test/")

    async def test_get_item_of_the_federated_collection(self, require_catalog_loaded: None) -> None:
        handler, seen = _answering(httpx.Response(200, json=load_fixture("item")))
        async with _client(handler) as client:
            response = await client.get(f"/stac/collections/{DATASET_ID}/items/{load_fixture('item')['id']}")
        assert response.status_code == 200
        assert response.json()["id"] == load_fixture("item")["id"]
        assert seen[0].headers["host"] == HOST

    async def test_get_item_missing_upstream_stays_404(self, require_catalog_loaded: None) -> None:
        handler, _ = _answering(httpx.Response(404, json={"description": "Not Found"}))
        async with _client(handler) as client:
            response = await client.get(f"/stac/collections/{DATASET_ID}/items/does-not-exist")
        assert response.status_code == 404

    async def test_upstream_trouble_answers_with_its_own_status_not_a_crash(
        self, require_catalog_loaded: None
    ) -> None:
        handler, _ = _answering(httpx.Response(503, json={"description": "upstream says no"}))
        async with _client(handler) as client:
            response = await client.get("/stac/search", params={"collections": DATASET_ID})
        assert response.status_code == 503

    async def test_get_item_answering_something_that_is_not_an_item_is_502_not_a_crash(
        self, require_catalog_loaded: None
    ) -> None:
        """M2-17 finding: `get_item` did not catch `UpstreamShapeError`, so this
        turned into our own `500` instead of the `502` the error mapping already
        has for it — the same case `post_search`/`get_search` were already
        covered for (`search answer is not a JSON object`)."""
        handler, _ = _answering(httpx.Response(200, json=["not", "an", "item"]))
        async with _client(handler) as client:
            response = await client.get(f"/stac/collections/{DATASET_ID}/items/does-not-exist")
        assert response.status_code == 502


class TestNoCoordinatesReachAnyLog:
    """M3-08 follow-up (Otto, 24.09.2026): does `intersects`/`bbox` ever reach a
    log written by `gateway` or an adapter — the request URL, an upstream error's
    text, or a retry? Each test carries its own distinctive, otherwise-unused
    longitude and searches every captured log record (message and `extra`
    fields alike, via the same `JsonFormatter` production logging renders with)
    for it. `caplog` needs no `configure_logging()` call to capture what a
    logger emits — it attaches its own handler at the root."""

    def _assert_marker_absent(self, caplog: pytest.LogCaptureFixture, marker: str) -> None:
        assert caplog.records, "the test would prove nothing if nothing was logged"
        formatter = JsonFormatter()
        for record in caplog.records:
            assert marker not in record.getMessage()
            assert marker not in formatter.format(record)  # extras (gateway_path, etc.) too

    async def test_a_successful_search_with_intersects_logs_no_coordinate(
        self, require_catalog_loaded: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        marker = "13.918273"  # a value distinctive enough it appears nowhere else
        polygon = {
            "type": "Polygon",
            "coordinates": [[[float(marker), 47.0], [12.0, 47.0], [float(marker), 51.0], [float(marker), 47.0]]],
        }
        handler, seen = _answering(httpx.Response(200, json=load_fixture("search_page_1")))
        with caplog.at_level(logging.DEBUG):
            async with _client(handler) as client:
                response = await client.post(
                    "/stac/search", json={"collections": [DATASET_ID], "intersects": polygon}
                )
        assert response.status_code == 200
        assert body_of(seen[0])["intersects"] == polygon  # the request really carried it
        self._assert_marker_absent(caplog, marker)

    async def test_a_retried_search_logs_no_coordinate(
        self, require_catalog_loaded: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Two gateway log lines this time (one per attempt) — both checked."""
        marker = "13.918274"
        polygon = {
            "type": "Polygon",
            "coordinates": [[[float(marker), 47.0], [12.0, 47.0], [float(marker), 51.0], [float(marker), 47.0]]],
        }
        handler, seen = _answering(
            httpx.Response(503, json={"description": "upstream says no"}),
            httpx.Response(200, json=load_fixture("search_page_1")),
        )
        with caplog.at_level(logging.DEBUG):
            async with _client(handler) as client:
                response = await client.post(
                    "/stac/search", json={"collections": [DATASET_ID], "intersects": polygon}
                )
        assert response.status_code == 200
        assert len(seen) == 2  # the retry actually happened
        self._assert_marker_absent(caplog, marker)

    async def test_an_upstream_rejection_that_echoes_the_coordinate_still_logs_none_of_it(
        self, require_catalog_loaded: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Worst case: the *source* quotes the coordinate in its own error body
        (measured for real, adr/0005 §3.5 and the M3-08 plan step §2.2 — Earth
        Search's `invalid latitude 95.0` for a bad point). `_adapter_error_to_http`
        already keeps that text out of our own response (adr/0005 rule III); this
        proves it never reaches a log line either."""
        marker = "13.918275"
        polygon = {"type": "Point", "coordinates": [float(marker), 49.0]}
        handler, seen = _answering(
            httpx.Response(400, json={"description": f"invalid latitude near {marker}"})
        )
        with caplog.at_level(logging.DEBUG):
            async with _client(handler) as client:
                response = await client.post(
                    "/stac/search", json={"collections": [DATASET_ID], "intersects": polygon}
                )
        assert response.status_code == 400
        assert marker not in response.text  # the source's own body did not reach the client either
        assert len(seen) == 1
        self._assert_marker_absent(caplog, marker)


class TestSearchCacheAndPageTokenCarryNoGeometry:
    """M3-08 follow-up (Otto, 24.09.2026): the plan (§4, Schritt 1) promised the
    search cache and page token carry only the fingerprint hash, never the
    geometry itself, in cleartext. `adapters.federated_search.search_fingerprint`
    already only ever *hashes* `intersects`/`ids` in memory (`_check_geometry`
    hands `SearchParams` the geometry, `search_fingerprint` folds it into a
    SHA-256 digest before anything is written or returned) — proved here against
    the real cache table and a real response body, not just read from the source."""

    async def test_the_cache_row_carries_no_search_geometry(self, require_catalog_loaded: None) -> None:
        marker = 13.918276
        polygon = {"type": "Polygon", "coordinates": [[[marker, 47.0], [12.0, 47.0], [marker, 51.0], [marker, 47.0]]]}
        handler, _ = _answering(httpx.Response(200, json=load_fixture("search_page_1")))
        async with _client(handler) as client:
            response = await client.post(
                "/stac/search", json={"collections": [DATASET_ID], "intersects": polygon}
            )
        assert response.status_code == 200

        with psycopg.connect(autocommit=True) as conn, conn.cursor() as cur:
            cur.execute("SELECT cache_key, payload::text FROM public.earthx_search_cache")
            rows = cur.fetchall()
        assert rows, "the search should have written a cache row"
        for cache_key, payload_text in rows:
            assert str(marker) not in cache_key
            assert str(marker) not in payload_text
            # The row is keyed and addressed only by hash — never the geometry
            # that produced it, in the key or in what got stored under it.

    async def test_the_page_token_itself_carries_no_search_geometry(self, require_catalog_loaded: None) -> None:
        """The page *token* (not the whole next link — a `POST` link's `body` is
        the caller's own request echoed back, geometry and all, so it can be
        repeated; that is not a leak, the caller already has it) embeds only the
        fingerprint (a hash) and the upstream's own keyset marker (datetime, id,
        collection) — never the geometry that was asked with, base64 and all
        (`federated_search.encode_page_token`/`decode_page_token`)."""
        marker = 13.918277
        polygon = {"type": "Polygon", "coordinates": [[[marker, 47.0], [12.0, 47.0], [marker, 51.0], [marker, 47.0]]]}
        handler, _ = _answering(httpx.Response(200, json=load_fixture("search_page_1")))
        async with _client(handler) as client:
            response = await client.post(
                "/stac/search", json={"collections": [DATASET_ID], "intersects": polygon, "limit": 2}
            )
        next_link = next(link for link in response.json()["links"] if link["rel"] == "next")
        token = next_link["body"]["token"]
        assert token.startswith("next:")
        opaque_marker = token[len("next:") :]
        assert str(marker) not in opaque_marker
        # decode_page_token reads back exactly {v, d, h, m} — asserted structurally,
        # not just "no substring", so a future field added to the token would have
        # to be deliberate, not an accidental extra key.
        import base64

        padded = opaque_marker + "=" * (-len(opaque_marker) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        assert set(payload.keys()) == {"v", "d", "h", "m"}
        assert str(marker) not in json.dumps(payload)

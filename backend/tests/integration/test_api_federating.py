"""T-C: the outward STAC API, against real pgstac with Earth Search mocked.

Real Postgres/pgstac (the collection and everything ``FederatingCoreCrudClient``
reads off it), a mocked Earth Search transport (adr/0002: no live network in a PR
run) — the same split M1-06's own tests use, one layer up. ``earthx.catalog.load``
is called directly rather than assumed already run: it is idempotent (M1-04's own
abnahme), so calling it here does not disturb whatever a session already loaded.
"""

from __future__ import annotations

import json
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

    async def test_an_ids_parameter_is_rejected_not_silently_dropped(self, require_catalog_loaded: None) -> None:
        """M2-17: before this check, `ids=["does-not-exist"]` answered `200` with an
        ordinary, unfiltered page — nothing was ever sent upstream to filter by."""
        handler, seen = _answering(httpx.Response(200, json=load_fixture("search_page_1")))
        async with _client(handler) as client:
            get_response = await client.get(
                "/stac/search", params={"collections": DATASET_ID, "ids": "does-not-exist"}
            )
            post_response = await client.post(
                "/stac/search", json={"collections": [DATASET_ID], "ids": ["does-not-exist"]}
            )
        assert get_response.status_code == 400
        assert post_response.status_code == 400
        assert seen == []

    async def test_an_intersects_parameter_is_rejected_not_silently_dropped(
        self, require_catalog_loaded: None
    ) -> None:
        handler, seen = _answering(httpx.Response(200, json=load_fixture("search_page_1")))
        polygon = {"type": "Polygon", "coordinates": [[[1, 1], [2, 1], [2, 2], [1, 2], [1, 1]]]}
        async with _client(handler) as client:
            get_response = await client.get(
                "/stac/search",
                params={"collections": DATASET_ID, "intersects": json.dumps(polygon)},
            )
            post_response = await client.post(
                "/stac/search", json={"collections": [DATASET_ID], "intersects": polygon}
            )
        assert get_response.status_code == 400
        assert post_response.status_code == 400
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

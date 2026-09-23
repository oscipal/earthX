"""No endpoint of the tiler takes an address, and every wrong request has an answer.

The acceptance criteria of M2-04, in the order the task names them:

* no endpoint accepts a free URL — checked twice, at the OpenAPI schema (there is
  no such parameter to send) and by sending one anyway;
* an asset host the registry does not name is refused (adr/0006 §3.3);
* a wrong ``z/x/y``, an unknown item and an unknown asset each have a defined
  answer rather than a traceback.

The item comes from the hand-written fixture, the app is built without a database
and the network guard of ``tests/conftest.py`` is active throughout: nothing here
reaches Earth Search or an asset bucket.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from rasterio.errors import RasterioIOError
from rio_tiler.errors import InvalidBandName, TileOutsideBounds

from earthx.adapters.earth_search import UnknownCollection
from earthx.api.dependencies import policy_from_registry
from earthx.api.tiler import DOWNLOAD_ROUTE, ROUTER_PREFIX, build_app
from earthx.catalog.datasets import REGISTRY, SENTINEL_2_L2A
from earthx.catalog.registry import DatasetRegistry, ViewerInfo
from earthx.gateway import (
    CachingResolver,
    UpstreamError,
    UpstreamTimeout,
    UpstreamUnreachable,
    UrlRejected,
    check_url,
)
from earthx.gateway.policy import inspect_url

FIXTURE = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "earth_search" / "item_asset_hosts.json"
DATASET = SENTINEL_2_L2A.dataset_id
ITEM = "SYNTH_T00AAA_20260724T100000_L2A"
BASE = f"/collections/{DATASET}/items/{ITEM}"


@pytest.fixture(scope="module")
def item() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def opened() -> list[str]:
    """Every path the render path actually opened, in order."""
    return []


@pytest.fixture
def fetched() -> list[str]:
    """Every item the route asked the source for, in order."""
    return []


@pytest.fixture
def client(
    item: dict[str, Any], opened: list[str], fetched: list[str], monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    """The real app, with the item source answering from the fixture.

    Two things stand in for the outside world, and nothing else does: the name is
    resolved from memory (the guard in ``tests/conftest.py`` refuses a real lookup,
    and rightly so), and the read of the asset records its path instead of fetching
    it. The checks in between — catalogue, allowlist, path building — are the real
    ones, which is the point of testing at this level at all.

    ``TestClient`` is deliberately *not* used as a context manager: entering it would
    run the lifespan, which opens a database pool and a gateway. Everything these
    tests check happens before either is needed.
    """
    monkeypatch.setattr(
        "earthx.readers.cog.check_url",
        # `**_` swallows the resolver `asset_path` hands on (M2-14): these tests
        # answer from memory whatever the caller would have resolved with.
        lambda url, policy, **_: check_url(url, policy, resolve=lambda host, port: ("93.184.216.34",)),
    )

    def fake_read(reader, src_path, **kwargs) -> dict[str, Any]:
        opened.append(str(src_path))
        return {}

    monkeypatch.setattr("earthx.access.tiles._read_statistics", fake_read)

    async def item_source(dataset_id: str, item_id: str) -> dict[str, Any]:
        fetched.append(item_id)
        if dataset_id not in REGISTRY:
            raise UnknownCollection(dataset_id)
        if item_id != ITEM:
            # What the adapter raises for an item the source does not have: the
            # gateway carries the upstream status code through unchanged.
            raise UpstreamError(404, "not found")
        return item

    app = build_app()
    app.state.earthx_item_source = item_source
    app.state.earthx_cache_pool = None
    return TestClient(app)


class TestNoFreeAddress:
    """K1 of adr/0006: the tiler renders what the catalogue names, and nothing else."""

    def test_no_endpoint_declares_a_url_parameter(self, client: TestClient) -> None:
        """Measured the way adr/0006 §10.1 measured it, now against our own app."""
        schema = client.app.openapi()
        parameters = {
            (parameter["in"], parameter["name"])
            for operations in schema["paths"].values()
            for operation in operations.values()
            if isinstance(operation, dict)
            for parameter in operation.get("parameters", [])
        }
        assert ("query", "url") not in parameters
        assert not [name for where, name in parameters if where == "query" and "url" in name.lower()]

    def test_every_path_names_a_dataset_and_an_item(self, client: TestClient) -> None:
        """There is no route that could render without going through the catalogue.

        The download route (M2-06) is the one exception to ``ROUTER_PREFIX``: it
        names only the dataset in its path because the item(s) travel in the body
        (a mosaic can list several), not because it skips the catalogue — every
        item it touches still resolves through ``earthx_item_source`` like any
        other route here.
        """
        rendering = [
            path for path in client.app.openapi()["paths"] if path not in ("/health", DOWNLOAD_ROUTE)
        ]
        assert rendering
        assert all(path.startswith(ROUTER_PREFIX) for path in rendering)

    @pytest.mark.parametrize(
        "query",
        [
            {"asset": "visual", "url": "https://attacker.example.invalid/x.tif"},
            {"asset": "visual", "src_path": "/vsicurl/https://attacker.example.invalid/x.tif"},
            {"asset": "visual", "path": "https://attacker.example.invalid/x.tif"},
        ],
    )
    def test_an_address_smuggled_into_the_query_is_not_read(
        self, client: TestClient, item: dict[str, Any], opened: list[str], query: dict[str, str]
    ) -> None:
        """The parameter does not exist, so FastAPI drops it — and what is opened is
        still the address the catalogue gave, not the one that was sent."""
        response = client.get(f"{BASE}/statistics", params=query)

        assert response.status_code == 200
        assert opened == [f"/vsicurl/{item['assets']['visual']['href']}"]

    @pytest.mark.parametrize("asset", ["https://attacker.example.invalid/x.tif", "../../../etc/passwd"])
    def test_an_address_in_place_of_an_asset_key_is_simply_not_an_asset(
        self, client: TestClient, opened: list[str], asset: str
    ) -> None:
        response = client.get(f"{BASE}/statistics", params={"asset": asset})

        assert response.status_code == 404
        assert "asset" in response.json()["detail"]
        assert opened == []

    def test_an_asset_on_a_host_the_registry_does_not_name_is_refused(
        self, client: TestClient, opened: list[str]
    ) -> None:
        """adr/0006 §3.7: `sentinel-cogs…` answers, and is still not this dataset's host."""
        response = client.get(f"{BASE}/statistics", params={"asset": "elsewhere"})

        assert response.status_code == 502
        assert "asset_hosts" in response.json()["detail"]
        assert opened == []


class TestDefinedErrors:
    def test_an_unknown_dataset_is_a_404(self, client: TestClient) -> None:
        response = client.get(
            f"/collections/no-such-dataset/items/{ITEM}/statistics", params={"asset": "visual"}
        )
        assert response.status_code == 404

    def test_an_unknown_item_is_a_404(self, client: TestClient) -> None:
        response = client.get(
            f"/collections/{DATASET}/items/SYNTH_T00AAA_19000101T000000_L2A/statistics",
            params={"asset": "visual"},
        )
        assert response.status_code == 404

    def test_an_unknown_asset_is_a_404_that_says_so(self, client: TestClient) -> None:
        response = client.get(f"{BASE}/statistics", params={"asset": "no-such-band"})
        assert response.status_code == 404
        assert "no-such-band" in response.json()["detail"]

    @pytest.mark.parametrize(
        ("error", "status"),
        [
            (UpstreamError(500, "boom"), 502),
            (UpstreamUnreachable("earth-search could not be reached"), 502),
            (UpstreamTimeout("earth-search did not answer in time"), 504),
        ],
    )
    def test_a_source_that_does_not_deliver_the_item_is_not_our_mistake(
        self, item: dict[str, Any], monkeypatch: pytest.MonkeyPatch, error: Exception, status: int
    ) -> None:
        """A 500 would say the tiler is broken when it is the source that is."""

        async def failing(dataset_id: str, item_id: str) -> dict[str, Any]:
            raise error

        app = build_app()
        app.state.earthx_item_source = failing
        app.state.earthx_cache_pool = None
        response = TestClient(app).get(f"{BASE}/statistics", params={"asset": "visual"})

        assert response.status_code == status

    def test_the_asset_is_required(self, client: TestClient) -> None:
        """A tile URL says what it shows; a default would make it say nothing (Z4)."""
        assert client.get(f"{BASE}/statistics").status_code == 422

    @pytest.mark.parametrize(
        "tile",
        [
            "WebMercatorQuad/10/x/2.png",  # not a number
            "NoSuchGrid/10/1/2.png",  # no such tile matrix set
            "WebMercatorQuad/10/1/2.jpeg2000",  # no such image format
        ],
    )
    def test_a_wrong_tile_address_is_refused_before_anything_is_opened(
        self, client: TestClient, opened: list[str], tile: str
    ) -> None:
        response = client.get(f"{BASE}/tiles/{tile}", params={"asset": "visual"})

        assert response.status_code == 422, response.text
        assert opened == []

    @pytest.mark.parametrize(
        ("error", "status"),
        [
            (TileOutsideBounds("tile 0/0/0 is outside"), 404),
            (InvalidBandName("no band b9"), 400),
            (RasterioIOError("the object is gone"), 502),
        ],
    )
    def test_what_the_read_can_raise_has_a_status_of_its_own(
        self, client: TestClient, error: Exception, status: int
    ) -> None:
        """A tile outside the scene, a band that is not there, an asset that vanished:
        each is a normal answer, not a traceback. Raised here rather than provoked,
        because provoking them needs the source (adr/0002 §2)."""

        @client.app.get("/raises")
        def raises() -> None:
            raise error

        assert client.get("/raises").status_code == status


class TestTheAllowlist:
    """The registry decides which hosts the tiler may read from (D12)."""

    def test_the_asset_host_of_the_registry_is_on_the_allowlist(self) -> None:
        policy = policy_from_registry(REGISTRY)
        assert policy.allows_host("e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com")
        assert policy.allows_host("earth-search.aws.element84.com")

    def test_the_bucket_of_the_older_collection_is_not(self) -> None:
        assert not policy_from_registry(REGISTRY).allows_host("sentinel-cogs.s3.us-west-2.amazonaws.com")

    def test_every_asset_of_the_fixture_passes_the_policy_except_the_foreign_one(
        self, item: dict[str, Any]
    ) -> None:
        """Without this the read path would stand still while the search kept working
        — the failure adr/0006 §3.3 measured and D12 fixes."""
        policy = policy_from_registry(REGISTRY)
        for key, asset in item["assets"].items():
            if key == "elsewhere":
                with pytest.raises(UrlRejected):
                    inspect_url(asset["href"], policy)
            else:
                assert inspect_url(asset["href"], policy).url == asset["href"]


class TestTheAssetHostIsResolvedOnce:
    """M2-14: a batch of tiles resolves the asset host once, not once per tile.

    Unlike the fixture above these tests leave ``check_url`` alone and put a
    counting resolver in the process's own slot, because what is under test is
    exactly the argument the path dependency hands on.
    """

    @pytest.fixture
    def counting(self, item: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, list[str]]:
        resolved: list[str] = []

        def resolve(host: str, port: int) -> tuple[str, ...]:
            resolved.append(host)
            return ("93.184.216.34",)

        def fake_read(reader, src_path, **kwargs) -> dict[str, Any]:
            return {}

        monkeypatch.setattr("earthx.access.tiles._read_statistics", fake_read)

        async def item_source(dataset_id: str, item_id: str) -> dict[str, Any]:
            return item

        app = build_app()
        app.state.earthx_item_source = item_source
        app.state.earthx_cache_pool = None
        app.state.earthx_resolver = CachingResolver(resolve=resolve)
        return TestClient(app), resolved

    def test_twenty_requests_for_one_item_resolve_the_host_once(
        self, counting: tuple[TestClient, list[str]]
    ) -> None:
        client, resolved = counting
        for _ in range(20):
            assert client.get(f"{BASE}/statistics", params={"asset": "visual"}).status_code == 200
        assert len(resolved) == 1

    def test_the_process_carries_a_resolver_of_its_own(self) -> None:
        """The app builds one; nothing has to remember to pass it in."""
        assert isinstance(build_app().state.earthx_resolver, CachingResolver)


def test_health_still_answers_the_way_compose_asks_it_to(client: TestClient) -> None:
    """docker-compose's healthcheck is unchanged; only the entrypoint moved."""
    assert client.get("/health").json() == {"status": "ok", "service": "tiler"}


class TestOnlyReleasedZoomLevels:
    """M2-10, Otto's first addition to F1: the tile path enforces the zoom range of
    ``earthx:viewer`` itself.

    The registry field alone only tells the viewer which levels to ask for. Another
    client can ask for z20 regardless, and for a Zarr dataset that is a read off the
    native 10 m level — far more bytes for pixels no sharper than z14 already gives.
    The range therefore has to hold at the route, and a refusal has to be cheap:
    nothing is fetched from the source for a level nobody serves.
    """

    @pytest.fixture
    def narrow_client(
        self, item: dict[str, Any], fetched: list[str], client: TestClient
    ) -> TestClient:
        """The same app against an entry released for z8..z14 only — the second
        dataset's range (D23), without needing its store."""
        return self._client_for(
            replace(SENTINEL_2_L2A.viewer, min_zoom=8, max_zoom=14), client, fetched
        )

    @staticmethod
    def _client_for(viewer: ViewerInfo | None, client: TestClient, fetched: list[str]) -> TestClient:
        registry = DatasetRegistry((replace(SENTINEL_2_L2A, viewer=viewer),))
        app = build_app(registry)
        app.state.earthx_item_source = client.app.state.earthx_item_source
        app.state.earthx_cache_pool = None
        return TestClient(app)

    @pytest.mark.parametrize("zoom", [7, 15, 20])
    def test_a_level_outside_the_range_is_refused(
        self, narrow_client: TestClient, fetched: list[str], zoom: int
    ) -> None:
        response = narrow_client.get(
            f"{BASE}/tiles/WebMercatorQuad/{zoom}/1/1", params={"asset": "visual"}
        )

        assert response.status_code == 400, response.text
        assert "z8 to z14" in response.json()["detail"]

    def test_the_refusal_costs_no_request_to_the_source(
        self, narrow_client: TestClient, fetched: list[str], opened: list[str]
    ) -> None:
        """Checked before the item is fetched — otherwise a client could still make
        us pay for a level we do not serve, just not in pixels."""
        narrow_client.get(f"{BASE}/tiles/WebMercatorQuad/20/1/1", params={"asset": "visual"})

        assert fetched == []
        assert opened == []

    @pytest.mark.parametrize("zoom", [8, 14])
    def test_the_boundaries_themselves_are_released(
        self, narrow_client: TestClient, fetched: list[str], zoom: int
    ) -> None:
        """An inclusive range: z8 and z14 are the levels adr/0007 §12.10 released,
        not the first two it refuses."""
        narrow_client.get(f"{BASE}/tiles/WebMercatorQuad/{zoom}/1/1", params={"asset": "visual"})

        assert fetched == [ITEM]

    def test_the_first_dataset_keeps_the_levels_it_always_had(
        self, client: TestClient, fetched: list[str]
    ) -> None:
        """Otto's second addition to F2: writing `0..19` into the entry must not
        change what the viewer could already ask for."""
        client.get(f"{BASE}/tiles/WebMercatorQuad/19/1/1", params={"asset": "visual"})
        assert fetched == [ITEM]

        response = client.get(f"{BASE}/tiles/WebMercatorQuad/20/1/1", params={"asset": "visual"})
        assert response.status_code == 400

    def test_statistics_carries_no_level_and_is_untouched(
        self, narrow_client: TestClient, fetched: list[str]
    ) -> None:
        """Statistics are answered on the coarsest level there is (adr/0007 §12.11
        point 8) — no zoom is named, so this check has nothing to say about them."""
        response = narrow_client.get(f"{BASE}/statistics", params={"asset": "visual"})

        # Past the check and into the read, which has no source to read from here.
        assert response.status_code != 400, response.text
        assert fetched == [ITEM]

    def test_there_is_no_preview_route_to_slip_past_the_check(
        self, narrow_client: TestClient, fetched: list[str]
    ) -> None:
        """`/preview` carried no level *and* computed no target resolution, so for a
        Zarr dataset it read the native one — the read the released range exists to
        prevent. It is not registered any more (`access.tiles`), and nothing asks
        for it (M2-10 review, finding 3)."""
        assert narrow_client.get(f"{BASE}/preview", params={"asset": "visual"}).status_code == 404
        assert fetched == []

    def test_only_one_tile_matrix_set_is_served(
        self, narrow_client: TestClient, opened: list[str]
    ) -> None:
        """The released range is a range of WebMercatorQuad levels (adr/0007 §12.10).
        A second grid would let the same number mean two resolutions — z14 in
        WorldCRS84Quad is about one WebMercator level finer — and walk straight
        through this check (M2-10 review, finding 2).

        Refused by the route's own parameter type, which is why this is a 422 and
        not the 400 above, and why it is `opened` rather than `fetched` that stays
        empty: FastAPI resolves the path dependency alongside validating the path
        parameters, the same as for any other malformed tile address here.
        """
        response = narrow_client.get(
            f"{BASE}/tiles/WorldCRS84Quad/14/1/1", params={"asset": "visual"}
        )

        assert response.status_code == 422, response.text
        assert opened == []

    def test_a_dataset_that_names_no_range_serves_no_tiles(
        self, client: TestClient, fetched: list[str], opened: list[str]
    ) -> None:
        """Not a caller's mistake but an entry that was never set up for tiling, so
        501 like a format without a reader — and never a guessed range (B10)."""
        blind = self._client_for(None, client, fetched)

        response = blind.get(f"{BASE}/tiles/WebMercatorQuad/10/1/1", params={"asset": "visual"})

        assert response.status_code == 501, response.text
        assert fetched == []
        assert opened == []

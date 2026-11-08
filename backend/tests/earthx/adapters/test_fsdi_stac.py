"""M5-08b: the FSDI dialect, fixed asset keys and the materialization over a STAC API (plan §4.1–§4.4, §4.7).

The source is synthetic: a mock transport answers the collection and the search pages the way the FSDI was measured
to (plan §2: `cursor` in a `merge: true` link, no count, asset keys after the file). No item, href or tile is real.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import httpx
import pytest

from earthx.adapters import (
    ADAPTER_SPECS,
    AdapterSpecMismatch,
    NotMaterialized,
    SearchParams,
    UnsupportedFilter,
    UpstreamShapeError,
    check_adapter_specs,
    materialize_items,
    stac_api,
)
from earthx.adapters import search_items as dispatch_search
from earthx.adapters.errors import ItemOffAssetKeys
from earthx.adapters.stac_api import (
    BODY_FIELDS,
    FSDI,
    STATE_PROPERTY,
    TILE_PROPERTY,
    dialect_of,
    get_item,
    search_items,
    with_fixed_asset_keys,
)
from earthx.catalog.registry import (
    AdapterKind,
    AssetKeyRule,
    CoverageProvider,
    DatasetRegistry,
    ItemHolding,
    ItemStateRule,
    ItemStates,
)
from earthx.catalog.search_filters import RangeCondition
from earthx.gateway import Policy, UpstreamError
from earthx.gateway.client import Gateway
from tests.catalog.entries import COP_DEM_GLO_30
from tests.earthx.adapters.test_cache_use import FakeCache

pytestmark = pytest.mark.anyio

HOST = "stac.example.invalid"
ENDPOINT = f"https://{HOST}/api/stac/v1"
COLLECTION = "ch.example.dtm"
ETAG = '"synthetic-collection-1"'
UPDATED = "2026-01-01T00:00:00Z"
COG = "image/tiff; application=geotiff; profile=cloud-optimized"
ZIP = "application/x.ascii-xyz+zip"
RULES = (
    AssetKeyRule("dtm", COG, 0.5),
    AssetKeyRule("dtm_2m", COG, 2.0),
    AssetKeyRule("xyz", ZIP, 0.5),
    AssetKeyRule("xyz_2m", ZIP, 2.0),
)
STATES = ItemStates(rule=ItemStateRule.LATEST, tile_pattern=r"dtm_\d{4}_(?P<tile>\d{4}-\d{4})")

ENTRY = replace(
    COP_DEM_GLO_30,
    dataset_id="earthx-test-fsdi",
    source=replace(
        COP_DEM_GLO_30.source,
        adapter=AdapterKind.FSDI_STAC_V1,
        endpoint=ENDPOINT,
        source_collection_id=COLLECTION,
        asset_hosts=(HOST,),
        asset_keys=RULES,
        item_states=STATES,
    ),
    default_render=replace(COP_DEM_GLO_30.default_render, assets=("dtm",)),
    band_units={"dtm": "m", "dtm_2m": "m"},
    auxiliary_assets=("xyz", "xyz_2m"),
)
# The same source searched live: no states (those are the materialization's). Not an entry the start check would take
# (the FSDI aggregates nothing), but what a direct call of the search gets.
FEDERATED = replace(
    ENTRY,
    dataset_id="earthx-test-fsdi-federated",
    source=replace(ENTRY.source, item_holding=ItemHolding.FEDERATED, item_states=None),
    coverage=replace(ENTRY.coverage, provider=CoverageProvider.UPSTREAM_AGGREGATION),
    capabilities=replace(ENTRY.capabilities, single_coverage_product=False),
)


def _public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


def gateway_for(handler) -> Gateway:
    async def sleep(seconds: float) -> None:
        return None

    return Gateway(Policy(allowed_hosts=frozenset({HOST})), transport=httpx.MockTransport(handler), resolve=_public, sleep=sleep)


def answering(status: int, payload: Any) -> Gateway:
    return gateway_for(lambda request: httpx.Response(status, json=payload))


def item(year: int, tile: str = "2600-1200", *, shift: float = 0.0, **changes: Any) -> dict[str, Any]:
    """One synthetic item in the shape measured at the FSDI: four assets keyed by their file name."""
    item_id = f"dtm_{year}_{tile}"
    west, south = 7.0 + shift, 46.0
    ring = [[west, south], [west + 0.01, south], [west + 0.01, south + 0.01], [west, south + 0.01], [west, south]]
    assets = {
        f"{item_id}_{gsd}_2056.{ext}": {
            "href": f"https://{HOST}/{COLLECTION}/{item_id}/{item_id}_{gsd}_2056.{ext}",
            "type": media_type,
            "gsd": gsd,
            "proj:epsg": 2056,
            "file:checksum": "1220" + "00" * 32,
        }
        for media_type, ext in ((COG, "tif"), (ZIP, "xyz.zip"))
        for gsd in (0.5, 2.0)
    }
    feature = {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": item_id,
        "collection": COLLECTION,
        "bbox": [west, south, west + 0.01, south + 0.01],
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": {"datetime": f"{year}-01-01T00:00:00Z", "created": UPDATED, "updated": UPDATED},
        "assets": assets,
        "links": [{"rel": "self", "href": f"{ENDPOINT}/collections/{COLLECTION}/items/{item_id}"}],
    }
    feature.update(changes)
    return feature


def page(features: list[Any], cursor: str | None) -> dict[str, Any]:
    links = [{"rel": "root", "href": ENDPOINT}]
    if cursor is not None:
        links.append({"rel": "next", "href": f"{ENDPOINT}/search", "method": "POST", "merge": True, "body": {"cursor": cursor}})
    return {"type": "FeatureCollection", "features": features, "links": links}


class Source:
    """The collection and a search over ``pages``; page ``n`` is asked for with the cursor ``p<n>``."""

    def __init__(
        self, pages: list[list[Any]], *, etag: str | None = ETAG, collection: Any = None, honours_etag: bool = True
    ) -> None:
        self.pages = pages
        self.etag = etag
        self.honours_etag = honours_etag
        self.collection = collection if collection is not None else {"id": COLLECTION, "updated": UPDATED}
        self.seen: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        if request.method == "GET" and "/items/" in request.url.path:
            wanted = request.url.path.rsplit("/", 1)[-1]
            found = [one for features in self.pages for one in features if one["id"] == wanted]
            return httpx.Response(200, json=found[0]) if found else httpx.Response(404, json={"description": "Not Found"})
        if request.method == "GET":
            if self.honours_etag and self.etag is not None and request.headers.get("if-none-match") == self.etag:
                return httpx.Response(304)
            return httpx.Response(200, json=self.collection, headers={"etag": self.etag} if self.etag else {})
        cursor = json.loads(request.content).get("cursor")
        index = 0 if cursor is None else int(cursor[1:])
        following = f"p{index + 1}" if index + 1 < len(self.pages) else None
        return httpx.Response(200, json=page(self.pages[index], following))

    def gateway(self) -> Gateway:
        return gateway_for(lambda request: self.handler(request))

    @property
    def searches(self) -> list[dict[str, Any]]:
        return [json.loads(request.content) for request in self.seen if request.method == "POST"]


async def materialize(source: Source, *, config=ENTRY, known_version: str | None = None):
    async with source.gateway() as gateway:
        return await materialize_items(config, adapters=ADAPTER_SPECS, gateway=gateway, known_version=known_version)


class TestDialect:
    def test_the_fsdi_entry_finds_its_dialect(self) -> None:
        assert dialect_of(ENTRY) is FSDI

    def test_the_spec_searches_fetches_and_materializes(self) -> None:
        spec = ADAPTER_SPECS[AdapterKind.FSDI_STAC_V1]
        assert spec.search is stac_api.search_items and spec.materialize is stac_api.materialize_items
        assert spec.filters is FSDI.filters and not spec.filters.query and not spec.filters.cql2

    def test_a_materialized_fsdi_entry_passes_the_start_check(self) -> None:
        check_adapter_specs(DatasetRegistry((ENTRY,)), ADAPTER_SPECS)

    @pytest.mark.parametrize("field", ["asset_keys", "item_states"])
    def test_a_bucket_adapter_may_not_take_either_field(self, field) -> None:
        """Only a STAC dialect applies them; a bucket adapter would pass them over without a word."""
        value = {"asset_keys": RULES[:1], "item_states": STATES}[field]
        bucket = replace(
            ENTRY,
            source=replace(ENTRY.source, adapter=AdapterKind.COP_DEM_BUCKET, **{"asset_keys": (), "item_states": None, field: value}),
            default_render=replace(ENTRY.default_render, assets=("dtm",)),
            band_units={"dtm": "m"},
            auxiliary_assets=(),
        )
        with pytest.raises(AdapterSpecMismatch, match="applies no source.asset_keys"):
            check_adapter_specs(DatasetRegistry((bucket,)), ADAPTER_SPECS)


class TestSearch:
    async def test_the_marker_comes_from_cursor_and_goes_back_beside_our_body(self) -> None:
        source = Source([[item(2019)], [item(2025)]])
        async with source.gateway() as gateway:
            first = await search_items(FEDERATED, SearchParams(limit=1), gateway=gateway)
            second = await search_items(FEDERATED, SearchParams(limit=1, page_token=first.next_page_token), gateway=gateway)
        assert [one["id"] for one in second.items] == ["dtm_2025_2600-1200"]
        assert source.searches[1] == {**source.searches[0], "cursor": "p1"}

    async def test_a_next_link_without_cursor_is_a_shape_error(self) -> None:
        answer = page([item(2019)], None)
        answer["links"].append({"rel": "next", "method": "POST", "body": {"next": "x"}})
        async with answering(200, answer) as gateway:
            with pytest.raises(UpstreamShapeError, match="no marker"):
                await search_items(FEDERATED, gateway=gateway)

    async def test_an_answer_without_a_count_has_no_count(self) -> None:
        async with Source([[item(2019)]]).gateway() as gateway:
            result = await search_items(FEDERATED, gateway=gateway)
        assert result.matched is None and result.next_page_token is None

    async def test_ids_and_intersects_go_out_and_nothing_else_does(self) -> None:
        polygon = {"type": "Polygon", "coordinates": [[[7, 46], [8, 46], [8, 47], [7, 46]]]}
        source = Source([[item(2019)]])
        async with source.gateway() as gateway:
            await search_items(FEDERATED, SearchParams(ids=("dtm_2019_2600-1200",), intersects=polygon), gateway=gateway)
        body = source.searches[0]
        assert body["ids"] == ["dtm_2019_2600-1200"] and body["intersects"] == polygon
        # The FSDI answers 400 to any field it does not know (plan §2).
        assert set(body) <= BODY_FIELDS

    async def test_conditions_are_refused_before_any_request(self) -> None:
        source = Source([[item(2019)]])
        params = SearchParams(conditions={"gsd": RangeCondition(minimum=None, maximum=1.0)})
        async with source.gateway() as gateway:
            with pytest.raises(UnsupportedFilter):
                await dispatch_search(FEDERATED, params, adapters=ADAPTER_SPECS, gateway=gateway)
            with pytest.raises(UnsupportedFilter):
                await search_items(FEDERATED, params, gateway=gateway)
        assert source.seen == []

    async def test_the_items_carry_the_fixed_keys(self) -> None:
        async with Source([[item(2019)]]).gateway() as gateway:
            result = await search_items(FEDERATED, gateway=gateway)
        assert list(result.items[0]["assets"]) == ["dtm", "dtm_2m", "xyz", "xyz_2m"]

    async def test_an_item_that_does_not_fit_the_keys_is_skipped_and_counted(self, caplog) -> None:
        """Otto, 08.11.2026: the page stays, the item is left out and counted; the log names no item."""
        broken = item(2025)
        broken["assets"].popitem()
        async with Source([[item(2019), broken, item(2019, "2601-1200")]]).gateway() as gateway:
            with caplog.at_level("WARNING", logger="earthx.adapters.stac_api"):
                result = await search_items(FEDERATED, gateway=gateway)
        assert [one["id"] for one in result.items] == ["dtm_2019_2600-1200", "dtm_2019_2601-1200"]
        assert result.skipped == 1
        (record,) = caplog.records
        assert record.skipped == 1 and record.dataset_id == FEDERATED.dataset_id
        logged = json.dumps({**record.__dict__, "msg": record.getMessage()}, default=str)
        assert "dtm_2025" not in logged and HOST not in logged

    async def test_the_count_comes_back_from_the_cache(self) -> None:
        broken = item(2025)
        broken["assets"].popitem()
        cache = FakeCache()
        source = Source([[item(2019), broken]])
        async with source.gateway() as gateway:
            live = await search_items(FEDERATED, gateway=gateway, cache=cache)
            cached = await search_items(FEDERATED, gateway=gateway, cache=cache)
        assert (live.skipped, cached.skipped, cached.from_cache) == (1, 1, True)
        assert len(source.searches) == 1

    async def test_a_page_with_nothing_skipped_is_stored_as_before(self) -> None:
        """The cache value of M5-08a stays byte for byte where nothing was skipped (Earth Search, golden test)."""
        cache = FakeCache()
        async with Source([[item(2019)]]).gateway() as gateway:
            result = await search_items(FEDERATED, gateway=gateway, cache=cache)
        (stored,) = cache.entries.values()
        assert set(stored) == {"features", "matched", "marker"} and result.skipped == 0

    @pytest.mark.parametrize("value", [-1, True, "1", None, 1.5])
    async def test_a_damaged_count_in_the_cache_reads_as_none_skipped(self, value) -> None:
        cache = FakeCache()
        source = Source([[item(2019)]])
        async with source.gateway() as gateway:
            await search_items(FEDERATED, gateway=gateway, cache=cache)
            (key,) = cache.entries
            cache.entries[key] = {**cache.entries[key], "skipped": value}
            cached = await search_items(FEDERATED, gateway=gateway, cache=cache)
        assert cached.from_cache and cached.skipped == 0

    async def test_one_item_that_does_not_fit_the_keys_is_still_an_error(self) -> None:
        """A fetch by id has no page to keep: the item asked for is not one the entry can serve."""
        broken = item(2019)
        broken["assets"].popitem()
        async with Source([[broken]]).gateway() as gateway:
            with pytest.raises(ItemOffAssetKeys, match="no asset for xyz_2m"):
                await get_item(FEDERATED, "dtm_2019_2600-1200", gateway=gateway)

    async def test_one_item_gets_the_fixed_keys_too(self) -> None:
        source = Source([[item(2019)]])
        async with source.gateway() as gateway:
            fetched = await get_item(FEDERATED, "dtm_2019_2600-1200", gateway=gateway)
        assert set(fetched["assets"]) == {"dtm", "dtm_2m", "xyz", "xyz_2m"}
        assert source.seen[0].url.path == f"/api/stac/v1/collections/{COLLECTION}/items/dtm_2019_2600-1200"

    async def test_a_missing_item_stays_a_404(self) -> None:
        async with Source([[item(2019)]]).gateway() as gateway:
            with pytest.raises(UpstreamError) as error:
                await get_item(FEDERATED, "dtm_2025_2600-1200", gateway=gateway)
        assert error.value.status_code == 404


class TestFixedAssetKeys:
    def test_no_rules_leave_the_item_alone(self) -> None:
        original = item(2019)
        assert with_fixed_asset_keys(original, ()) is original

    def test_each_asset_takes_the_key_of_its_rule(self) -> None:
        keyed = with_fixed_asset_keys(item(2019), RULES)
        assert keyed["assets"]["dtm_2m"]["gsd"] == 2.0 and keyed["assets"]["xyz"]["type"] == ZIP

    @pytest.mark.parametrize(
        ("change", "message"),
        [
            (lambda assets: next(iter(assets.values())).update(gsd=1.0), "fits no rule"),
            (lambda assets: next(iter(assets.values())).update(type="image/png"), "fits no rule"),
            (lambda assets: next(iter(assets.values())).update(gsd=True), "fits no rule"),
            (lambda assets: assets.update(extra={"href": "x", "type": COG, "gsd": 0.5}), "two assets"),
            (lambda assets: assets.pop(next(iter(assets))), "no asset for dtm"),
            (lambda assets: assets.update(junk="not an asset"), "fits no rule"),
        ],
    )
    def test_an_asset_without_its_rule_makes_the_item_unusable(self, change, message) -> None:
        broken = item(2019)
        change(broken["assets"])
        with pytest.raises(UpstreamShapeError, match=message):
            with_fixed_asset_keys(broken, RULES)

    def test_an_item_without_assets_is_unusable(self) -> None:
        with pytest.raises(UpstreamShapeError, match="no assets"):
            with_fixed_asset_keys(item(2019, assets=None), RULES)


class TestMaterialize:
    async def test_every_page_is_read_and_the_latest_state_per_tile_is_loaded(self) -> None:
        source = Source(
            [
                [item(2019, "2600-1200"), item(2025, "2600-1200"), item(2019, "2601-1200")],
                [item(2024, "2601-1200", shift=0.002), item(2025, "2601-1200", shift=0.004), item(2019, "2602-1200")],
            ]
        )
        outcome = await materialize(source)
        assert outcome.status == "loaded"
        assert sorted(one["id"] for one in outcome.items) == ["dtm_2019_2602-1200", "dtm_2025_2600-1200", "dtm_2025_2601-1200"]
        assert (outcome.listed, outcome.in_bucket, outcome.missing, outcome.withheld, outcome.unknown) == (6, 6, 0, 3, 0)
        assert outcome.source_version == f"{ETAG};updated={UPDATED}"

    async def test_the_search_asks_for_the_whole_collection_by_id(self) -> None:
        source = Source([[item(2019)], [item(2025)]])
        await materialize(source)
        assert source.searches[0] == {
            "collections": [COLLECTION],
            "limit": 100,
            "sortby": [{"field": "id", "direction": "asc"}],
        }
        assert source.searches[1] == {**source.searches[0], "cursor": "p1"}

    async def test_the_items_are_ours(self) -> None:
        outcome = await materialize(Source([[item(2019), item(2025)]]))
        (loaded,) = outcome.items
        assert loaded["collection"] == ENTRY.dataset_id and loaded["links"] == []
        assert loaded["properties"][TILE_PROPERTY] == "2600-1200" and loaded["properties"][STATE_PROPERTY] == "latest"
        assert loaded["properties"]["datetime"] == "2025-01-01T00:00:00Z"
        assert list(loaded["assets"]) == ["dtm", "dtm_2m", "xyz", "xyz_2m"]

    async def test_without_states_every_item_is_loaded(self) -> None:
        config = replace(ENTRY, source=replace(ENTRY.source, item_states=None))
        outcome = await materialize(Source([[item(2019), item(2025)]]), config=config)
        assert len(outcome.items) == 2 and outcome.withheld == 0
        assert all(TILE_PROPERTY not in one["properties"] for one in outcome.items)

    async def test_a_tie_at_the_top_loads_nothing_of_the_tile(self) -> None:
        good = [item(2019, f"{2600 + n}-1200") for n in range(300)]
        older = item(2019, "2999-1200")
        first = item(2025, "2999-1200")
        second = item(2026, "2999-1200")
        second["properties"] = {**second["properties"], "datetime": first["properties"]["datetime"]}
        outcome = await materialize(Source([good + [older, first, second]]))
        assert outcome.unknown == 2 and outcome.withheld == 1
        assert not any(one["id"].endswith("2999-1200") for one in outcome.items)

    async def test_a_tie_below_the_top_still_loads_the_latest(self) -> None:
        good = [item(2019, f"{2600 + n}-1200") for n in range(300)]
        first, second, latest = item(2019, "2999-1200"), item(2020, "2999-1200"), item(2025, "2999-1200")
        second["properties"] = {**second["properties"], "datetime": first["properties"]["datetime"]}
        outcome = await materialize(Source([good + [first, second, latest]]))
        assert outcome.unknown == 2 and outcome.withheld == 0
        assert "dtm_2025_2999-1200" in {one["id"] for one in outcome.items}

    @pytest.mark.parametrize(
        "change",
        [
            {"id": "dtm_2025_elsewhere"},
            {"collection": "ch.example.other"},
            {"geometry": None},
            {"geometry": {"type": "Polygon"}},
            {"properties": {"created": UPDATED}},
            {"properties": {"datetime": "2025"}},
            {"properties": {"datetime": "2025-01-01T00:00:00"}},
            {"id": "dtm_2025_2600-1200/../x"},
        ],
        ids=["id-without-tile", "collection", "no-geometry", "no-coordinates", "no-datetime", "no-instant", "no-offset", "bad-id"],
    )
    async def test_an_item_that_does_not_fit_counts_as_unknown(self, change) -> None:
        good = [item(2019, f"{2600 + n}-1200") for n in range(200)]
        outcome = await materialize(Source([[*good, item(2025, "2900-1200", **change)]]))
        assert outcome.unknown == 1 and len(outcome.items) == 200

    @pytest.mark.parametrize(
        "href",
        ["https://elsewhere.example.invalid/a.tif", f"http://{HOST}/a.tif", f"https://{HOST}.evil.invalid/a.tif", None, "https://[::1"],
    )
    async def test_an_asset_off_the_asset_hosts_counts_as_unknown(self, href) -> None:
        good = [item(2019, f"{2600 + n}-1200") for n in range(200)]
        foreign = item(2025, "2900-1200")
        next(iter(foreign["assets"].values()))["href"] = href
        outcome = await materialize(Source([[*good, foreign]]))
        assert outcome.unknown == 1

    @pytest.mark.parametrize("assets", [None, [], "x", {}], ids=["null", "list", "text", "empty"])
    async def test_an_item_without_assets_counts_as_unknown_even_without_rules(self, assets) -> None:
        """A later FSDI collection keeps the source keys (SWISSIMAGE); its items still need assets."""
        config = replace(ENTRY, source=replace(ENTRY.source, asset_keys=()), default_render=None, band_units={}, auxiliary_assets=())
        good = [item(2019, f"{2600 + n}-1200") for n in range(200)]
        outcome = await materialize(Source([[*good, item(2025, "2900-1200", assets=assets)]]), config=config)
        assert outcome.unknown == 1

    async def test_an_item_off_the_asset_keys_counts_as_unknown(self) -> None:
        good = [item(2019, f"{2600 + n}-1200") for n in range(200)]
        odd = item(2025, "2900-1200")
        odd["assets"].popitem()
        outcome = await materialize(Source([[*good, odd, "not a feature"]]))
        assert outcome.unknown == 2 and outcome.listed == 202

    async def test_above_one_percent_unknown_the_run_aborts(self) -> None:
        good = [item(2019, f"{2600 + n}-1200") for n in range(98)]
        bad = [item(2025, f"{2700 + n}-1200", collection="ch.example.other") for n in range(2)]
        with pytest.raises(UpstreamShapeError, match="2 of 100 items"):
            await materialize(Source([good, bad]))

    async def test_an_unchanged_collection_asks_no_search(self) -> None:
        source = Source([[item(2019)]])
        outcome = await materialize(source, known_version=f"{ETAG};updated={UPDATED}")
        assert outcome.status == "unchanged" and outcome.items == ()
        assert source.seen[0].headers["if-none-match"] == ETAG and len(source.seen) == 1

    async def test_the_same_version_without_a_304_asks_no_search_either(self) -> None:
        source = Source([[item(2019)]], honours_etag=False)
        outcome = await materialize(source, known_version=f"{ETAG};updated={UPDATED}")
        assert outcome.status == "unchanged" and len(source.seen) == 1

    async def test_a_new_updated_under_the_same_etag_reloads(self) -> None:
        """Plan §7 R1: whether the ETag changes when only items are added is not measured."""
        source = Source([[item(2019)]], honours_etag=False, collection={"id": COLLECTION, "updated": "2026-02-01T00:00:00Z"})
        outcome = await materialize(source, known_version=f"{ETAG};updated={UPDATED}")
        assert outcome.status == "loaded" and outcome.source_version == f"{ETAG};updated=2026-02-01T00:00:00Z"

    @pytest.mark.parametrize(
        ("etag", "collection", "message"),
        [
            (None, {"id": COLLECTION, "updated": UPDATED}, "without an ETag"),
            (ETAG, {"id": COLLECTION}, "no updated"),
            (ETAG, {"id": "ch.example.other", "updated": UPDATED}, "not the collection"),
            (ETAG, [], "not the collection"),
        ],
    )
    async def test_a_collection_a_later_run_cannot_compare_against_is_refused(self, etag, collection, message) -> None:
        with pytest.raises(UpstreamShapeError, match=message):
            await materialize(Source([[item(2019)]], etag=etag, collection=collection))

    async def test_an_empty_collection_is_refused(self) -> None:
        """Rule I: the FSDI answers an unknown collection with an empty list (plan §2)."""
        with pytest.raises(UpstreamShapeError, match="lists no item"):
            await materialize(Source([[]]))

    async def test_the_same_marker_twice_stops_the_run(self) -> None:
        source = Source([[item(2019)], [item(2020)], [item(2021)]])
        original = source.handler

        def looping(request: httpx.Request) -> httpx.Response:
            response = original(request)
            if request.method == "POST":
                return httpx.Response(200, json=page(json.loads(response.content)["features"], "p1"))
            return response

        source.handler = looping  # type: ignore[method-assign]
        with pytest.raises(UpstreamShapeError, match="same page marker twice"):
            await materialize(source)

    async def test_an_item_twice_stops_the_run(self) -> None:
        with pytest.raises(UpstreamShapeError, match="returned an item twice"):
            await materialize(Source([[item(2019)], [item(2019)]]))

    async def test_a_federated_entry_is_not_materialized(self) -> None:
        source = Source([[item(2019)]])
        async with source.gateway() as gateway:
            with pytest.raises(NotMaterialized):
                await stac_api.materialize_items(FEDERATED, gateway=gateway, known_version=None)
        assert source.seen == []

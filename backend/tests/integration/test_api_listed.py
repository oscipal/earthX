"""T-C: listed entries on the API (M5-40 plan §5.5, §5.8; adr/0033 §9).

The running `api` app over the registry in pgstac and a handful of synthetic listed entries in ``earthx_listed_entry``.
``catalog-load`` commits, and so does the fixture that writes the listed rows; it deletes them again when the test ends,
because the next ``catalog-load`` would turn a left-over hand entry into a tombstone and the other tests count the
catalogue. Nothing goes out: neither the listed documents nor their links are fetched from anywhere.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import date

import httpx
import psycopg
import pytest

from earthx.api.federating_client import GONE_TEXT
from earthx.api.main import app
from earthx.catalog.listed import (
    HAND_SOURCE,
    BlockReason,
    BlockRule,
    BlockScope,
    DataKind,
    DeliveryKind,
    ListedAccess,
    ListedEntry,
    load_listed,
    sort_title,
)
from earthx.catalog.listed_store import apply_blocklist, supersede, write_hand_entries
from earthx.catalog.load import main as load_catalog
from earthx.catalog.registry import AccountKind, SpatialExtent, TemporalExtent
from tests.catalog.entries import REGISTRY
from tests.catalog.listed_entries import listed_entry, utc
from tests.conftest import log_line_without_timestamp
from tests.integration.listed_rows import insert_row

pytestmark = pytest.mark.anyio

FULL = {config.dataset_id: config.title for config in REGISTRY}
# The full entries that reach Kenya: all but those of the Alps (swissALTI3D, BEV, the MeteoSwiss grids, M5-11).
GLOBAL_FULL = sorted(set(FULL) - {"swissalti3d", "bev-als-dgm", "meteoswiss-daily-1km", "meteoswiss-daily-precip-1km"})
_EXACT_LON, _EXACT_LAT = "7.123457", "46.654321"
KENYA = SpatialExtent(bbox=(36.0, -1.0, 37.0, 0.0))


def _entries() -> tuple[ListedEntry, ...]:
    """Seven listed entries whose titles fall between and after those of the full ones, two with one title."""
    return (
        listed_entry(
            "alpine-glacier-inventory",
            title="Alpine glacier inventory",
            spatial_extent=SpatialExtent(bbox=(6.0, 45.5, 14.0, 47.8)),
            temporal_extent=TemporalExtent(utc(2000), utc(2020, 12, 31)),
        ),
        listed_entry(
            "danube-flood-zones",
            title="Danube flood hazard zones",
            spatial_extent=SpatialExtent(bbox=(12.0, 47.8, 19.0, 48.8)),
            temporal_extent=TemporalExtent(None, None),
        ),
        listed_entry(
            "global-lightning-climatology",
            title="Global lightning climatology",
            spatial_extent=SpatialExtent(bbox=(-180.0, -60.0, 180.0, 80.0)),
            temporal_extent=TemporalExtent(utc(1998), utc(2013, 12, 31)),
        ),
        listed_entry(
            "bavaria-rainfall-gauges",
            title="Rainfall gauges of Bavaria",
            spatial_extent=SpatialExtent(bbox=(11.2, 48.2, 11.6, 48.4)),
            temporal_extent=TemporalExtent(utc(2015), None),
            publisher="Example Weather Service",
        ),
        listed_entry(
            "shared-title-b",
            title="Shared title",
            spatial_extent=KENYA,
            temporal_extent=TemporalExtent(utc(2010), utc(2012, 12, 31)),
        ),
        listed_entry(
            "shared-title-a",
            title="Shared title",
            spatial_extent=KENYA,
            temporal_extent=TemporalExtent(utc(2010), utc(2012, 12, 31)),
        ),
        listed_entry(
            "zurich-cadastral-map",
            title="Zurich cadastral map",
            data_kind=DataKind.VECTOR,
            spatial_extent=SpatialExtent(bbox=(8.4, 47.3, 8.7, 47.5)),
            temporal_extent=TemporalExtent(utc(2020), None),
            access=ListedAccess(AccountKind.PAID, "example-shop", DeliveryKind.ORDER),
        ),
    )


LISTED = {entry.dataset_id: entry for entry in _entries()}


def _by_title(titles: dict[str, str]) -> list[str]:
    return [dataset_id for _, dataset_id in sorted((sort_title(title), i) for i, title in titles.items())]


def _titles_of_listed(*ids: str) -> dict[str, str]:
    return {i: LISTED[i].title for i in ids}


ALL_IDS = _by_title({**FULL, **_titles_of_listed(*LISTED)})
LISTED_IDS = _by_title(_titles_of_listed(*LISTED))
FULL_IDS = _by_title(FULL)


def _commit(work) -> None:
    with psycopg.connect() as conn:
        work(conn)
        conn.commit()


def _write(*entries: ListedEntry, blocklist: tuple[BlockRule, ...] = ()) -> None:
    _commit(
        lambda conn: write_hand_entries(conn, [(entry, "a" * 64) for entry in entries], list(blocklist), full_ids=[])
    )


def _tombstone(dataset_id: str, reason: BlockReason) -> None:
    rule = BlockRule(BlockScope.ENTRY, reason, date(2026, 11, 1), source_id=HAND_SOURCE, source_key=dataset_id)
    _commit(lambda conn: apply_blocklist(conn, [rule]))


@pytest.fixture
def catalogue(require_postgres_env: None) -> Iterator[None]:
    """The registry loaded, then the listed rows of the test, committed; deleted again at the end, also after a failure."""
    assert load_catalog() == 0
    _write(*LISTED.values())
    try:
        yield
    finally:
        _commit(lambda conn: conn.execute("DELETE FROM public.earthx_listed_entry"))


@asynccontextmanager
async def _running() -> AsyncIterator[httpx.AsyncClient]:
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            yield http


@pytest.fixture
async def client(catalogue: None) -> AsyncIterator[httpx.AsyncClient]:
    async with _running() as http:
        yield http


def _ids(response: httpx.Response) -> list[str]:
    assert response.status_code == 200, response.text
    return [collection["id"] for collection in response.json()["collections"]]


def _next(response: httpx.Response) -> dict | None:
    return next((link for link in response.json()["links"] if link["rel"] == "next"), None)


async def _walk_get(client: httpx.AsyncClient, **params: object) -> tuple[list[str], list[httpx.Response]]:
    """Every id of the pages a search comes in, by the ``next`` link of each, and the pages."""
    seen: list[str] = []
    pages: list[httpx.Response] = []
    request = dict(params)
    while True:
        response = await client.get("/stac/collections", params=request)
        pages.append(response)
        seen += _ids(response)
        if (link := _next(response)) is None:
            return seen, pages
        assert link["method"] == "GET"
        request = dict(httpx.URL(link["href"]).params)


async def _walk_post(client: httpx.AsyncClient, body: dict) -> tuple[list[str], list[httpx.Response]]:
    seen: list[str] = []
    pages: list[httpx.Response] = []
    while True:
        response = await client.post("/stac/collections", json=body)
        pages.append(response)
        seen += _ids(response)
        if (link := _next(response)) is None:
            return seen, pages
        assert link["method"] == "POST"
        body = link["body"]


def _key(dataset_id: str) -> tuple[str, str]:
    titles = {**FULL, **{i: entry.title for i, entry in LISTED.items()}}
    return sort_title(titles[dataset_id]), dataset_id


def _by_id(body: dict) -> dict[str, dict]:
    return {collection["id"]: collection for collection in body["collections"]}


# --- one listed entry ------------------------------------------------------------------------------------------------


async def test_a_listed_entry_is_a_collection(client):
    response = await client.get("/stac/collections/bavaria-rainfall-gauges")
    assert response.status_code == 200
    document = response.json()
    assert (document["type"], document["id"], document["title"]) == (
        "Collection",
        "bavaria-rainfall-gauges",
        "Rainfall gauges of Bavaria",
    )
    assert document["earthx:entry"] == "listed"
    assert document["earthx:regions"] == ["DE", "DE-BY"]
    assert document["earthx:data_kind"] == "raster"
    assert document["earthx:access"] == {"account": "none", "account_provider": None, "delivery": "download"}
    assert document["earthx:listing"]["publisher"] == "Example Weather Service"
    assert document["extent"]["spatial"]["bbox"] == [[11.2, 48.2, 11.6, 48.4]]
    assert document["extent"]["temporal"]["interval"][0][1] is None
    assert not {"earthx:viewer", "earthx:capabilities", "earthx:source"} & set(document)


async def test_a_listed_entry_has_the_links_of_a_collection_and_its_link_to_the_source(client):
    links = (await client.get("/stac/collections/bavaria-rainfall-gauges")).json()["links"]
    rels = {link["rel"] for link in links}
    assert {"root", "self", "via"} <= rels
    own = next(link for link in links if link["rel"] == "self")
    assert own["href"] == "http://test/stac/collections/bavaria-rainfall-gauges"
    assert (
        next(link for link in links if link["rel"] == "via")["href"]
        == "https://data.example.org/bavaria-rainfall-gauges"
    )


async def test_a_paid_entry_says_so(client):
    document = (await client.get("/stac/collections/zurich-cadastral-map")).json()
    assert document["earthx:access"] == {"account": "paid", "account_provider": "example-shop", "delivery": "order"}
    assert document["earthx:data_kind"] == "vector"


async def test_a_full_entry_is_still_answered_by_pgstac(client):
    response = await client.get("/stac/collections/cop-dem-glo-30")
    assert response.status_code == 200 and response.json()["id"] == "cop-dem-glo-30"
    assert response.json()["earthx:viewer"] is not None


async def test_a_full_entry_says_it_is_full(client):
    assert (await client.get("/stac/collections/cop-dem-glo-30")).json()["earthx:entry"] == "full"


async def test_an_unknown_id_is_a_404(client):
    for dataset_id in ("no-such-entry", "proto-no-such-entry", "NO-SUCH-ENTRY"):
        assert (await client.get(f"/stac/collections/{dataset_id}")).status_code == 404


@pytest.mark.parametrize("state", ["in_review", "needs_rule", "blocked"])
async def test_a_row_that_is_not_published_is_a_404_and_on_no_page(client, state):
    _commit(lambda conn: insert_row(conn, "harvested-hidden", state=state, title="Hidden harvest"))
    assert (await client.get("/stac/collections/harvested-hidden")).status_code == 404
    assert "harvested-hidden" not in (await _walk_get(client, limit=5))[0]


async def test_a_superseded_row_is_a_404_for_its_id(client):
    _commit(lambda conn: supersede(conn, ["shared-title-a"]))
    assert (await client.get("/stac/collections/shared-title-a")).status_code == 404
    assert "shared-title-a" not in (await _walk_get(client, limit=5))[0]


# --- a tombstone -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("reason", list(BlockReason))
async def test_a_tombstone_is_a_410_with_the_general_text_of_its_reason_and_none_of_the_content(client, reason):
    _tombstone("bavaria-rainfall-gauges", reason)
    response = await client.get("/stac/collections/bavaria-rainfall-gauges")
    assert response.status_code == 410
    assert response.json() == {"detail": GONE_TEXT[reason.value]}
    for content in ("Rainfall", "Example Weather Service", "example.org", "synthetic", "11.2", "earthx:", "extent"):
        assert content not in response.text


async def test_a_vanished_hand_entry_is_a_410_with_its_own_text(client):
    _write(*(entry for entry in LISTED.values() if entry.dataset_id != "bavaria-rainfall-gauges"))
    response = await client.get("/stac/collections/bavaria-rainfall-gauges")
    assert (response.status_code, response.json()) == (410, {"detail": GONE_TEXT["source_removed"]})


def test_every_reason_has_its_own_text_and_none_names_a_person_or_a_source():
    assert set(GONE_TEXT) == {reason.value for reason in BlockReason} | {"source_removed"}
    assert len(set(GONE_TEXT.values())) == len(GONE_TEXT)
    for text in GONE_TEXT.values():
        assert text.startswith("This catalogue entry was removed") and len(text) < 100


async def test_a_tombstone_is_on_no_page_and_not_counted(client):
    _tombstone("bavaria-rainfall-gauges", BlockReason.QUALITY)
    seen, pages = await _walk_get(client, limit=4)
    assert seen == [i for i in ALL_IDS if i != "bavaria-rainfall-gauges"]
    assert pages[0].json()["numberMatched"] == len(ALL_IDS) - 1


async def test_the_items_of_a_tombstone_are_a_404(client):
    _tombstone("bavaria-rainfall-gauges", BlockReason.QUALITY)
    assert (await client.get("/stac/collections/bavaria-rainfall-gauges/items")).status_code == 404


# --- pages -----------------------------------------------------------------------------------------------------------


def test_the_synthetic_catalogue_interleaves_full_and_listed_entries_and_has_a_tie():
    kinds = ["full" if i in FULL else "listed" for i in ALL_IDS]
    assert kinds[0] == "listed" and kinds[-1] == "listed" and "full" in kinds[1:-1]
    assert ALL_IDS.index("shared-title-a") + 1 == ALL_IDS.index("shared-title-b")
    assert len(ALL_IDS) == 16


@pytest.mark.parametrize("limit", [1, 2, 3, 5, 15, 16, 17])
async def test_get_pages_walk_full_and_listed_entries_in_title_order_without_a_gap_or_a_duplicate(client, limit):
    seen, pages = await _walk_get(client, limit=limit)
    assert seen == ALL_IDS
    assert len(pages) == -(-len(ALL_IDS) // limit)
    # Counted on the first page only (plan A9).
    assert pages[0].json()["numberMatched"] == len(ALL_IDS)
    assert all("numberMatched" not in page.json() for page in pages[1:])
    assert [page.json()["numberReturned"] for page in pages] == [len(_ids(page)) for page in pages]


@pytest.mark.parametrize("limit", [1, 2, 5, 16])
async def test_post_pages_walk_the_same_order(client, limit):
    seen, pages = await _walk_post(client, {"limit": limit})
    assert seen == ALL_IDS
    assert _next(pages[0]) is None or _next(pages[0])["body"]["limit"] == limit


async def test_a_page_ends_with_no_next_link_exactly_at_the_end(client):
    exact = await client.get("/stac/collections", params={"limit": len(ALL_IDS)})
    assert _ids(exact) == ALL_IDS and _next(exact) is None
    short = await client.get("/stac/collections", params={"limit": len(ALL_IDS) - 1})
    assert _next(short) is not None


async def test_the_next_link_carries_the_search_and_the_token_of_the_last_entry(client):
    first = await client.get("/stac/collections", params={"limit": 2, "entry": "listed"})
    link = _next(first)
    params = dict(httpx.URL(link["href"]).params)
    assert (params["limit"], params["entry"]) == ("2", "listed") and "token" in params and "offset" not in params
    assert _ids(first) == LISTED_IDS[:2]


async def test_the_default_page_holds_everything_while_it_is_below_100(client):
    response = await client.get("/stac/collections", params={"entry": "listed"})
    assert _ids(response) == LISTED_IDS and _next(response) is None


async def test_a_limit_above_1000_is_a_valid_request_with_the_page_capped(client):
    response = await client.get("/stac/collections", params={"limit": 5000})
    assert _ids(response) == ALL_IDS


async def test_the_order_of_listed_entries_with_one_title_is_by_id(client):
    ids = _ids(await client.get("/stac/collections", params={"limit": 20}))
    assert ids.index("shared-title-a") < ids.index("shared-title-b")


async def test_a_token_works_on_an_app_started_afterwards(catalogue):
    # Nothing is kept in the process (plan §5.5): the token of one instance is a full page key for another.
    async with _running() as first_instance:
        first = await first_instance.get("/stac/collections", params={"limit": 4})
        link = _next(first)
    async with _running() as second_instance:
        second = await second_instance.get(link["href"])
        assert _ids(first) + _ids(second)[:4] == ALL_IDS[:8]
        both = await second_instance.get("/stac/collections", params={"limit": 8})
        assert _ids(both) == ALL_IDS[:8]


async def test_pages_go_on_when_an_entry_leaves_and_another_comes_between_two_requests(client):
    first = await client.get("/stac/collections", params={"limit": 4})
    assert _ids(first) == ALL_IDS[:4] and ALL_IDS[3] == "danube-flood-zones"
    _tombstone("danube-flood-zones", BlockReason.NOT_GEODATA)  # the entry the token stands on leaves ...
    _commit(
        lambda conn: insert_row(conn, "eager-new-entry", title="Eager new entry")
    )  # ... one sorts right behind it ...
    _commit(
        lambda conn: insert_row(conn, "aardvark-atlas", title="Aardvark atlas")
    )  # ... one in front of the page seen
    rest, _ = await _walk_get(client, **dict(httpx.URL(_next(first)["href"]).params))
    assert rest == ["eager-new-entry", *ALL_IDS[4:]]


# --- misuse of the token, the limit and the parameters ---------------------------------------------------------------


@pytest.mark.parametrize("token", ["!!!", "bm90IGpzb24=", "A" * 1001, "W10=", "WyJhIl0=", "WzEsMl0="])
async def test_a_token_this_api_did_not_give_out_is_a_400_and_is_not_repeated(client, token):
    response = await client.get("/stac/collections", params={"token": token})
    assert response.status_code == 400 and token not in response.text
    response = await client.post("/stac/collections", json={"token": token})
    assert response.status_code == 400 and token not in response.text


async def test_a_token_with_text_is_a_400(client):
    token = dict(httpx.URL(_next(await client.get("/stac/collections", params={"limit": 2}))["href"]).params)["token"]
    assert (await client.get("/stac/collections", params={"q": "elevation", "token": token})).status_code == 400
    assert (await client.post("/stac/collections", json={"q": "elevation", "token": token})).status_code == 400


@pytest.mark.parametrize("params", [{"limit": "0"}, {"limit": "-1"}, {"limit": "many"}, {"offset": "5", "limit": "2"}])
async def test_a_limit_or_an_offset_that_does_not_fit_is_a_400(client, params):
    assert (await client.get("/stac/collections", params=params)).status_code == 400


@pytest.mark.parametrize("body", [{"limit": 0}, {"limit": -3}, {"offset": 2, "limit": 2}, {"token": 5}, {"entry": "x"}])
async def test_a_body_that_does_not_fit_is_a_400(client, body):
    assert (await client.post("/stac/collections", json=body)).status_code == 400


@pytest.mark.parametrize("params", [{"entry": "everything"}, {"entry": "FULL"}, {"entry": ""}])
async def test_an_entry_that_is_not_full_or_listed_is_a_400(client, params):
    assert (await client.get("/stac/collections", params={**params, "limit": 2})).status_code == 400


@pytest.mark.parametrize("region", ["bavaria", "de", "DEU", "DE-", "DE-BAYE", ",", "DE;AT"])
async def test_a_region_that_is_no_iso_code_is_a_400(client, region):
    assert (await client.get("/stac/collections", params={"region": region})).status_code == 400
    assert (await client.post("/stac/collections", json={"region": [region]})).status_code == 400


async def test_a_refused_region_is_not_repeated_in_the_answer(client):
    for response in (
        await client.get("/stac/collections", params={"region": "Bavaria-ish"}),
        await client.post("/stac/collections", json={"region": ["Bavaria-ish"]}),
    ):
        assert response.status_code == 400 and "Bavaria-ish" not in response.text


async def test_more_than_50_regions_are_a_400(client):
    codes = [f"{a}{b}" for a in "AB" for b in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"][:51]
    assert (await client.get("/stac/collections", params={"region": ",".join(codes)})).status_code == 400
    assert (await client.post("/stac/collections", json={"region": codes})).status_code == 400
    assert (await client.get("/stac/collections", params={"region": ",".join(codes[:50])})).status_code == 200


# --- entry ------------------------------------------------------------------------------------------------------------


async def test_entry_listed_holds_only_listed_entries_and_entry_full_only_full_ones(client):
    listed, listed_pages = await _walk_get(client, entry="listed", limit=3)
    assert listed == LISTED_IDS
    full, full_pages = await _walk_get(client, entry="full", limit=4)
    assert full == FULL_IDS
    assert listed_pages[0].json()["numberMatched"] == len(LISTED_IDS)
    assert full_pages[0].json()["numberMatched"] == len(FULL_IDS)
    for page in listed_pages:
        assert {c["earthx:entry"] for c in page.json()["collections"]} == {"listed"}


async def test_entry_full_is_the_whole_registry_in_title_order_and_needs_no_listed_row(client):
    response = await client.post("/stac/collections", json={"entry": "full"})
    assert _ids(response) == FULL_IDS and _next(response) is None


async def test_with_text_only_full_entries_are_searched_until_m5_42(client):
    # Plan F7: `q` does not reach the listed entries; no listed entry turns up for text that fits its title.
    response = await client.get("/stac/collections", params={"q": "Rainfall gauges of Bavaria"})
    assert not set(_ids(response)) & set(LISTED)
    response = await client.get("/stac/collections", params={"q": "elevation", "entry": "listed"})
    assert _ids(response) == [] and response.json()["numberMatched"] == 0


# --- region -----------------------------------------------------------------------------------------------------------


async def test_a_region_keeps_the_listed_entries_in_it(client):
    ids = _ids(await client.get("/stac/collections", params={"region": "DE-BY", "entry": "listed"}))
    assert "bavaria-rainfall-gauges" in ids and "global-lightning-climatology" in ids
    assert not {"shared-title-a", "shared-title-b", "zurich-cadastral-map"} & set(ids)
    documents = _by_id((await client.get("/stac/collections", params={"region": "DE-BY", "entry": "listed"})).json())
    assert all("DE-BY" in document["earthx:regions"] for document in documents.values())


async def test_a_region_keeps_the_full_entries_whose_box_overlaps_it_too(client):
    # Kenya: the global full entries, not those of the Alps (GLOBAL_FULL); listed ones by their box.
    ids = _ids(await client.get("/stac/collections", params={"region": "KE", "limit": 50}))
    assert ids == _by_title({**{i: FULL[i] for i in GLOBAL_FULL}, **_titles_of_listed(*LISTED_IDS_IN_KENYA)})


LISTED_IDS_IN_KENYA = ("global-lightning-climatology", "shared-title-a", "shared-title-b")


async def test_one_region_of_several_is_enough(client):
    body = {"region": ["KE", "DE-BY"], "entry": "listed"}
    assert set(_ids(await client.post("/stac/collections", json=body))) >= {"bavaria-rainfall-gauges", "shared-title-a"}
    got = await client.get("/stac/collections", params={"region": "KE,DE-BY", "entry": "listed"})
    assert set(_ids(got)) >= {"bavaria-rainfall-gauges", "shared-title-a"}


@pytest.mark.parametrize("region", ["ZZ", "JP-13"])
async def test_a_region_that_no_entry_is_in_gives_an_empty_page_and_no_link(client, region):
    for params in ({"region": region}, {"region": region, "entry": "listed"}):
        response = await client.get("/stac/collections", params=params)
        assert (_ids(response), response.json()["numberMatched"], _next(response)) == ([], 0, None)
    assert _ids(await client.post("/stac/collections", json={"region": [region]})) == []


async def test_a_region_filter_pages_without_a_gap(client):
    seen, _ = await _walk_get(client, region="KE", limit=2)
    assert seen == _by_title({**{i: FULL[i] for i in GLOBAL_FULL}, **_titles_of_listed(*LISTED_IDS_IN_KENYA)})


# --- area -------------------------------------------------------------------------------------------------------------


async def test_a_bbox_keeps_what_meets_it(client):
    ids = _ids(await client.get("/stac/collections", params={"bbox": "11.3,48.25,11.5,48.35", "entry": "listed"}))
    assert ids == _by_title(_titles_of_listed("bavaria-rainfall-gauges", "global-lightning-climatology"))
    kenya = _ids(await client.get("/stac/collections", params={"bbox": "36,-1,37,0", "entry": "listed"}))
    assert kenya == _by_title(_titles_of_listed(*LISTED_IDS_IN_KENYA))


async def test_corine_is_found_in_its_countries_and_not_in_morocco_inside_its_box(client):
    """M5-17 F4: the footprint of CORINE is the union of its 39 states, not its box, which reaches into North Africa."""
    corine = next(entry for entry, _ in load_listed() if entry.dataset_id == "corine-land-cover")
    _write(*LISTED.values(), corine)
    marrakesh = _ids(await client.get("/stac/collections", params={"bbox": "-8.5,31.0,-7.5,32.0", "entry": "listed"}))
    vienna = _ids(await client.get("/stac/collections", params={"bbox": "16.2,48.1,16.5,48.3", "entry": "listed"}))
    assert "corine-land-cover" not in marrakesh
    assert "corine-land-cover" in vienna
    assert "corine-land-cover" not in _ids(await client.get("/stac/collections", params={"region": "MA"}))
    assert "corine-land-cover" in _ids(await client.get("/stac/collections", params={"region": "AT-9"}))


async def test_a_bbox_filter_applies_to_full_entries_in_the_same_order(client):
    ids = _ids(await client.get("/stac/collections", params={"bbox": "8.5,47.35,8.6,47.45"}))
    assert "zurich-cadastral-map" in ids and "swissalti3d" in ids and "shared-title-a" not in ids
    assert ids == sorted(ids, key=_key)


async def test_intersects_by_post_is_the_area_of_the_frontend_for_listed_entries_too(client):
    area = {"type": "Polygon", "coordinates": [[[36.1, -0.9], [36.9, -0.9], [36.9, -0.1], [36.1, -0.9]]]}
    response = await client.post("/stac/collections", json={"intersects": area, "entry": "listed"})
    assert _ids(response) == _by_title(_titles_of_listed(*LISTED_IDS_IN_KENYA))


async def test_a_box_across_the_antimeridian_is_two_boxes_for_listed_entries_too(client):
    # 170° E to 170° W over Fiji: only the entry that spans the world; read the other way round it would hold Europe.
    response = await client.get("/stac/collections", params={"bbox": "170,-20,-170,-10", "entry": "listed"})
    assert _ids(response) == ["global-lightning-climatology"]
    response = await client.post("/stac/collections", json={"bbox": [170, -20, -170, -10], "entry": "listed"})
    assert _ids(response) == ["global-lightning-climatology"]


async def test_a_box_that_touches_an_entry_meets_it(client):
    # Plan §5.5: ST_Intersects; the box begins where the box of the Zurich entry ends.
    ids = _ids(await client.get("/stac/collections", params={"bbox": "8.7,47.5,9.0,47.8", "entry": "listed"}))
    assert "zurich-cadastral-map" in ids


@pytest.mark.parametrize(
    "params",
    [{"bbox": "x"}, {"bbox": "1,2,3"}, {"bbox": "7,95,8,96"}, {"bbox": "190,46,191,47"}, {"bbox": "7,47,8,46"}],
)
async def test_a_bbox_that_does_not_fit_is_a_400_without_the_catalogue_being_read(client, params):
    response = await client.get("/stac/collections", params={**params, "entry": "listed"})
    assert response.status_code == 400


# --- time -------------------------------------------------------------------------------------------------------------


async def test_an_entry_without_a_period_stays_under_a_time_filter_and_is_named(client):
    period = "2001-01-01T00:00:00Z/2005-12-31T23:59:59Z"
    response = await client.get("/stac/collections", params={"datetime": period, "entry": "listed"})
    body = response.json()
    assert _ids(response) == _by_title(
        _titles_of_listed("alpine-glacier-inventory", "danube-flood-zones", "global-lightning-climatology")
    )
    assert body["ignored_filters"] == ["datetime"]
    assert body["ignored_filters_by_collection"] == {"danube-flood-zones": ["datetime"]}
    assert body["numberMatched"] == 3


async def test_a_time_filter_names_the_full_entries_it_could_not_apply_to_as_before(client):
    period = "2001-01-01T00:00:00Z/2005-12-31T23:59:59Z"
    body = (await client.get("/stac/collections", params={"datetime": period, "limit": 50})).json()
    assert {"cop-dem-glo-30", "danube-flood-zones"} <= set(body["ignored_filters_by_collection"])
    assert body["ignored_filters_by_collection"]["cop-dem-glo-30"] == ["datetime"]
    assert "alpine-glacier-inventory" not in body["ignored_filters_by_collection"]


async def test_a_time_filter_over_pages_names_only_the_entries_of_each_page(client):
    period = "2001-01-01T00:00:00Z/2005-12-31T23:59:59Z"
    _, pages = await _walk_get(client, datetime=period, entry="listed", limit=1)
    for page in pages:
        body = page.json()
        assert set(body.get("ignored_filters_by_collection", {})) <= {c["id"] for c in body["collections"]}
    assert [bool(page.json().get("ignored_filters")) for page in pages] == [False, True, False]


async def test_an_instant_is_a_period_of_one_moment(client):
    ids = _ids(await client.get("/stac/collections", params={"datetime": "2012-06-01T00:00:00Z", "entry": "listed"}))
    assert ids == _by_title(
        _titles_of_listed(
            "alpine-glacier-inventory",
            "danube-flood-zones",
            "global-lightning-climatology",
            "shared-title-a",
            "shared-title-b",
        )
    )


async def test_an_open_end_of_the_filter_and_an_open_end_of_an_entry(client):
    ids = _ids(await client.get("/stac/collections", params={"datetime": "2030-01-01T00:00:00Z/..", "entry": "listed"}))
    assert ids == _by_title(_titles_of_listed("bavaria-rainfall-gauges", "danube-flood-zones", "zurich-cadastral-map"))
    ids = _ids(await client.get("/stac/collections", params={"datetime": "../1990-01-01T00:00:00Z", "entry": "listed"}))
    assert ids == ["danube-flood-zones"]


async def test_no_time_filter_names_nothing_as_ignored(client):
    body = (await client.get("/stac/collections", params={"entry": "listed"})).json()
    assert "ignored_filters" not in body and "ignored_filters_by_collection" not in body


@pytest.mark.parametrize("value", ["2005-01-01T00:00:00Z/2000-01-01T00:00:00Z", "2020", "not a time"])
async def test_a_period_that_does_not_fit_is_a_400(client, value):
    assert (await client.get("/stac/collections", params={"datetime": value, "entry": "listed"})).status_code == 400
    assert (await client.post("/stac/collections", json={"datetime": value, "entry": "listed"})).status_code == 400


async def test_area_region_and_time_together_narrow_one_another(client):
    body = {
        "bbox": [36, -1, 37, 0],
        "region": ["KE"],
        "datetime": "2011-01-01T00:00:00Z/2011-12-31T00:00:00Z",
        "entry": "listed",
    }
    assert _ids(await client.post("/stac/collections", json=body)) == _by_title(_titles_of_listed(*LISTED_IDS_IN_KENYA))
    body["datetime"] = "2016-01-01T00:00:00Z/2016-12-31T00:00:00Z"
    assert _ids(await client.post("/stac/collections", json=body)) == []


# --- numberMatched ----------------------------------------------------------------------------------------------------


def _bulk(count: int, first: int = 1) -> None:
    def insert(conn: psycopg.Connection) -> None:
        conn.execute(
            """
            INSERT INTO public.earthx_listed_entry (dataset_id, source_id, source_key, state, content, content_sha256,
                sort_title, footprint, regions, keywords, data_kind, category, account, delivery, publisher, link_host)
            SELECT 'bulk-' || n, 'bulk', 'bulk-' || n, 'published',
                   jsonb_build_object('type', 'Collection', 'id', 'bulk-' || n, 'title', 'zz bulk ' || n),
                   'x', 'zz bulk ' || lpad(n::text, 8, '0'), ST_MakeEnvelope(0, 0, 1, 1, 4326), '{}', '{bulk}', 'vector', 'other', 'none',
                   'download', 'P', 'bulk.example.org'
            FROM generate_series(%s::int, %s::int) AS n
            """,
            (first, first + count - 1),
        )

    _commit(insert)


async def test_number_matched_is_exact_up_to_10000_and_left_out_above(client):
    _bulk(10_000 - len(ALL_IDS))
    at_the_cap = (await client.get("/stac/collections", params={"limit": 2})).json()
    assert at_the_cap["numberMatched"] == 10_000
    _bulk(1, first=50_000_000)
    above = await client.get("/stac/collections", params={"limit": 2})
    assert above.status_code == 200 and "numberMatched" not in above.json()
    assert above.json()["numberReturned"] == 2 and _next(above) is not None
    # A filter that narrows the catalogue, or a kind of entry, brings the number back.
    narrow = (await client.get("/stac/collections", params={"region": "KE", "entry": "listed"})).json()
    assert narrow["numberMatched"] == len(LISTED_IDS_IN_KENYA)
    assert (await client.get("/stac/collections", params={"entry": "full"})).json()["numberMatched"] == len(FULL_IDS)


async def test_number_matched_is_there_for_a_small_catalogue_and_counts_what_the_filter_matches(client):
    assert (await client.get("/stac/collections", params={"limit": 2})).json()["numberMatched"] == len(ALL_IDS)
    kenya = (await client.get("/stac/collections", params={"bbox": "36,-1,37,0", "limit": 2})).json()
    assert kenya["numberMatched"] == len(GLOBAL_FULL) + len(LISTED_IDS_IN_KENYA) and kenya["numberReturned"] == 2


# --- items ------------------------------------------------------------------------------------------------------------


async def test_the_items_of_a_listed_entry_are_an_empty_feature_collection(client):
    response = await client.get("/stac/collections/bavaria-rainfall-gauges/items")
    assert response.status_code == 200
    assert response.json()["type"] == "FeatureCollection" and response.json()["features"] == []


async def test_the_items_of_a_listed_entry_stay_empty_under_any_item_filter(client):
    for params in ({"bbox": "11,48,12,49"}, {"datetime": "2016-01-01T00:00:00Z/2016-12-31T00:00:00Z"}, {"limit": "5"}):
        response = await client.get("/stac/collections/bavaria-rainfall-gauges/items", params=params)
        assert (response.status_code, response.json()["features"]) == (200, [])


async def test_a_single_item_of_a_listed_entry_is_a_404(client):
    assert (await client.get("/stac/collections/bavaria-rainfall-gauges/items/anything")).status_code == 404


async def test_a_search_that_names_a_listed_entry_is_a_400(client):
    response = await client.post("/stac/search", json={"collections": ["bavaria-rainfall-gauges"]})
    assert response.status_code == 400 and "catalogue entry without items" in response.text
    mixed = await client.post("/stac/search", json={"collections": ["cop-dem-glo-30", "bavaria-rainfall-gauges"]})
    assert mixed.status_code == 400
    by_get = await client.get("/stac/search", params={"collections": "bavaria-rainfall-gauges"})
    assert by_get.status_code == 400


# --- logs -------------------------------------------------------------------------------------------------------------


async def test_neither_the_area_nor_the_region_nor_the_token_reaches_the_access_log(client, access_log_lines):
    area = {"type": "Polygon", "coordinates": [[[7.123457, 46.654321], [8, 46.654321], [8, 47], [7.123457, 46.654321]]]}
    first = await client.get(
        "/stac/collections", params={"bbox": "7.123457,46.654321,8,47", "region": "DE-BY,AT", "limit": 1}
    )
    assert first.is_success
    link = _next(first)
    token = dict(httpx.URL(link["href"]).params)["token"]
    assert (await client.get(link["href"])).is_success
    posted = await client.post("/stac/collections", json={"intersects": area, "region": ["DE-BY"], "limit": 1})
    assert posted.is_success
    assert (await client.post("/stac/collections", json={"token": token, "limit": 1})).is_success
    assert (await client.get("/stac/collections", params={"token": "!!!", "region": "DE-BY"})).status_code == 400
    assert len(access_log_lines) == 5
    for raw in access_log_lines:
        line = log_line_without_timestamp(raw)
        for secret in (_EXACT_LON, _EXACT_LAT, "DE-BY", token, "region", "token", "bbox", "?"):
            assert secret not in line
    assert json.dumps(access_log_lines).count(token) == 0


# --- review of M5-40: keys that a collation like en_US orders differently, and a listed row with a full entry's id ---


async def test_titles_and_ids_with_spaces_and_punctuation_page_without_a_gap(client):
    # Under en_US "land use" sorts after "landsat 8" (spaces skipped), in Python before: one page each must reach both.
    extra = (
        listed_entry("x-2", title="Land use", spatial_extent=KENYA),
        listed_entry("x1", title="Landsat 8", spatial_extent=KENYA),
        listed_entry("x.3", title="Land-use", spatial_extent=KENYA),
    )
    _write(*LISTED.values(), *extra)
    seen, _ = await _walk_get(client, entry="listed", limit=1)
    expected = _by_title({**_titles_of_listed(*LISTED), **{entry.dataset_id: entry.title for entry in extra}})
    assert seen == expected


async def test_a_listed_row_with_the_id_and_title_of_a_full_entry_shows_the_full_one_once(client):
    # Between a harvest and the next catalogue load a published row can carry a full entry's id (plan §5.3, step 4).
    full_id = "cop-dem-glo-30"
    _commit(lambda conn: insert_row(conn, full_id, source_key="dem", title=FULL[full_id]))
    seen, _ = await _walk_get(client, limit=3)
    assert seen.count(full_id) == 1
    assert (await client.get(f"/stac/collections/{full_id}")).json()["earthx:entry"] == "full"


# --- the category filter (M5-40 G6; one group of the Data catalogue per category) ------------------------------------


async def test_the_category_filter_keeps_full_and_listed_entries_of_that_category(client):
    # Every listed entry of these tests is in `water`; the full entries keep their categories of before.
    water, _ = await _walk_get(client, category="water", limit=3)
    assert water == LISTED_IDS
    elevation, _ = await _walk_get(client, category="elevation", limit=3)
    assert elevation == _by_title({i: FULL[i] for i in FULL if REGISTRY.get(i).category == "elevation"})
    body = {"category": "water", "entry": "full"}
    assert _ids(await client.post("/stac/collections", json=body)) == []


async def test_a_category_filter_with_text_keeps_only_full_entries_of_it(client):
    response = await client.get("/stac/collections", params={"q": "elevation", "category": "elevation"})
    assert set(_ids(response)) <= {i for i in FULL if REGISTRY.get(i).category == "elevation"}


async def test_an_unknown_category_is_a_400(client):
    assert (await client.get("/stac/collections", params={"category": "volcanoes"})).status_code == 400
    assert (await client.post("/stac/collections", json={"category": "Water"})).status_code == 400


async def test_a_listed_entry_carries_its_category(client):
    assert (await client.get("/stac/collections/zurich-cadastral-map")).json()["earthx:category"] == "water"

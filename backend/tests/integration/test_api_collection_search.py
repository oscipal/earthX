"""T-C: Collection Search with ``q`` on ``/stac/collections`` (M5-22 plan §3.7, §4; adr/0026 §4.5, F6, F9).

The running `api` app over the catalogue of the registry in pgstac and the search index, both written by
``catalog-load``. Nothing goes out: neither the search nor the collection documents leave the database.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import pytest

from earthx.api.main import app
from earthx.catalog.load import main as load_catalog
from earthx.catalog.search import MAX_QUERY_CHARS
from tests.catalog.entries import REGISTRY
from tests.conftest import log_line_without_timestamp

pytestmark = pytest.mark.anyio

ALL_IDS = sorted(config.dataset_id for config in REGISTRY)
KENYA = {"type": "Polygon", "coordinates": [[[36.0, -1.0], [37.0, -1.0], [37.0, 0.0], [36.0, 0.0], [36.0, -1.0]]]}
# Distinctive values: if one turns up in an access-log line, the line carries the search.
_EXACT_LON, _EXACT_LAT = "7.123457", "46.654321"
_TEXT = "Bodenreflexion"


@pytest.fixture
async def client(require_postgres_env: None) -> AsyncIterator[httpx.AsyncClient]:
    assert load_catalog() == 0
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            yield http


def _ids(response: httpx.Response) -> list[str]:
    assert response.status_code == 200, response.text
    return [collection["id"] for collection in response.json()["collections"]]


def _next(response: httpx.Response) -> dict | None:
    return next((link for link in response.json()["links"] if link["rel"] == "next"), None)


# --- without a parameter -----------------------------------------------------------------------------------------------


async def test_without_a_parameter_every_collection_comes_as_before(client):
    # Plan A5, A15: the list the frontend loads, every collection by id, no paging and no search field.
    response = await client.get("/stac/collections")
    body = response.json()
    assert _ids(response) == ALL_IDS
    assert set(body) == {"collections", "links", "numberMatched", "numberReturned"}
    assert (body["numberMatched"], body["numberReturned"]) == (len(ALL_IDS), len(ALL_IDS))
    assert [link["rel"] for link in body["links"]] == ["root", "self"]
    for collection in body["collections"]:
        assert collection == (await client.get(f"/stac/collections/{collection['id']}")).json()


async def test_an_empty_body_lists_the_same(client):
    assert (await client.post("/stac/collections", json={})).json() == (await client.get("/stac/collections")).json()


# --- text --------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["GET", "POST"])
async def test_q_ranks_the_collections(client, method):
    response = await (
        client.get("/stac/collections", params={"q": "Sentinel-2"})
        if method == "GET"
        else client.post("/stac/collections", json={"q": "Sentinel-2"})
    )
    assert _ids(response)[0] == "sentinel-2-c1-l2a"
    assert "score" not in json.dumps(response.json())


@pytest.mark.parametrize("text", ["Sentinel-3", "Landsat 9", "Bevölkerungsdichte"])
async def test_nothing_fits_an_empty_list(client, text):
    response = await client.get("/stac/collections", params={"q": text})
    assert _ids(response) == []
    assert (response.json()["numberMatched"], _next(response)) == (0, None)


async def test_a_comma_is_an_ordinary_separator(client):
    # No Free-text syntax: "radar,backscatter" is the same search as "radar backscatter", not an OR of two.
    by_comma = _ids(await client.get("/stac/collections", params={"q": "radar,backscatter"}))
    assert by_comma == _ids(await client.get("/stac/collections", params={"q": "radar backscatter"}))


async def test_only_spaces_is_no_text(client):
    assert _ids(await client.get("/stac/collections", params={"q": "   "})) == ALL_IDS


async def test_two_hundred_characters_are_a_query_and_one_more_is_not(client):
    assert (await client.get("/stac/collections", params={"q": "a" * MAX_QUERY_CHARS})).status_code == 200
    response = await client.post("/stac/collections", json={"q": "a" * (MAX_QUERY_CHARS + 1)})
    assert response.status_code == 400
    assert "a" * 20 not in response.text


# --- pages -------------------------------------------------------------------------------------------------------------


async def test_a_get_page_links_the_next_one(client):
    first = await client.get("/stac/collections", params={"q": "Sentinel", "limit": 2})
    assert len(_ids(first)) == 2 and first.json()["numberMatched"] > 2
    link = _next(first)
    assert link["method"] == "GET" and "offset=2" in link["href"]
    second = await client.get(link["href"])
    assert set(_ids(second)).isdisjoint(_ids(first))


async def test_a_post_page_links_the_next_one_with_its_body(client):
    first = await client.post("/stac/collections", json={"q": "Sentinel", "limit": 2})
    link = _next(first)
    assert link["method"] == "POST" and link["body"] == {"q": "Sentinel", "limit": 2, "offset": 2}
    second = await client.post("/stac/collections", json=link["body"])
    assert set(_ids(second)).isdisjoint(_ids(first))
    every = _ids(await client.post("/stac/collections", json={"q": "Sentinel"}))
    assert _ids(first) + _ids(second) == every[:4]


async def test_the_last_page_links_no_next_one(client):
    assert _next(await client.get("/stac/collections", params={"q": "Sentinel-2", "limit": 20})) is None


async def test_without_text_a_limit_pages_by_id(client):
    response = await client.get("/stac/collections", params={"limit": 2, "offset": 2})
    assert _ids(response) == ALL_IDS[2:4]


# --- area and time -----------------------------------------------------------------------------------------------------


async def test_a_bbox_by_get_keeps_what_meets_it(client):
    # The Kenya box of Q28: everything global, not swissALTI3D.
    assert "swissalti3d" not in _ids(await client.get("/stac/collections", params={"bbox": "36,-1,37,0"}))
    assert "swissalti3d" in _ids(await client.get("/stac/collections", params={"bbox": "7,46,8,47"}))


async def test_intersects_by_post_is_the_area_of_the_frontend(client):
    response = await client.post("/stac/collections", json={"q": "land cover", "intersects": KENYA})
    assert set(_ids(response)) == {"esa-worldcover-2020", "esa-worldcover-2021"}


async def test_a_box_across_the_antimeridian_is_two_boxes(client):
    # 170° E to 170° W over Fiji: global datasets only; read as 170° W to 170° E it would hold Switzerland.
    response = await client.post("/stac/collections", json={"bbox": [170, -20, -170, -10]})
    assert "swissalti3d" not in _ids(response) and "cop-dem-glo-30" in _ids(response)


async def test_a_dataset_without_a_time_axis_stays_and_is_named(client):
    period = "2000-01-01T00:00:00Z/2005-12-31T23:59:59Z"
    body = (await client.get("/stac/collections", params={"q": "elevation", "datetime": period})).json()
    assert "cop-dem-glo-30" in [collection["id"] for collection in body["collections"]]
    assert body["ignored_filters"] == ["datetime"]
    assert body["ignored_filters_by_collection"]["cop-dem-glo-30"] == ["datetime"]


async def test_a_time_series_outside_the_period_drops_out(client):
    # Q32: Sentinel-1 begins in 2014.
    response = await client.post(
        "/stac/collections", json={"q": "SAR", "datetime": "2000-01-01T00:00:00Z/2005-12-31T23:59:59Z"}
    )
    assert "sentinel-1-grd" not in _ids(response)


# --- refused -----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "params",
    [
        {"bbox": "x"},
        {"bbox": "1,2,3"},
        {"bbox": "7,95,8,96"},
        {"bbox": "190,46,191,47"},
        {"bbox": "7,47,8,46"},
        {"intersects": json.dumps(KENYA)},
        {"datetime": "2005-01-01T00:00:00Z/2000-01-01T00:00:00Z"},
        {"datetime": "2020"},
        {"limit": "0"},
        {"offset": "-1"},
        {"filter": "id = 'x'"},
        {"sortby": "id"},
        {"query": "{}"},
        {"fields": "id"},
    ],
)
async def test_get_refuses_what_is_no_valid_search(client, params):
    assert (await client.get("/stac/collections", params=params)).status_code == 400


@pytest.mark.parametrize(
    "body",
    [
        {"unknown": 1},
        {"filter": {"op": "=", "args": [1, 1]}},
        {"q": ["Sentinel-2"]},
        {"bbox": [36, -1, 37, 0], "intersects": KENYA},
        {"intersects": {"type": "Point", "coordinates": [10.0, 999.0]}},
        {"intersects": {"type": "Polygon", "coordinates": "nothing"}},
        {"bbox": [1, 2, 3, 4, 5]},
        {"datetime": "not a time"},
        {"limit": 0},
    ],
)
async def test_post_refuses_what_is_no_valid_search(client, body):
    assert (await client.post("/stac/collections", json=body)).status_code == 400


@pytest.mark.parametrize(
    "body",
    [
        {"q": _TEXT, "intersects": {"type": "Point", "coordinates": [7.123457, 46.654321]}, "limit": 0},
        {"q": _TEXT, "bbox": [7.123457, 46.654321, 8, 47], "unknown": 1},
        {"q": _TEXT, "intersects": {"type": "Polygon", "coordinates": [[7.123457, 46.654321]]}},
        {"q": _TEXT, "intersects": {"type": "Point", "coordinates": [7.123457, 95.654321]}},
    ],
)
async def test_a_refusal_repeats_neither_the_text_nor_the_area(client, body):
    response = await client.post("/stac/collections", json=body)
    assert response.status_code == 400
    assert _TEXT not in response.text and "7.123457" not in response.text


async def test_a_refusal_elsewhere_keeps_the_answer_of_the_library(client):
    response = await client.post("/stac/search", json={"collections": ["sentinel-2-c1-l2a"], "limit": "many"})
    assert response.status_code == 400 and "body" in response.json()


async def test_an_unknown_parameter_lists_every_collection(client):
    assert _ids(await client.get("/stac/collections", params={"unknown": "1"})) == ALL_IDS


async def test_a_bowtie_area_is_answered(client):
    # A self-crossing ring is a mistake of the caller, not of this server.
    bowtie = {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]}
    assert (await client.post("/stac/collections", json={"intersects": bowtie})).status_code == 200


# --- conformance and logs ----------------------------------------------------------------------------------------------


async def test_the_landing_page_claims_collection_search_but_not_free_text(client):
    classes = (await client.get("/stac/conformance")).json()["conformsTo"]
    assert any(c.endswith("/collection-search") for c in classes)
    assert not any("free-text" in c for c in classes)
    assert (await client.get("/stac/")).json()["conformsTo"] == classes


async def test_neither_the_text_nor_the_area_reaches_the_access_log(client, access_log_lines):
    area = {"type": "Polygon", "coordinates": [[[7.123457, 46.654321], [8, 46.654321], [8, 47], [7.123457, 46.654321]]]}
    assert (await client.get("/stac/collections", params={"q": _TEXT, "bbox": "7.123457,46.654321,8,47"})).is_success
    assert (await client.post("/stac/collections", json={"q": _TEXT, "intersects": area})).is_success
    assert (await client.get("/stac/collections", params={"q": _TEXT, "bbox": "x"})).status_code == 400
    assert len(access_log_lines) == 3
    for raw in access_log_lines:
        line = log_line_without_timestamp(raw)
        assert _TEXT not in line and _EXACT_LON not in line and _EXACT_LAT not in line and "?" not in line

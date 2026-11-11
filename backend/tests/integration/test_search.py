"""The lexical arm and its hard filters over a synthetic catalogue (M5-22 plan §3.5, §3.6, §4)."""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest

from earthx.catalog.glossary import load_glossary
from earthx.catalog.pgstac import load_collection, upsert_items, use_pgstac_search_path
from earthx.catalog.registry import DatasetConfig, DatasetRegistry, SpatialExtent, TemporalExtent
from earthx.catalog.search import (
    MAX_QUERY_CHARS,
    Joining,
    QueryTooLong,
    box_area,
    fuse,
    ranks,
    search_datasets,
)
from earthx.catalog.search_index import write_search_index
from tests.catalog.entries import COP_DEM_GLO_30, SENTINEL_2_L2A, SWISSALTI3D

GLOSSARY = load_glossary()


def _entry(
    base: DatasetConfig, dataset_id: str, title: str, keywords: tuple[str, ...], **changes: Any
) -> DatasetConfig:
    return dataclasses.replace(
        base,
        dataset_id=dataset_id,
        title=title,
        description=changes.pop("description", "A synthetic entry of the search tests."),
        keywords=keywords,
        **changes,
    )


# Three static rasters over one box, a time series, and a materialized dataset whose box is wide but whose items cover
# one small square only. Keywords chosen so each test can tell them apart.
TERRAIN = _entry(SWISSALTI3D, "test-terrain", "Terrain Alpha", ("digital terrain model", "alpine"))
SURFACE = _entry(SWISSALTI3D, "test-surface", "Surface Beta", ("digital surface model", "alpine"))
KENYA = _entry(
    SWISSALTI3D,
    "test-kenya",
    "Equator Gamma",
    ("land cover", "savanna"),
    spatial_extent=SpatialExtent((36.0, -1.0, 37.0, 0.0)),
)
SERIES = _entry(
    SENTINEL_2_L2A,
    "test-series",
    "Series Delta",
    ("multispectral", "alpine"),
    temporal_extent=TemporalExtent(datetime(2015, 1, 1, tzinfo=UTC), None),
)
FOOTPRINTS = _entry(
    COP_DEM_GLO_30,
    "test-footprints",
    "Footprint Epsilon",
    ("elevation", "alpine"),
    spatial_extent=SpatialExtent((0.0, 40.0, 20.0, 50.0)),
)
CATALOGUE = DatasetRegistry((TERRAIN, SURFACE, KENYA, SERIES, FOOTPRINTS))

pytestmark = pytest.mark.anyio


def _square(item_id: str, west: float, south: float) -> dict[str, Any]:
    return {
        "id": item_id,
        "type": "Feature",
        "stac_version": "1.0.0",
        "collection": FOOTPRINTS.dataset_id,
        "bbox": [west, south, west + 1, south + 1],
        "geometry": box_area(west, south, west + 1, south + 1),
        "properties": {
            "datetime": None,
            "start_datetime": "2011-01-01T00:00:00Z",
            "end_datetime": "2014-12-31T00:00:00Z",
        },
        "assets": {},
        "links": [],
    }


@pytest.fixture
def catalogue(require_postgres_env: None) -> Iterator[None]:
    """The index of :data:`CATALOGUE`, committed so the async connection of the search sees it; removed afterwards."""
    with psycopg.connect(autocommit=True) as conn:
        write_search_index(conn, CATALOGUE)
        yield
        conn.execute("DELETE FROM public.earthx_dataset_search")


@pytest.fixture
def footprints(catalogue: None) -> Iterator[None]:
    """One item of :data:`FOOTPRINTS` in pgstac, a square from 5° to 6° E and 45° to 46° N."""
    with psycopg.connect(autocommit=True) as conn:
        use_pgstac_search_path(conn)
        load_collection(conn, FOOTPRINTS)
        upsert_items(conn, FOOTPRINTS, [_square("square", 5.0, 45.0)])
        yield
        conn.execute("SELECT pgstac.delete_collection(%s)", (FOOTPRINTS.dataset_id,))


async def _ids(aconn, text, **kwargs) -> tuple[str, ...]:
    return (await search_datasets(aconn, text, glossary=GLOSSARY, **kwargs)).ids


# --- full text and glossary --------------------------------------------------------------------------------------------


async def test_a_glossary_term_finds_its_partner_in_the_other_language(catalogue, aconn):
    # "Echtfarben" is in no text; its group holds "true color", which the time series has from `true_color`.
    assert await _ids(aconn, "Echtfarben") == ("test-series",)


async def test_a_surface_model_is_no_terrain_model(catalogue, aconn):
    # Every entry made from swissALTI3D carries its band `dtm`; only one names a surface model.
    assert await _ids(aconn, "Oberflächenmodell") == ("test-surface",)
    assert "test-surface" in await _ids(aconn, "DTM") and "test-terrain" not in await _ids(aconn, "DSM")


async def test_a_stop_word_is_no_condition(catalogue, aconn):
    assert await _ids(aconn, "Echtfarben in the alpine", joining=Joining.ALL) == ("test-series",)


@pytest.mark.parametrize(
    ("joining", "expected"),
    [
        # "glacier" is in no text: every unit fails, every known unit holds, half the units hold.
        (Joining.ALL, ()),
        (Joining.KNOWN, ("test-series",)),
        (Joining.SHARE, ("test-series",)),
    ],
)
async def test_how_the_units_are_joined(catalogue, aconn, joining, expected):
    # The trigram arm is switched off (a threshold above 1): this is about the full text alone.
    assert await _ids(aconn, "Echtfarben glacier", joining=joining, threshold=1.1) == expected


async def test_known_still_asks_for_every_known_unit(catalogue, aconn):
    assert await _ids(aconn, "savanna alpine", joining=Joining.KNOWN, threshold=1.1) == ()


async def test_trigrams_find_one_word_of_two_where_it_is_half_the_query(catalogue, aconn):
    # Known and accepted with the threshold 0.5 (plan §3.5): "savanna" is half of "savanna alpine".
    assert await _ids(aconn, "savanna alpine", joining=Joining.KNOWN) == ("test-kenya",)


async def test_a_typing_error_is_found_by_trigrams(catalogue, aconn):
    assert await _ids(aconn, "Equatr Gama") == ("test-kenya",)


async def test_a_weak_trigram_match_stays_out(catalogue, aconn):
    assert await _ids(aconn, "ocean salinity") == ()


async def test_equal_ranks_are_ordered_by_title(catalogue, aconn):
    # Four entries share "alpine" on the same weight; the title decides, the same way every time.
    first = await _ids(aconn, "alpine")
    assert first == ("test-footprints", "test-series", "test-surface", "test-terrain")
    assert await _ids(aconn, "alpine") == first


@pytest.mark.parametrize(
    "text",
    [
        "'; DROP TABLE public.earthx_dataset_search; --",
        "\\",
        "100% _alpine_",
        "a:b & c | !d <-> e",
        "(alpine",
        "\x00",
    ],
)
async def test_characters_of_sql_and_tsquery_are_plain_text(catalogue, aconn, text):
    await _ids(aconn, text)
    assert await _ids(aconn, "alpine")


@pytest.mark.parametrize("text", ["?!…", "🌍🛰️", "--"])
async def test_a_query_without_a_word_finds_nothing(catalogue, aconn, text):
    assert await _ids(aconn, text) == ()


@pytest.mark.parametrize("text", [None, "", "   \t "])
async def test_no_text_lists_every_dataset_by_id_without_a_rank(catalogue, aconn, text):
    assert await _ids(aconn, text) == tuple(sorted(c.dataset_id for c in CATALOGUE))


async def test_two_hundred_characters_are_allowed_and_one_more_is_not(catalogue, aconn):
    await _ids(aconn, "a" * MAX_QUERY_CHARS)
    with pytest.raises(QueryTooLong):
        await _ids(aconn, "a" * (MAX_QUERY_CHARS + 1))


# --- area --------------------------------------------------------------------------------------------------------------


async def test_the_area_keeps_what_its_box_meets(catalogue, aconn):
    # The time series has the global box of Sentinel-2.
    kenya = box_area(36.2, -0.8, 36.4, -0.6)
    assert await _ids(aconn, None, area=kenya) == ("test-kenya", "test-series")
    assert await _ids(aconn, "alpine", area=kenya) == ("test-series",)


async def test_a_materialized_dataset_with_items_counts_its_footprints(footprints, aconn):
    inside_box_outside_items = box_area(15.0, 48.0, 16.0, 49.0)
    assert FOOTPRINTS.dataset_id not in await _ids(aconn, "elevation", area=inside_box_outside_items)
    on_the_item = box_area(5.2, 45.2, 5.4, 45.4)
    assert FOOTPRINTS.dataset_id in await _ids(aconn, "elevation", area=on_the_item)


async def test_a_materialized_dataset_without_items_falls_back_to_its_box(catalogue, aconn):
    # Plan A4: otherwise it would vanish in every instance where its items are not loaded yet.
    assert FOOTPRINTS.dataset_id in await _ids(aconn, "elevation", area=box_area(15.0, 48.0, 16.0, 49.0))


async def test_an_area_that_is_no_geometry_is_an_error(catalogue, aconn):
    with pytest.raises(psycopg.Error):
        await _ids(aconn, "alpine", area={"type": "Polygon", "coordinates": "nothing"})


# --- period ------------------------------------------------------------------------------------------------------------


def _years(first: int, last: int) -> tuple[datetime, datetime]:
    return datetime(first, 1, 1, tzinfo=UTC), datetime(last, 12, 31, 23, 59, 59, tzinfo=UTC)


async def test_a_period_before_the_start_drops_a_time_series(catalogue, aconn):
    result = await search_datasets(aconn, "multispectral", period=_years(2000, 2005), glossary=GLOSSARY)
    assert result.ids == ()


async def test_an_open_end_means_today(catalogue, aconn):
    assert await _ids(aconn, "multispectral", period=_years(2020, 2021)) == ("test-series",)
    assert await _ids(aconn, "multispectral", period=_years(2090, 2091)) == ()
    assert await _ids(aconn, "multispectral", period=(datetime(2016, 1, 1, tzinfo=UTC), None)) == ("test-series",)


async def test_a_dataset_without_a_time_axis_stays_and_is_named(catalogue, aconn):
    result = await search_datasets(aconn, "alpine", period=_years(2000, 2005), glossary=GLOSSARY)
    assert "test-terrain" in result.ids and "test-series" not in result.ids
    assert result.ignored_filters == ("datetime",)
    assert result.ignored_filters_by_collection["test-terrain"] == ("datetime",)
    assert "test-series" not in result.ignored_filters_by_collection


async def test_without_a_period_nothing_is_ignored(catalogue, aconn):
    result = await search_datasets(aconn, "alpine", glossary=GLOSSARY)
    assert (result.ignored_filters, dict(result.ignored_filters_by_collection)) == ((), {})


# --- fusion ------------------------------------------------------------------------------------------------------------


def test_equal_scores_share_a_rank():
    assert ranks([("a", 3.0), ("b", 1.0), ("c", 1.0), ("d", 0.5)]) == {"a": 1, "b": 2, "c": 2, "d": 4}


def test_a_tie_in_one_arm_does_not_decide_the_fusion():
    # Both are 1.0 in the trigram arm; the full text puts "s2" first, so it wins whatever the titles say.
    fused = fuse({"s2": 1, "wc": 2}, ranks([("wc", 1.0), ("s2", 1.0)]), titles={"s2": "Sentinel-2", "wc": "ESA"})
    assert fused == ("s2", "wc")


def test_what_no_arm_lists_is_not_there():
    assert fuse({}, {}, titles={}) == ()

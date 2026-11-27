"""The lexical arm and its hard filters over a synthetic catalogue (M5-22 plan §3.5, §3.6, §4)."""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest
from psycopg import sql

from earthx.catalog.glossary import load_glossary, parse_query
from earthx.catalog.pgstac import load_collection, upsert_items, use_pgstac_search_path
from earthx.catalog.registry import (
    DatasetConfig,
    DatasetRegistry,
    OverviewMode,
    OverviewResampling,
    SpatialExtent,
    TemporalExtent,
)
from earthx.catalog.search import (
    AREA_FIRST_MAX,
    COUNT_UP_TO,
    DEPTH,
    MAX_QUERY_CHARS,
    MIN_SHARE,
    TEXT_FIRST_MAX,
    TIME_FILTER,
    Joining,
    Kept,
    QueryTooLong,
    Start,
    _filter_params,
    _full_text_sql,
    _start,
    box_area,
    fuse,
    names_before_numbers,
    numbered_names,
    numbers_after_names,
    numbers_of,
    ranks,
    search_datasets,
)
from earthx.catalog.search_index import write_listed_search_index, write_search_index
from tests.catalog.entries import COP_DEM_GLO_30, SENTINEL_2_L2A, SWISSALTI3D
from tests.integration.listed_rows import insert_row

GLOSSARY = load_glossary()


# swissALTI3D with a pyramid of its own: the copies below stand without the substitute the released entry names, and
# without the listing at opendata.swiss it names (`also_listed_as`), which one entry only may name.
STATIC = dataclasses.replace(
    SWISSALTI3D,
    also_listed_as=(),
    viewer=dataclasses.replace(
        SWISSALTI3D.viewer,
        overview=OverviewMode.PYRAMID,
        overview_resampling=OverviewResampling.AVERAGE,
        overview_substitute=None,
    ),
)


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
TERRAIN = _entry(STATIC, "test-terrain", "Terrain Alpha", ("digital terrain model", "alpine"))
SURFACE = _entry(STATIC, "test-surface", "Surface Beta", ("digital surface model", "alpine"))
KENYA = _entry(
    STATIC,
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


# --- numbers at a name (plan §11.7) -------------------------------------------------------------------------------------

# A mission with a number and a code with another one (like "c1" in the id of Sentinel-2), a product that names it as
# a keyword (like WorldCover names Sentinel-2) and whose own name carries no number, and a model whose number stands
# behind a hyphen ("GLO-30", which the full text splits into "glo" and "-30").
ORBITER = _entry(
    SENTINEL_2_L2A,
    "test-orbiter-2",
    "Orbiter-2 Imagery",
    ("orbiter-2", "panchromatic", "c1"),
    description="Imagery of the second orbiter, 9 bands.",
)
PRODUCT = _entry(
    SENTINEL_2_L2A, "test-product", "Landuse Zeta", ("orbiter-2", "land use"), description="Land use at 10 m."
)
MAPPER = _entry(COP_DEM_GLO_30, "test-mapper", "Mapper GLO-30", ("relief",))
NUMBERED = DatasetRegistry((ORBITER, PRODUCT, MAPPER))


@pytest.fixture
def numbered(require_postgres_env: None) -> Iterator[None]:
    with psycopg.connect(autocommit=True) as conn:
        write_search_index(conn, NUMBERED)
        yield
        conn.execute("DELETE FROM public.earthx_dataset_search")


@pytest.mark.parametrize(
    "text", ["Orbiter-3", "Orbiter 3", "orbiter3", "Orbitr 3", "Orbiter 1", "Mapper GLO-90", "Mapper 90"]
)
async def test_a_name_with_a_number_no_dataset_has_finds_nothing(numbered, aconn, text):
    assert await _ids(aconn, text) == ()


@pytest.mark.parametrize("text", ["Orbiter-2", "Orbiter 2", "orbiter2", "Orbitr 2"])
async def test_the_number_finds_the_name_and_where_it_is_a_keyword(numbered, aconn, text):
    assert set(await _ids(aconn, text)) == {"test-orbiter-2", "test-product"}


async def test_a_number_behind_a_hyphen_is_still_the_number(numbered, aconn):
    assert await _ids(aconn, "Mapper GLO 30") == ("test-mapper",)
    assert await _ids(aconn, "Mapper 30", threshold=1.1) == ("test-mapper",)


async def test_a_bare_number_carries_no_dataset(numbered, aconn):
    # "9" stands in the description of the orbiter; "Landsat" in no text.
    assert await _ids(aconn, "Landsat 9") == ()
    assert await _ids(aconn, "9", threshold=1.1) == ()


async def test_a_number_after_a_topic_still_drops_out_where_unknown(numbered, aconn):
    # "panchromatic" is a keyword, no name: "2024" is a word no text has, dropped as under Joining.KNOWN before.
    assert await _ids(aconn, "panchromatic 2024") == ("test-orbiter-2",)


@pytest.mark.parametrize("text", ["Zeta 10 m", "Zeta 10m", "Landuse 7", "Mapper 2019"])
async def test_a_unit_a_year_or_a_name_without_a_number_lets_the_number_drop_out(numbered, aconn, text):
    # Otto, 11.11.2026 (A18): "10 m" is a resolution, 2019 a year; "Landuse Zeta" carries no number of its own.
    expected = "test-mapper" if text.startswith("Mapper") else "test-product"
    assert expected in await _ids(aconn, text)


def test_only_names_that_carry_a_number_are_numbered():
    rows = [
        "test-orbiter-2 Orbiter-2 Imagery",
        "esa-worldcover-2020 ESA WorldCover 2020",
        "test-mapper Mapper GLO-30",
        "test-grid Grid 10 m",
    ]
    assert numbered_names(rows) == {"test", "orbiter", "mapper", "glo"}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Sentinel 3", ("3",)),
        ("Sentinel-3", ("3",)),
        ("Sentinel S3b", ()),
        ("Höhenmodell 2024", ()),
        ("Sentinel 2024", ()),
        ("Sentinel 10 m", ()),
        ("3 Sentinel", ()),
        ("Sentinel", ()),
    ],
)
def test_the_numbers_right_after_a_name(text, expected):
    assert numbers_after_names(text, frozenset({"sentinel"})) == expected


def test_numbers_are_words_of_digits_and_codes_are_the_digits_of_other_words():
    # A year and a number with a unit are neither.
    assert numbers_of("Sentinel-2 L2A 2020 sentinel3 10 m 20km") == (("2",), ("2", "3"))


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


def test_ranks_of_a_hundred_thousand_hits_take_well_under_a_second():
    # Listed entries bring lists of 10⁴–10⁵ hits; counting the better scores per hit took minutes there.
    scored = [(f"e{i}", float(i % 1000)) for i in range(100_000)]
    started = time.perf_counter()
    ranked = ranks(scored)
    assert time.perf_counter() - started < 1.0
    assert (ranked["e999"], ranked["e1998"], ranked["e0"]) == (1, 101, 99_901)


def test_a_tie_in_one_arm_does_not_decide_the_fusion():
    # Both are 1.0 in the trigram arm; the full text puts "s2" first, so it wins whatever the titles say.
    fused = fuse({"s2": 1, "wc": 2}, ranks([("wc", 1.0), ("s2", 1.0)]), titles={"s2": "Sentinel-2", "wc": "ESA"})
    assert fused == ("s2", "wc")


def test_what_no_arm_lists_is_not_there():
    assert fuse({}, {}, titles={}) == ()


# --- listed entries ----------------------------------------------------------------------------------------------------


@pytest.fixture
def listed(catalogue: None) -> Iterator[None]:
    """Next to :data:`CATALOGUE`: a published listed entry, a duplicate of it from another source and one in review."""
    with psycopg.connect() as conn:
        conn.execute("DELETE FROM public.earthx_listed_entry")
        insert_row(conn, "main-entry", title="Neophyten der Schweiz", bbox=(6.0, 45.8, 10.5, 47.8))
        insert_row(conn, "duplicate", state="duplicate", source_id="src-2", title="Götterbaum Standorte")
        insert_row(conn, "in-review", state="in_review", title="Baumkataster der Stadt")
        insert_row(conn, "only-regions", title="Bevölkerung der Stadt Winterthur", bbox=None, regions=("CH", "CH-ZH"))
        insert_row(conn, "no-extent", title="Bevölkerung nach Steuerklasse", bbox=None)
        write_listed_search_index(conn, [config.dataset_id for config in CATALOGUE])
        conn.commit()
        yield
        conn.execute("DELETE FROM public.earthx_listed_entry")
        conn.commit()


async def test_a_listed_entry_is_found_by_its_title_and_by_the_title_of_a_duplicate(listed, aconn):
    result = await search_datasets(aconn, "Neophyten", glossary=GLOSSARY)
    assert (result.ids, result.listed) == (("main-entry",), frozenset({"main-entry"}))
    assert await _ids(aconn, "Götterbaum") == ("main-entry",)
    assert await _ids(aconn, "Goetterbaum") == ("main-entry",)


async def test_an_entry_in_review_is_no_hit_and_no_listed_entry_is_in_a_list_without_text(listed, aconn):
    assert await _ids(aconn, "Baumkataster") == ()
    assert set(await _ids(aconn, None)) == {config.dataset_id for config in CATALOGUE}


async def test_the_area_meets_the_footprint_of_a_listed_entry(listed, aconn):
    assert await _ids(aconn, "Neophyten", area=box_area(7.0, 46.0, 7.5, 46.5)) == ("main-entry",)
    assert await _ids(aconn, "Neophyten", area=box_area(36.0, -1.0, 37.0, 0.0)) == ()


async def test_a_listed_entry_without_a_period_stays_and_is_named(listed, aconn):
    result = await search_datasets(aconn, "Neophyten", period=_years(2001, 2002), glossary=GLOSSARY)
    assert result.ids == ("main-entry",)
    assert result.ignored_filters_by_collection == {"main-entry": (TIME_FILTER,)}


def test_the_rows_of_names_before_numbers_are_asked_by_like_patterns():
    assert names_before_numbers("Landsat 9") == ["%landsat%"]
    assert names_before_numbers("Sentinel 2 and Sentinel-2") == ["%sentinel%"]
    assert names_before_numbers("10 m, 2021") == []


async def test_an_entry_without_a_footprint_is_found_by_text_and_by_the_names_of_its_regions(listed, aconn):
    assert set(await _ids(aconn, "Bevölkerung")) == {"only-regions", "no-extent"}
    assert await _ids(aconn, "Winterthur Zürich") == ("only-regions",)
    # The trigram arm also finds the other one by its strong "Bevölkerung"; the full text puts the Swiss one first.
    assert (await _ids(aconn, "Bevölkerung Schweiz"))[0] == "only-regions"


async def test_the_area_filter_never_meets_an_entry_without_a_footprint(listed, aconn):
    assert await _ids(aconn, "Bevölkerung", area=box_area(8.6, 47.4, 8.8, 47.6)) == ()
    assert await _ids(aconn, "Bevölkerung", area=box_area(-180.0, -90.0, 180.0, 90.0)) == ()


# --- the area before the text (M5-65) ---------------------------------------------------------------------------------


async def test_an_entry_whose_link_failed_the_check_since_the_last_load_is_no_hit_by_text_or_by_area(listed, aconn):
    # `catalog-load` wrote the row of "main-entry" while it was published; the link check hides it between two loads.
    await aconn.execute("UPDATE public.earthx_listed_entry SET state = 'link_hidden' WHERE dataset_id = 'main-entry'")
    over_it = box_area(7.0, 46.0, 7.5, 46.5)
    assert await _ids(aconn, "Neophyten", area=over_it) == ()
    assert await _ids(aconn, "Neophyten") == ()
    assert await _ids(aconn, "Neophyten Götterbaum Schweiz", area=over_it) == ()
    assert "main-entry" not in await _ids(aconn, None, area=over_it)
    await aconn.execute("UPDATE public.earthx_listed_entry SET state = 'published' WHERE dataset_id = 'main-entry'")
    assert await _ids(aconn, "Neophyten", area=over_it) == ("main-entry",)


async def test_an_area_without_text_meets_the_full_entries_by_their_box(catalogue, aconn):
    assert await _ids(aconn, None, area=box_area(36.2, -0.8, 36.4, -0.6)) == ("test-kenya", "test-series")
    assert await _ids(aconn, None, area=box_area(-60.0, -60.0, -59.0, -59.0)) == ("test-series",)


def test_the_envelope_of_a_full_row_is_computed_from_its_box_and_a_listed_row_has_none(listed, conn):
    conn.execute("UPDATE public.earthx_dataset_search SET west = 30.0 WHERE dataset_id = 'test-kenya'")
    rows = dict(
        conn.execute(
            "SELECT dataset_id, ST_AsText(geometry) FROM public.earthx_dataset_search"
            " WHERE dataset_id IN ('test-kenya', 'main-entry')"
        ).fetchall()
    )
    assert rows["test-kenya"] == "POLYGON((30 -1,30 0,37 0,37 -1,30 -1))"
    assert rows["main-entry"] is None


#: A search that starts from the area whatever the text (no text has "at most -1" hits) and one that starts from the text
#: whatever the area (no area keeps "at most -1" entries).
FROM_THE_AREA = {"area_first_max": 10**9, "text_first_max": -1}
FROM_THE_TEXT = {"area_first_max": -1}


async def _plan(aconn, statement, params) -> str:
    async with aconn.cursor() as cur:
        await cur.execute(sql.SQL("EXPLAIN (COSTS OFF) ") + statement, params, prepare=False)
        return "\n".join(row[0] for row in await cur.fetchall())


def _full_text_statement(start: Start, area: dict | None = None, text: str = "Neophyten"):
    units = parse_query(text, GLOSSARY)
    terms = {f"term_{n}_{i}": term for n, unit in enumerate(units) for i, term in enumerate(unit.terms)}
    params = {
        **_filter_params(area, None),
        **terms,
        "share": MIN_SHARE,
        "named_numbers": [],
        "depth": DEPTH,
        "count_up_to": COUNT_UP_TO,
    }
    return _full_text_sql(units, Joining.KNOWN, start=start, named_numbers=False), params


@pytest.mark.parametrize("start", list(Start))
async def test_the_statement_has_a_condition_on_the_area_only_where_there_is_one(listed, aconn, start):
    statement, _ = _full_text_statement(start)
    assert ("%(area)s" in statement.as_string(aconn)) == (start is not Start.NO_AREA)


async def test_the_ranks_of_the_units_of_a_hit_are_summed_in_the_order_of_the_units(listed, aconn):
    # Without it the sum of `real` values, and with it which hits tie, would depend on the plan.
    # M5-66: with more than one unit the ranks are summed when the rows the joining keeps are read again; with one
    # there is nothing to sum.
    statement, _ = _full_text_statement(Start.NO_AREA, text="Neophyten Kanton")
    assert "sum(ts_rank_cd(s.document, u.query) ORDER BY u.ord)" in statement.as_string(aconn)
    statement, _ = _full_text_statement(Start.NO_AREA)
    assert "sum(" not in statement.as_string(aconn)


#: 60 × 60 listed entries, each half a degree wide on a grid of whole degrees, all with "Alpha" in the title.
_GRID = """
    INSERT INTO public.earthx_listed_entry (
        dataset_id, source_id, source_key, state, content, content_sha256, sort_title, footprint, regions, keywords,
        data_kind, category, account, delivery, publisher, link_host)
    SELECT 'grid-' || g, 'grid', 'grid-' || g, 'published',
           jsonb_build_object('type', 'Collection', 'id', 'grid-' || g, 'title', 'Alpha grid ' || g,
                              'earthx:entry', 'listed'),
           md5(g::text) || md5(g::text), 'alpha grid ' || g,
           ST_MakeEnvelope((g % 60) - 30, (g / 60) - 30, (g % 60) - 29.5, (g / 60) - 29.5, 4326), '{}', '{grid}',
           'vector', 'other', 'none', 'download', 'Grid Office', 'grid.example.org'
    FROM generate_series(0, 3599) g
"""
ONE_CELL = box_area(10.1, 20.1, 10.2, 20.2)


@pytest.fixture
def grid(catalogue: None) -> Iterator[None]:
    with psycopg.connect() as conn:
        conn.execute("DELETE FROM public.earthx_listed_entry")
        conn.execute(_GRID)
        write_listed_search_index(conn, [config.dataset_id for config in CATALOGUE])
        conn.execute("ANALYZE public.earthx_listed_entry")
        conn.execute("ANALYZE public.earthx_dataset_search")
        conn.commit()
        yield
        conn.execute("DELETE FROM public.earthx_listed_entry")
        conn.commit()


def _cell_id(west: int, south: int) -> str:
    return f"grid-{(south + 30) * 60 + west + 30}"


async def _grid_ids(aconn, area=None, **kwargs) -> list[str]:
    """The grid entries "Alpha" finds, in rank order; the trigram arm also finds "alpine" of a full entry."""
    return [i for i in await _ids(aconn, "Alpha", area=area, **kwargs) if i.startswith("grid-")]


async def _start_of(aconn, text, area, **limits) -> Start:
    units = parse_query(text, GLOSSARY)
    terms = {f"term_{n}_{i}": term for n, unit in enumerate(units) for i, term in enumerate(unit.terms)}
    params = _filter_params(area, None)
    return await _start(
        aconn,
        params,
        units,
        terms,
        limits.get("area_first_max", AREA_FIRST_MAX),
        limits.get("text_first_max", TEXT_FIRST_MAX),
    )


async def test_a_text_with_many_hits_over_a_small_area_starts_from_the_area(grid, aconn):
    # 3 601 hits for "Alpha" (the grid and "Terrain Alpha"), one entry in the area.
    assert await _start_of(aconn, "Alpha", ONE_CELL) is Start.AREA


async def test_a_text_with_few_hits_starts_from_the_text_whatever_the_area(grid, aconn):
    assert await _start_of(aconn, "Alpha", ONE_CELL, text_first_max=3601) is Start.TEXT
    assert await _start_of(aconn, "Alpha", ONE_CELL, text_first_max=3600) is Start.AREA
    assert await _start_of(aconn, "Neophyten", ONE_CELL) is Start.TEXT
    assert await _start_of(aconn, "in der", ONE_CELL) is Start.TEXT  # nothing but stop words


async def test_an_area_over_many_entries_starts_from_the_text(grid, aconn):
    everywhere = box_area(-31.0, -31.0, 31.0, 31.0)
    assert await _start_of(aconn, "Alpha", everywhere, area_first_max=3599) is Start.TEXT
    assert await _start_of(aconn, "Alpha", everywhere, area_first_max=3600) is Start.AREA
    assert await _start_of(aconn, "Alpha", None) is Start.NO_AREA


async def test_starting_from_the_area_reads_the_footprint_index_and_looks_each_entry_up_by_its_id(grid, aconn):
    statement, params = _full_text_statement(Start.AREA, ONE_CELL, "Alpha")
    plan = await _plan(aconn, statement, params)
    assert "earthx_listed_entry_footprint_idx" in plan and "earthx_dataset_search_id_c_idx" in plan


async def test_both_starts_find_the_same_with_an_area_that_keeps_one_or_many(grid, aconn):
    many = box_area(0.2, 0.2, 2.2, 1.2)
    for area, expected in (
        (ONE_CELL, {_cell_id(10, 20)}),
        (many, {_cell_id(west, south) for west in range(0, 3) for south in range(0, 2)}),
    ):
        by_area = await _grid_ids(aconn, area, **FROM_THE_AREA)
        assert set(by_area) == expected
        assert by_area == await _grid_ids(aconn, area, **FROM_THE_TEXT)


async def test_both_starts_rank_alike(listed, aconn):
    area = box_area(7.0, 46.0, 7.5, 46.5)
    for text in ("Neophyten", "Bevölkerung Schweiz", "Götterbaum Neophyten Sentinel", "alpine"):
        by_area = await search_datasets(aconn, text, area=area, glossary=GLOSSARY, **FROM_THE_AREA)
        by_text = await search_datasets(aconn, text, area=area, glossary=GLOSSARY, **FROM_THE_TEXT)
        assert by_area == by_text, text


async def test_a_period_with_an_area_keeps_the_same_hits_and_names_the_same_ignored_filter_from_either_start(
    listed, aconn
):
    area = box_area(7.0, 46.0, 7.5, 46.5)
    for text in ("Neophyten", "alpine"):
        found = [
            await search_datasets(aconn, text, area=area, period=_years(2001, 2002), glossary=GLOSSARY, **limits)
            for limits in (FROM_THE_AREA, FROM_THE_TEXT)
        ]
        assert found[0] == found[1], text
    listed_result = await search_datasets(
        aconn, "Neophyten", area=area, period=_years(2001, 2002), glossary=GLOSSARY, **FROM_THE_AREA
    )
    assert listed_result.ids == ("main-entry",)
    assert listed_result.ignored_filters_by_collection == {"main-entry": (TIME_FILTER,)}


async def test_no_start_lets_an_entry_with_a_hidden_link_through(listed, aconn):
    await aconn.execute("UPDATE public.earthx_listed_entry SET state = 'link_hidden' WHERE dataset_id = 'main-entry'")
    over_it = box_area(7.0, 46.0, 7.5, 46.5)
    for limits in (FROM_THE_AREA, FROM_THE_TEXT):
        assert await _ids(aconn, "Neophyten", area=over_it, **limits) == ()
        assert "main-entry" not in await _ids(aconn, "Neophyten Götterbaum Schweiz", area=over_it, **limits)


# --- M5-66: filters of the Data catalogue in the statements, depth per arm, number of hits -----------------------------

#: Two regions of invented codes, so that no outline of `regions.json` a load wrote is touched: one over the box of the
#: static rasters, one over Kenya.
_REGIONS = {"ZZ": (5.0, 45.0, 11.0, 48.5), "ZY": (35.0, -2.0, 38.0, 1.0)}


@pytest.fixture
def kept(listed: None) -> Iterator[None]:
    """:func:`listed` with categories and regions of the listed rows, and the two regions of :data:`_REGIONS`."""
    with psycopg.connect(autocommit=True) as conn:
        for code, box in _REGIONS.items():
            conn.execute(
                "INSERT INTO public.earthx_region (code, level, name, outline) VALUES"
                " (%s, 'state', %s, ST_Multi(ST_MakeEnvelope(%s, %s, %s, %s, 4326)))",
                (code, code, *box),
            )
            conn.execute(
                "INSERT INTO public.earthx_region_part (code, part) SELECT code, outline FROM"
                " public.earthx_region WHERE code = %s",
                (code,),
            )
        conn.execute(
            "UPDATE public.earthx_listed_entry SET category = 'population', regions = '{ZZ}'"
            " WHERE dataset_id = 'only-regions'"
        )
        conn.execute("UPDATE public.earthx_listed_entry SET regions = '{ZY}' WHERE dataset_id = 'no-extent'")
        yield
        conn.execute("DELETE FROM public.earthx_region WHERE code = ANY(%s)", (list(_REGIONS),))


async def test_the_filters_of_the_catalogue_keep_the_listed_hits_in_the_statements(kept, aconn):
    both = {"only-regions", "no-extent"}
    assert set(await _ids(aconn, "Bevölkerung")) == both
    assert await _ids(aconn, "Bevölkerung", kept=Kept(category="population")) == ("only-regions",)
    assert await _ids(aconn, "Bevölkerung", kept=Kept(category="water")) == ()
    assert await _ids(aconn, "Bevölkerung", kept=Kept(regions=("ZY",))) == ("no-extent",)
    assert set(await _ids(aconn, "Bevölkerung", kept=Kept(regions=("ZY", "ZZ")))) == both
    assert await _ids(aconn, "Bevölkerung", kept=Kept(regions=("XX",))) == ()
    assert await _ids(aconn, "Bevölkerung", kept=Kept(entry="full")) == ()
    assert set(await _ids(aconn, "Bevölkerung", kept=Kept(entry="listed"))) == both


async def test_a_full_entry_is_kept_by_the_ids_of_its_category_and_by_the_regions_its_box_overlaps(kept, aconn):
    alpine = {"test-terrain", "test-surface", "test-series", "test-footprints"}
    assert set(await _ids(aconn, "alpine")) == alpine
    assert await _ids(aconn, "alpine", kept=Kept(full_ids=["test-terrain", "test-kenya"])) == ("test-terrain",)
    assert await _ids(aconn, "alpine", kept=Kept(full_ids=[])) == ()
    # The time series has the box of Sentinel-2, the whole earth: it overlaps Kenya too.
    assert await _ids(aconn, "alpine", kept=Kept(regions=("ZY",))) == ("test-series",)
    assert set(await _ids(aconn, "alpine", kept=Kept(regions=("ZZ",)))) == alpine
    assert await _ids(aconn, "savanna", kept=Kept(regions=("ZY",))) == ("test-kenya",)
    assert await _ids(aconn, "savanna", kept=Kept(regions=("ZZ",))) == ()
    assert await _ids(aconn, "savanna", kept=Kept(entry="listed")) == ()
    # A listed category keeps no full entry out on its own: the caller names the full ids of the category.
    assert await _ids(aconn, "savanna", kept=Kept(category="population")) == ("test-kenya",)


async def test_the_filters_keep_the_same_hits_in_the_same_order_from_either_start(kept, aconn):
    area = box_area(6.0, 45.0, 11.0, 49.0)
    for text in ("Bevölkerung", "Neophyten Schweiz", "alpine"):
        for filters in (Kept(regions=("ZZ",)), Kept(category="other", full_ids=["test-terrain"]), Kept(entry="listed")):
            by_area = await search_datasets(aconn, text, area=area, glossary=GLOSSARY, kept=filters, **FROM_THE_AREA)
            by_text = await search_datasets(aconn, text, area=area, glossary=GLOSSARY, kept=filters, **FROM_THE_TEXT)
            assert by_area == by_text, (text, filters)


#: Listed entries whose titles hold "Kappa" one to five times: five distinct ranks in the full text, one similarity.
_KAPPA = {f"kappa-{n}": " ".join(["Kappa"] * n) + " Liste" for n in range(1, 6)}


@pytest.fixture
def kappa(catalogue: None) -> Iterator[None]:
    with psycopg.connect() as conn:
        conn.execute("DELETE FROM public.earthx_listed_entry")
        for dataset_id, title in _KAPPA.items():
            insert_row(conn, dataset_id, title=title)
        write_listed_search_index(conn, [config.dataset_id for config in CATALOGUE])
        conn.commit()
        yield
        conn.execute("DELETE FROM public.earthx_listed_entry")
        conn.commit()


async def test_only_the_places_up_to_the_depth_of_an_arm_go_into_the_fusion(kappa, aconn):
    full_text_only = {"threshold": 1.1}
    everything = await search_datasets(aconn, "Kappa", glossary=GLOSSARY, **full_text_only)
    assert everything.ids == tuple(f"kappa-{n}" for n in range(5, 0, -1))
    cut = await search_datasets(aconn, "Kappa", glossary=GLOSSARY, depth=2, **full_text_only)
    assert cut.ids == ("kappa-5", "kappa-4")
    # Every hit still counts.
    assert (everything.matched, cut.matched) == (5, 5)


async def test_a_tie_at_the_depth_is_never_cut(kappa, aconn):
    # The trigram arm gives each "Kappa" title the same similarity: one tie, taken whole at depth 1, so that the fusion
    # is the one without a depth.
    assert await _ids(aconn, "Kappa", depth=1) == await _ids(aconn, "Kappa")
    trigrams_only = await search_datasets(aconn, "Kappa", glossary=GLOSSARY, depth=1, joining=Joining.ALL)
    assert set(trigrams_only.ids) == set(_KAPPA)


async def test_the_grid_ranks_alike_at_any_depth(grid, aconn):
    assert await _grid_ids(aconn, depth=1) == await _grid_ids(aconn)


async def test_the_number_of_hits_is_exact_up_to_the_limit_and_none_above(kappa, aconn):
    assert (await search_datasets(aconn, "Kappa", glossary=GLOSSARY, count_up_to=5)).matched == 5
    assert (await search_datasets(aconn, "Kappa", glossary=GLOSSARY, count_up_to=4)).matched is None
    # Above the limit it stays None also where the depth cuts the arms down below it.
    assert (await search_datasets(aconn, "Kappa", glossary=GLOSSARY, count_up_to=4, depth=1)).matched is None
    assert (await search_datasets(aconn, "Kappa", glossary=GLOSSARY, kept=Kept(entry="full"))).matched == 0
    assert (await search_datasets(aconn, "nothing like it", glossary=GLOSSARY)).matched == 0


async def test_a_hit_of_both_arms_counts_once(listed, aconn):
    # "Neophyten" is in the title (full text) and in the trigram text of the one entry.
    assert (await search_datasets(aconn, "Neophyten", glossary=GLOSSARY)).matched == 1


async def test_without_text_the_number_is_that_of_the_list(listed, aconn):
    result = await search_datasets(aconn, None, glossary=GLOSSARY)
    assert result.matched == len(result.ids) == len(CATALOGUE)


async def test_several_units_rank_as_the_sum_of_their_ranks_in_the_order_of_the_units(kappa, aconn):
    # "Kappa Liste": every title has both words; the order is that of "Kappa" alone, the ranks of "Liste" being equal.
    assert await _ids(aconn, "Kappa Liste", threshold=1.1) == await _ids(aconn, "Kappa", threshold=1.1)
    assert await _ids(aconn, "Kappa Liste", threshold=1.1, depth=1) == ("kappa-5",)

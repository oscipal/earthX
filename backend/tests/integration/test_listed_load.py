"""T-C: ``catalog-load`` writes listed entries, regions and tombstones into Postgres (M5-40 plan §5.1, §5.3, §5.4, §5.8).

The writers of ``earthx.catalog.listed_store`` are called directly on the rolled-back ``conn`` of the tests, with
synthetic entries (invented ids, titles and hosts under ``example.org``); nothing is committed and nothing goes out.
The tables and their ``CHECK`` constraints are the real ones of migration ``021``; inserting around the writers shows
what the database itself refuses. ``ctid`` tells whether a row was rewritten: an update always makes a new row version.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import dict_row

from earthx.catalog.listed import (
    HAND_SOURCE,
    BlockReason,
    BlockRule,
    BlockScope,
    DeliveryKind,
    ListedAccess,
    ListedEntry,
    Region,
    load_listed,
    load_regions,
)
from earthx.catalog.listed_store import apply_blocklist, supersede, write_hand_entries, write_regions
from earthx.catalog.registry import AccountKind, ConfigError, SpatialExtent, TemporalExtent
from tests.catalog.listed_entries import PUBLISHER, listed_entry, utc, with_hash
from tests.integration.listed_rows import insert_row

BLOCKED_ON = date(2026, 11, 1)
#: The 27 EU members, the five other members and the six cooperating countries of the EEA, and the UK (CLC 2018).
EEA_39 = frozenset(
    "AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE "
    "IS LI NO CH TR AL BA ME MK RS XK GB".split()
)
CONTENT_COLUMNS = (
    "content",
    "content_sha256",
    "sort_title",
    "footprint",
    "time_span",
    "regions",
    "keywords",
    "data_kind",
    "category",
    "account",
    "delivery",
    "publisher",
    "link_host",
    "license_ref",
)


def _row(conn: psycopg.Connection, dataset_id: str) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT *, ctid::text AS tid FROM public.earthx_listed_entry WHERE dataset_id = %s", (dataset_id,))
        return cur.fetchone()


def _state(conn: psycopg.Connection, dataset_id: str) -> str | None:
    row = _row(conn, dataset_id)
    return None if row is None else row["state"]


def _tids(conn: psycopg.Connection) -> dict[str, str]:
    return dict(conn.execute("SELECT dataset_id, ctid::text FROM public.earthx_listed_entry").fetchall())


def _today(conn: psycopg.Connection) -> date:
    return conn.execute("SELECT current_date").fetchone()[0]


def _put(conn: psycopg.Connection, tmp_path: Path, *entries: ListedEntry, blocklist=(), full_ids=()):
    pairs = [with_hash(entry, tmp_path) for entry in entries]
    return write_hand_entries(conn, pairs, list(blocklist), full_ids=full_ids)


def _block(scope: BlockScope, reason: BlockReason = BlockReason.LEGAL, **fields: str) -> BlockRule:
    return BlockRule(scope=scope, reason=reason, blocked_on=BLOCKED_ON, **fields)


def _four(tmp_path: Path) -> tuple[ListedEntry, ...]:
    """Two publishers and two hosts, crossed: what each scope of the blocklist has to tell apart."""
    return (
        listed_entry("example-a", publisher="Publisher One", source_url="https://one.example.org/a"),
        listed_entry("example-b", publisher="Publisher One", source_url="https://two.example.org/b"),
        listed_entry("example-c", publisher="Publisher Two", source_url="https://one.example.org/c"),
        listed_entry("example-d", publisher="Publisher Two", source_url="https://three.example.org/d"),
    )


# --- a hand entry in the table ---------------------------------------------------------------------------------------


def test_a_hand_entry_is_written_with_its_provenance(conn: psycopg.Connection, tmp_path: Path) -> None:
    entry = listed_entry("example-atlas", access=ListedAccess(AccountKind.PAID, "example-shop", DeliveryKind.ORDER))
    pair = with_hash(entry, tmp_path)
    written, blocked = write_hand_entries(conn, [pair], [], full_ids=[])
    assert (written, blocked) == (("example-atlas",), ())
    row = _row(conn, "example-atlas")
    assert (row["source_id"], row["source_key"], row["state"]) == (HAND_SOURCE, "example-atlas", "published")
    assert (row["approval_file"], row["approval_sha256"], row["approved_on"]) == (
        "listed/example-atlas.yaml",
        pair[1],
        entry.approved_on,
    )
    assert (row["license_rule"], row["run_id"], row["removed_reason"], row["removed_on"]) == (None, None, None, None)
    assert (row["data_kind"], row["account"], row["delivery"]) == ("raster", "paid", "order")
    assert (row["publisher"], row["link_host"], row["sort_title"]) == (PUBLISHER, "data.example.org", "example atlas")
    assert row["content"]["id"] == "example-atlas" and row["content"]["earthx:entry"] == "listed"
    assert "earthx:regions" not in row["content"]  # derived on the way out, so a new outline needs no rewrite
    assert row["published_at"] is not None


def test_the_period_is_a_range_with_open_ends_or_none(conn: psycopg.Connection, tmp_path: Path) -> None:
    _put(
        conn,
        tmp_path,
        listed_entry("example-closed"),
        listed_entry("example-open", temporal_extent=TemporalExtent(utc(2015), None)),
        listed_entry("example-since", temporal_extent=TemporalExtent(None, utc(2015))),
        listed_entry("example-none", temporal_extent=TemporalExtent(None, None)),
    )
    rows = {
        row[0]: row[1:]
        for row in conn.execute(
            "SELECT dataset_id, time_span IS NULL, lower(time_span), upper(time_span), lower_inf(time_span), "
            "upper_inf(time_span) FROM public.earthx_listed_entry"
        ).fetchall()
    }
    assert rows["example-none"][0] is True
    assert rows["example-closed"] == (False, utc(2000), utc(2020, 12, 31), False, False)
    assert rows["example-open"] == (False, utc(2015), None, False, True)
    assert rows["example-since"] == (False, None, utc(2015), True, False)


def test_a_changed_entry_is_rewritten_and_the_unchanged_one_is_not(conn: psycopg.Connection, tmp_path: Path) -> None:
    first, other = listed_entry("example-atlas"), listed_entry("example-other", title="Example other")
    _put(conn, tmp_path, first, other)
    before = _tids(conn)
    written, _ = _put(conn, tmp_path, replace(first, title="Example atlas, second edition"), other)
    assert written == ("example-atlas",)
    after = _tids(conn)
    assert after["example-other"] == before["example-other"] and after["example-atlas"] != before["example-atlas"]
    assert _row(conn, "example-atlas")["sort_title"] == "example atlas second edition"


def test_a_new_hash_of_the_file_alone_rewrites_the_row(conn: psycopg.Connection, tmp_path: Path) -> None:
    entry = listed_entry("example-atlas")
    write_hand_entries(conn, [(entry, "a" * 64)], [], full_ids=[])
    assert write_hand_entries(conn, [(entry, "a" * 64)], [], full_ids=[]) == ((), ())
    assert write_hand_entries(conn, [(entry, "b" * 64)], [], full_ids=[]) == (("example-atlas",), ())
    assert _row(conn, "example-atlas")["approval_sha256"] == "b" * 64


# --- idempotence -----------------------------------------------------------------------------------------------------


def test_a_second_run_writes_nothing(conn: psycopg.Connection, tmp_path: Path) -> None:
    regions = load_regions()
    entries = _four(tmp_path) + (listed_entry("example-gone", title="Gone soon"),)
    rule = _block(BlockScope.ENTRY, source_id=HAND_SOURCE, source_key="example-gone")

    def run() -> tuple:
        changed = write_regions(conn, regions)
        written, blocked = _put(conn, tmp_path, *entries[:4], blocklist=[rule], full_ids=["full-1"])
        return changed, written, blocked, supersede(conn, ["full-1"]), apply_blocklist(conn, [rule])

    first = run()
    assert first[1] == tuple(entry.dataset_id for entry in entries[:4])
    before = _tids(conn)
    assert run() == (0, (), (), (), 0)
    assert _tids(conn) == before


def test_a_second_run_leaves_a_tombstone_and_a_superseded_row_as_they_are(
    conn: psycopg.Connection, tmp_path: Path
) -> None:
    kept, gone = listed_entry("example-kept"), listed_entry("example-gone", title="Gone")
    _put(conn, tmp_path, kept, gone)
    insert_row(conn, "harvested-1")
    supersede(conn, ["harvested-1"])
    _put(conn, tmp_path, kept)
    before = {key: (_row(conn, key)["tid"], _row(conn, key)["state"]) for key in ("example-gone", "harvested-1")}
    assert _put(conn, tmp_path, kept) == ((), ())
    assert {key: (_row(conn, key)["tid"], _row(conn, key)["state"]) for key in before} == before
    assert before["example-gone"][1] == "tombstone" and before["harvested-1"][1] == "superseded"


def test_regions_written_twice_change_nothing_the_second_time(conn: psycopg.Connection) -> None:
    regions = load_regions()
    write_regions(conn, regions)
    assert write_regions(conn, regions) == 0
    assert conn.execute("SELECT count(*) FROM public.earthx_region").fetchone()[0] == len(regions)


# --- regions ---------------------------------------------------------------------------------------------------------


def _regions_of(conn: psycopg.Connection, dataset_id: str) -> list[str]:
    return _row(conn, dataset_id)["regions"]


def test_a_box_inside_bavaria_gets_the_state_and_the_subdivision(conn: psycopg.Connection, tmp_path: Path) -> None:
    write_regions(conn, load_regions())
    _put(conn, tmp_path, listed_entry("example-munich", spatial_extent=_box(11.2, 48.2, 11.6, 48.4)))
    assert _regions_of(conn, "example-munich") == ["DE", "DE-BY"]


def test_a_box_over_the_border_of_germany_and_austria_gets_both(conn: psycopg.Connection, tmp_path: Path) -> None:
    write_regions(conn, load_regions())
    _put(conn, tmp_path, listed_entry("example-border", spatial_extent=_box(12.8, 47.6, 13.2, 47.9)))
    regions = _regions_of(conn, "example-border")
    assert {"DE", "AT", "DE-BY"} <= set(regions)
    assert regions == sorted(regions)


def test_a_box_in_the_open_sea_has_no_region_and_not_a_null(conn: psycopg.Connection, tmp_path: Path) -> None:
    write_regions(conn, load_regions())
    _put(conn, tmp_path, listed_entry("example-sea", spatial_extent=_box(-30.0, -10.0, -29.0, -9.0)))
    assert _regions_of(conn, "example-sea") == []


def test_without_outlines_in_the_table_an_entry_has_no_regions(conn: psycopg.Connection, tmp_path: Path) -> None:
    write_regions(conn, [])
    _put(conn, tmp_path, listed_entry("example-munich", spatial_extent=_box(11.2, 48.2, 11.6, 48.4)))
    assert _regions_of(conn, "example-munich") == []


def _square(west: float, south: float, east: float, north: float) -> dict:
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    return {"type": "Polygon", "coordinates": [ring]}


def _box(west: float, south: float, east: float, north: float) -> SpatialExtent:
    return SpatialExtent(bbox=(west, south, east, north))


def test_a_region_that_only_shares_a_border_with_the_box_does_not_count(
    conn: psycopg.Connection, tmp_path: Path
) -> None:
    # Two squares side by side; the box lies in the left one and its east edge is the border to the right one.
    write_regions(
        conn,
        [
            Region("XA", "state", "Land A", _square(0.0, 0.0, 1.0, 1.0)),
            Region("XB", "state", "Land B", _square(1.0, 0.0, 2.0, 1.0)),
        ],
    )
    _put(conn, tmp_path, listed_entry("example-edge", spatial_extent=_box(0.5, 0.2, 1.0, 0.8)))
    assert _regions_of(conn, "example-edge") == ["XA"]


def test_a_changed_outline_derives_the_regions_of_every_entry_anew(conn: psycopg.Connection, tmp_path: Path) -> None:
    left = Region("XA", "state", "Land A", _square(0.0, 0.0, 1.0, 1.0))
    write_regions(conn, [left])
    _put(conn, tmp_path, listed_entry("example-in", spatial_extent=_box(0.2, 0.2, 0.4, 0.4)))
    assert _regions_of(conn, "example-in") == ["XA"]
    moved = Region("XA", "state", "Land A", _square(5.0, 5.0, 6.0, 6.0))
    assert write_regions(conn, [moved]) == 1
    assert _regions_of(conn, "example-in") == []
    assert write_regions(conn, [moved, Region("XC", "state", "Land C", _square(0.0, 0.0, 1.0, 1.0))]) == 1
    assert _regions_of(conn, "example-in") == ["XC"]


def test_a_region_that_left_the_file_leaves_the_table(conn: psycopg.Connection) -> None:
    write_regions(
        conn, [Region("XA", "state", "Land A", _square(0, 0, 1, 1)), Region("XB", "state", "B", _square(2, 2, 3, 3))]
    )
    assert write_regions(conn, [Region("XA", "state", "Land A", _square(0, 0, 1, 1))]) == 1
    assert [code for (code,) in conn.execute("SELECT code FROM public.earthx_region").fetchall()] == ["XA"]


def test_a_renamed_region_is_one_changed_row(conn: psycopg.Connection) -> None:
    write_regions(conn, [Region("XA", "state", "Land A", _square(0, 0, 1, 1))])
    assert write_regions(conn, [Region("XA", "state", "Land A, renamed", _square(0, 0, 1, 1))]) == 1
    assert conn.execute("SELECT name FROM public.earthx_region WHERE code = 'XA'").fetchone()[0] == "Land A, renamed"


def _parts(conn: psycopg.Connection) -> dict[str, int]:
    return dict(conn.execute("SELECT code, count(*) FROM public.earthx_region_part GROUP BY code").fetchall())


def test_the_outlines_are_cut_into_parts_that_cover_them(conn: psycopg.Connection) -> None:
    write_regions(conn, load_regions())
    parts = _parts(conn)
    assert set(parts) == {region.code for region in load_regions()}
    assert parts["DE"] > 1  # a large outline is cut into small pieces
    area_difference = conn.execute(
        "SELECT max(ST_Area(ST_SymDifference(r.outline, p.merged))) FROM public.earthx_region r JOIN "
        "(SELECT code, ST_Union(part) AS merged FROM public.earthx_region_part GROUP BY code) p USING (code) "
        "WHERE r.code IN ('DE', 'DE-BY', 'AT', 'LI')"
    ).fetchone()[0]
    assert area_difference < 1e-9


def test_the_parts_are_written_once_and_rewritten_only_where_an_outline_changed(conn: psycopg.Connection) -> None:
    regions = load_regions()
    write_regions(conn, regions)
    before = dict(conn.execute("SELECT ctid::text, code FROM public.earthx_region_part").fetchall())
    assert write_regions(conn, regions) == 0
    assert dict(conn.execute("SELECT ctid::text, code FROM public.earthx_region_part").fetchall()) == before


def test_a_region_that_left_the_file_takes_its_parts_with_it(conn: psycopg.Connection) -> None:
    write_regions(
        conn, [Region("XA", "state", "A", _square(0, 0, 1, 1)), Region("XB", "state", "B", _square(2, 2, 3, 3))]
    )
    assert set(_parts(conn)) == {"XA", "XB"}
    write_regions(conn, [Region("XA", "state", "A", _square(0, 0, 1, 1))])
    assert set(_parts(conn)) == {"XA"}


def test_a_changed_outline_has_new_parts(conn: psycopg.Connection) -> None:
    write_regions(conn, [Region("XA", "state", "A", _square(0, 0, 1, 1))])
    write_regions(conn, [Region("XA", "state", "A", _square(5, 5, 6, 6))])
    assert conn.execute("SELECT ST_XMin(ST_Extent(part)) FROM public.earthx_region_part").fetchone()[0] == 5.0


def test_a_part_cannot_name_a_region_that_does_not_exist(conn: psycopg.Connection) -> None:
    _refused(
        conn,
        "INSERT INTO public.earthx_region_part (code, part) VALUES ('XZ', ST_MakeEnvelope(0, 0, 1, 1, 4326))",
        {},
        psycopg.errors.ForeignKeyViolation,
    )


def test_a_box_touching_only_the_cut_between_two_parts_of_one_outline_still_gets_the_region(
    conn: psycopg.Connection, tmp_path: Path
) -> None:
    # A square of many points is cut by ST_Subdivide; a box inside it must get the region wherever the cuts run.
    ring = [[i / 100, 0.0] for i in range(0, 101)] + [[1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]
    write_regions(conn, [Region("XA", "state", "A", {"type": "Polygon", "coordinates": [ring]})])
    for index, west in enumerate((0.1, 0.25, 0.5, 0.74, 0.9)):
        _put(conn, tmp_path, listed_entry(f"example-in-{index}", spatial_extent=_box(west, 0.2, west + 0.05, 0.4)))
        assert _regions_of(conn, f"example-in-{index}") == ["XA"]


def test_a_tombstone_has_no_regions_to_derive(conn: psycopg.Connection, tmp_path: Path) -> None:
    _put(conn, tmp_path, listed_entry("example-atlas"))
    apply_blocklist(conn, [_block(BlockScope.SOURCE, source_id=HAND_SOURCE)])
    write_regions(conn, [Region("XA", "state", "Land A", _square(0, 0, 1, 1))])
    assert _row(conn, "example-atlas")["regions"] is None


# --- tombstones by the blocklist -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rule", "hit"),
    [
        (_block(BlockScope.ENTRY, source_id=HAND_SOURCE, source_key="example-a"), {"example-a"}),
        (_block(BlockScope.PUBLISHER, source_id=HAND_SOURCE, publisher="Publisher One"), {"example-a", "example-b"}),
        (_block(BlockScope.HOST, host="one.example.org"), {"example-a", "example-c"}),
        (_block(BlockScope.SOURCE, source_id=HAND_SOURCE), {"example-a", "example-b", "example-c", "example-d"}),
    ],
    ids=["entry", "publisher", "host", "source"],
)
def test_a_line_makes_a_tombstone_of_exactly_what_its_scope_names(
    conn: psycopg.Connection, tmp_path: Path, rule: BlockRule, hit: set[str]
) -> None:
    _put(conn, tmp_path, *_four(tmp_path))
    assert apply_blocklist(conn, [rule]) == len(hit)
    for dataset_id in ("example-a", "example-b", "example-c", "example-d"):
        assert (_state(conn, dataset_id) == "tombstone") == (dataset_id in hit)
    for dataset_id in hit:
        row = _row(conn, dataset_id)
        assert (row["removed_reason"], row["removed_on"]) == ("legal", BLOCKED_ON)
        assert [column for column in CONTENT_COLUMNS if row[column] is not None] == []
        assert (row["source_id"], row["source_key"]) == (HAND_SOURCE, dataset_id)
    assert apply_blocklist(conn, [rule]) == 0  # a tombstone is not turned into one again


@pytest.mark.parametrize("reason", list(BlockReason))
def test_the_tombstone_keeps_the_reason_and_the_day_of_its_line(
    conn: psycopg.Connection, tmp_path: Path, reason: BlockReason
) -> None:
    _put(conn, tmp_path, listed_entry("example-atlas"))
    apply_blocklist(conn, [_block(BlockScope.SOURCE, reason, source_id=HAND_SOURCE)])
    row = _row(conn, "example-atlas")
    assert (row["state"], row["removed_reason"], row["removed_on"]) == ("tombstone", reason.value, BLOCKED_ON)


def test_a_host_line_reaches_a_harvested_row_too_and_a_source_line_only_its_own_source(
    conn: psycopg.Connection, tmp_path: Path
) -> None:
    _put(conn, tmp_path, *_four(tmp_path))
    insert_row(conn, "harvested-1", host="one.example.org")
    insert_row(conn, "harvested-2", source_id="src-2", host="elsewhere.example.org")
    assert apply_blocklist(conn, [_block(BlockScope.SOURCE, source_id="src-2")]) == 1
    assert (_state(conn, "harvested-2"), _state(conn, "harvested-1"), _state(conn, "example-a")) == (
        "tombstone",
        "published",
        "published",
    )
    assert apply_blocklist(conn, [_block(BlockScope.HOST, host="one.example.org")]) == 3
    assert _state(conn, "harvested-1") == "tombstone"


@pytest.mark.parametrize(
    "rule",
    [
        _block(BlockScope.ENTRY, source_id="src-1", source_key="example-a"),  # another source
        _block(BlockScope.ENTRY, source_id=HAND_SOURCE, source_key="example-A"),
        _block(BlockScope.ENTRY, source_id=HAND_SOURCE, source_key="example"),  # a prefix is no match
        _block(
            BlockScope.PUBLISHER, source_id=HAND_SOURCE, publisher="publisher one"
        ),  # exactly as the source names it
        _block(BlockScope.PUBLISHER, source_id="src-1", publisher="Publisher One"),
        _block(BlockScope.PUBLISHER, source_id=HAND_SOURCE, publisher="Publisher"),
        _block(BlockScope.HOST, host="example.org"),  # a parent domain is no match
        _block(BlockScope.HOST, host="ne.example.org"),
        _block(BlockScope.SOURCE, source_id="src-9"),
        _block(BlockScope.SOURCE, source_id="Listed"),
    ],
)
def test_a_line_that_names_nothing_here_blocks_nothing(
    conn: psycopg.Connection, tmp_path: Path, rule: BlockRule
) -> None:
    _put(conn, tmp_path, *_four(tmp_path))
    assert apply_blocklist(conn, [rule]) == 0
    assert {_state(conn, f"example-{letter}") for letter in "abcd"} == {"published"}


def test_a_quote_in_a_blocklist_value_is_data_and_not_sql(conn: psycopg.Connection, tmp_path: Path) -> None:
    _put(conn, tmp_path, *_four(tmp_path))
    rule = _block(BlockScope.PUBLISHER, source_id=HAND_SOURCE, publisher="x' OR '1'='1")
    assert apply_blocklist(conn, [rule]) == 0
    assert _state(conn, "example-a") == "published"


def test_an_empty_blocklist_blocks_nothing(conn: psycopg.Connection, tmp_path: Path) -> None:
    _put(conn, tmp_path, *_four(tmp_path))
    assert apply_blocklist(conn, []) == 0


def test_two_lines_that_name_the_same_entry_count_it_once(conn: psycopg.Connection, tmp_path: Path) -> None:
    _put(conn, tmp_path, *_four(tmp_path))
    first = _block(BlockScope.ENTRY, BlockReason.QUALITY, source_id=HAND_SOURCE, source_key="example-a")
    second = _block(BlockScope.HOST, BlockReason.LEGAL, host="one.example.org")
    assert apply_blocklist(conn, [first, second]) == 2  # a, then c
    assert _row(conn, "example-a")["removed_reason"] == "quality"  # the first line that names it keeps its say


# --- a blocked hand entry --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rule", "left_out"),
    [
        (_block(BlockScope.ENTRY, source_id=HAND_SOURCE, source_key="example-a"), ("example-a",)),
        (_block(BlockScope.PUBLISHER, source_id=HAND_SOURCE, publisher="Publisher Two"), ("example-c", "example-d")),
        (_block(BlockScope.HOST, host="one.example.org"), ("example-a", "example-c")),
        (_block(BlockScope.SOURCE, source_id=HAND_SOURCE), ("example-a", "example-b", "example-c", "example-d")),
    ],
    ids=["entry", "publisher", "host", "source"],
)
def test_a_blocked_hand_entry_is_left_out_and_never_written(
    conn: psycopg.Connection, tmp_path: Path, rule: BlockRule, left_out: tuple[str, ...]
) -> None:
    entries = _four(tmp_path)
    written, blocked = _put(conn, tmp_path, *entries, blocklist=[rule])
    assert blocked == left_out
    assert written == tuple(entry.dataset_id for entry in entries if entry.dataset_id not in left_out)
    assert all(_row(conn, dataset_id) is None for dataset_id in left_out)


def test_a_block_that_comes_after_the_entry_ends_in_a_tombstone_and_is_no_source_removed(
    conn: psycopg.Connection, tmp_path: Path
) -> None:
    entry = listed_entry("example-atlas")
    rule = _block(BlockScope.ENTRY, BlockReason.NOT_GEODATA, source_id=HAND_SOURCE, source_key="example-atlas")
    _put(conn, tmp_path, entry)
    assert _put(conn, tmp_path, entry, blocklist=[rule]) == ((), ("example-atlas",))
    assert apply_blocklist(conn, [rule]) == 1
    # What `catalog-load` does on every run: the file is still there, the line still stands, the tombstone stays.
    assert _put(conn, tmp_path, entry, blocklist=[rule]) == ((), ("example-atlas",))
    assert apply_blocklist(conn, [rule]) == 0
    row = _row(conn, "example-atlas")
    assert (row["state"], row["removed_reason"], row["removed_on"]) == ("tombstone", "not_geodata", BLOCKED_ON)


def test_lifting_the_block_brings_the_entry_back_as_published(conn: psycopg.Connection, tmp_path: Path) -> None:
    entry = listed_entry("example-atlas")
    rule = _block(BlockScope.ENTRY, source_id=HAND_SOURCE, source_key="example-atlas")
    _put(conn, tmp_path, entry)
    apply_blocklist(conn, [rule])
    assert _state(conn, "example-atlas") == "tombstone"
    written, blocked = _put(conn, tmp_path, entry)
    assert (written, blocked) == (("example-atlas",), ())
    row = _row(conn, "example-atlas")
    assert (row["state"], row["removed_reason"], row["removed_on"]) == ("published", None, None)
    assert row["content"]["id"] == "example-atlas" and row["regions"] is not None and row["footprint"] is not None


# --- a hand entry that left listed/ ----------------------------------------------------------------------------------


def test_an_entry_removed_from_the_list_becomes_a_tombstone_with_source_removed(
    conn: psycopg.Connection, tmp_path: Path
) -> None:
    kept, gone = listed_entry("example-kept"), listed_entry("example-gone", title="Gone")
    _put(conn, tmp_path, kept, gone)
    assert _put(conn, tmp_path, kept) == ((), ())
    row = _row(conn, "example-gone")
    assert (row["state"], row["removed_reason"], row["removed_on"]) == ("tombstone", "source_removed", _today(conn))
    assert [column for column in CONTENT_COLUMNS if row[column] is not None] == []
    assert (row["source_id"], row["source_key"]) == (HAND_SOURCE, "example-gone")
    assert _state(conn, "example-kept") == "published"


def test_an_empty_list_turns_every_hand_entry_into_a_tombstone(conn: psycopg.Connection, tmp_path: Path) -> None:
    _put(conn, tmp_path, *_four(tmp_path))
    assert _put(conn, tmp_path) == ((), ())
    assert {_state(conn, f"example-{letter}") for letter in "abcd"} == {"tombstone"}


def test_a_harvested_row_is_not_a_hand_entry_that_left_the_list(conn: psycopg.Connection, tmp_path: Path) -> None:
    insert_row(conn, "harvested-1")
    _put(conn, tmp_path)
    assert _state(conn, "harvested-1") == "published"


def test_an_entry_whose_file_comes_back_is_published_again(conn: psycopg.Connection, tmp_path: Path) -> None:
    entry = listed_entry("example-atlas")
    _put(conn, tmp_path, entry)
    _put(conn, tmp_path)
    assert _state(conn, "example-atlas") == "tombstone"
    assert _put(conn, tmp_path, entry) == (("example-atlas",), ())
    row = _row(conn, "example-atlas")
    assert (row["state"], row["removed_reason"], row["removed_on"]) == ("published", None, None)


# --- an id that a full entry or a harvested row holds ----------------------------------------------------------------


def test_an_id_of_a_full_entry_is_an_error(conn: psycopg.Connection, tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="a full or retired entry has the same id: example-atlas"):
        _put(conn, tmp_path, listed_entry("example-atlas"), listed_entry("example-other"), full_ids=["example-atlas"])
    assert _row(conn, "example-other") is None  # nothing of the run was written


def test_the_ids_of_several_clashes_are_all_named(conn: psycopg.Connection, tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="example-a, example-c"):
        _put(conn, tmp_path, *_four(tmp_path), full_ids=["example-c", "example-a", "unrelated"])


def test_an_id_of_a_harvested_row_is_an_error(conn: psycopg.Connection, tmp_path: Path) -> None:
    insert_row(conn, "example-atlas", source_id="src-1")
    with pytest.raises(ConfigError, match="a harvested entry holds the same id: example-atlas"):
        _put(conn, tmp_path, listed_entry("example-atlas"))
    row = _row(conn, "example-atlas")
    assert (row["source_id"], row["state"]) == ("src-1", "published")  # the harvested row is untouched


def test_an_id_of_a_blocked_hand_entry_that_a_harvested_row_holds_is_an_error_all_the_same(
    conn: psycopg.Connection, tmp_path: Path
) -> None:
    insert_row(conn, "example-atlas")
    rule = _block(BlockScope.SOURCE, source_id=HAND_SOURCE)
    with pytest.raises(ConfigError, match="harvested"):
        _put(conn, tmp_path, listed_entry("example-atlas"), blocklist=[rule])


# --- supersede -------------------------------------------------------------------------------------------------------


def test_a_row_whose_id_a_full_entry_took_over_is_marked_superseded(conn: psycopg.Connection, tmp_path: Path) -> None:
    _put(conn, tmp_path, listed_entry("example-atlas"), listed_entry("example-other"))
    insert_row(conn, "harvested-1")
    assert supersede(conn, ["harvested-1", "example-atlas", "no-such-row"]) == ("example-atlas", "harvested-1")
    assert (_state(conn, "example-atlas"), _state(conn, "harvested-1"), _state(conn, "example-other")) == (
        "superseded",
        "superseded",
        "published",
    )
    assert supersede(conn, ["example-atlas", "harvested-1"]) == ()


def test_a_superseded_row_keeps_its_content_so_that_lifting_it_needs_no_reharvest(
    conn: psycopg.Connection, tmp_path: Path
) -> None:
    _put(conn, tmp_path, listed_entry("example-atlas"))
    supersede(conn, ["example-atlas"])
    assert _row(conn, "example-atlas")["content"] is not None


def test_a_tombstone_is_not_superseded(conn: psycopg.Connection, tmp_path: Path) -> None:
    _put(conn, tmp_path, listed_entry("example-atlas"))
    apply_blocklist(conn, [_block(BlockScope.SOURCE, source_id=HAND_SOURCE)])
    assert supersede(conn, ["example-atlas"]) == ()
    assert _state(conn, "example-atlas") == "tombstone"


def test_an_empty_list_of_full_ids_supersedes_nothing(conn: psycopg.Connection, tmp_path: Path) -> None:
    _put(conn, tmp_path, listed_entry("example-atlas"))
    assert supersede(conn, []) == ()


def test_the_blocklist_and_the_removal_leave_a_superseded_row_alone(conn: psycopg.Connection, tmp_path: Path) -> None:
    _put(conn, tmp_path, listed_entry("example-atlas"))
    supersede(conn, ["example-atlas"])
    assert apply_blocklist(conn, [_block(BlockScope.SOURCE, source_id=HAND_SOURCE)]) == 0
    _put(conn, tmp_path)  # the file is gone
    assert _state(conn, "example-atlas") == "superseded"


# --- what the database itself refuses --------------------------------------------------------------------------------

_PUBLISHED = """
    INSERT INTO public.earthx_listed_entry (dataset_id, source_id, source_key, state, content, content_sha256, sort_title,
        footprint, regions, keywords, data_kind, category, account, delivery, link_host)
    VALUES (%(id)s, 'src-1', %(key)s, 'published', '{}'::jsonb, 'x', 't', ST_MakeEnvelope(0, 0, 1, 1, 4326), '{}',
            '{example}', 'vector', 'other', 'none', 'download', 'h.example.org')
"""


def _refused(conn: psycopg.Connection, statement: str, params: dict, error: type[psycopg.Error]) -> None:
    conn.execute("SELECT 1")  # open the transaction, so that the block below is a savepoint and can never commit
    with pytest.raises(error):
        with conn.transaction():  # the refusal does not poison the transaction of the test
            conn.execute(statement, params)


def test_the_published_insert_of_these_tests_is_valid(conn: psycopg.Connection) -> None:
    conn.execute(_PUBLISHED, {"id": "example-ok", "key": "example-ok"})
    assert _state(conn, "example-ok") == "published"


@pytest.mark.parametrize(
    "dataset_id",
    ["proto-example", "proto-", "Example", "-example", "", "e" * 129, "example atlas", "example/atlas"],
)
def test_the_table_refuses_a_prototype_id_and_a_bad_one(conn: psycopg.Connection, dataset_id: str) -> None:
    _refused(conn, _PUBLISHED, {"id": dataset_id, "key": "k"}, psycopg.errors.CheckViolation)


def test_the_table_refuses_a_tombstone_that_holds_content(conn: psycopg.Connection) -> None:
    statement = """
        INSERT INTO public.earthx_listed_entry (dataset_id, source_id, source_key, state, removed_reason, removed_on, {col})
        VALUES ('example-x', 'src-1', 'k', 'tombstone', 'legal', current_date, {value})
    """
    values = {
        "content": "'{}'::jsonb",
        "content_sha256": "'x'",
        "sort_title": "'t'",
        "footprint": "ST_MakeEnvelope(0, 0, 1, 1, 4326)",
        "time_span": "tstzrange(now(), now() + interval '1 day')",
        "regions": "'{}'",
        "keywords": "'{example}'",
        "data_kind": "'raster'",
        "category": "'water'",
        "account": "'none'",
        "delivery": "'download'",
        "publisher": "'P'",
        "link_host": "'h.example.org'",
        "license_ref": "'CC0-1.0'",
    }
    for column, value in values.items():
        _refused(conn, statement.format(col=column, value=value), {}, psycopg.errors.CheckViolation)


def test_the_table_takes_a_tombstone_with_only_its_key_reason_and_day(conn: psycopg.Connection) -> None:
    conn.execute(
        "INSERT INTO public.earthx_listed_entry (dataset_id, source_id, source_key, state, removed_reason, removed_on) "
        "VALUES ('example-x', 'src-1', 'k', 'tombstone', 'legal', current_date)"
    )
    assert _state(conn, "example-x") == "tombstone"


@pytest.mark.parametrize(
    "removal",
    ["NULL, NULL", "'legal', NULL", "NULL, current_date", "'spam', current_date"],
    ids=["none", "no-day", "no-reason", "unknown-reason"],
)
def test_the_table_refuses_a_tombstone_without_reason_and_day(conn: psycopg.Connection, removal: str) -> None:
    statement = (
        "INSERT INTO public.earthx_listed_entry (dataset_id, source_id, source_key, state, removed_reason, removed_on) "
        f"VALUES ('example-x', 'src-1', 'k', 'tombstone', {removal})"
    )
    _refused(conn, statement, {}, psycopg.errors.CheckViolation)


def test_the_table_refuses_a_reason_on_a_row_that_is_no_tombstone(conn: psycopg.Connection) -> None:
    conn.execute(_PUBLISHED, {"id": "example-x", "key": "k"})
    _refused(
        conn,
        "UPDATE public.earthx_listed_entry SET removed_reason = 'legal', removed_on = current_date",
        {},
        psycopg.errors.CheckViolation,
    )


@pytest.mark.parametrize(
    "column",
    [
        "content",
        "content_sha256",
        "sort_title",
        "footprint",
        "regions",
        "keywords",
        "data_kind",
        "category",
        "account",
        "delivery",
        "link_host",
    ],
)
def test_the_table_refuses_a_published_row_without_a_field_it_is_found_by(
    conn: psycopg.Connection, column: str
) -> None:
    conn.execute(_PUBLISHED, {"id": "example-x", "key": "k"})
    _refused(conn, f"UPDATE public.earthx_listed_entry SET {column} = NULL", {}, psycopg.errors.CheckViolation)


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("state", "visible"),
        ("data_kind", "image"),
        ("category", "Water"),
        ("account", "gratis"),
        ("delivery", "post"),
    ],
)
def test_the_table_refuses_a_value_outside_its_fixed_ones(conn: psycopg.Connection, column: str, value: str) -> None:
    conn.execute(_PUBLISHED, {"id": "example-x", "key": "k"})
    _refused(
        conn,
        f"UPDATE public.earthx_listed_entry SET {column} = %(value)s",
        {"value": value},
        psycopg.errors.CheckViolation,
    )


@pytest.mark.parametrize(
    "state", ["published", "in_review", "needs_rule", "blocked", "superseded", "not_geodata", "duplicate"]
)
def test_the_table_takes_every_state_of_the_approval_of_m5_20(conn: psycopg.Connection, state: str) -> None:
    insert_row(conn, "example-x", state=state)
    assert _state(conn, "example-x") == state


def test_the_table_takes_a_paid_account(conn: psycopg.Connection) -> None:
    conn.execute(_PUBLISHED, {"id": "example-x", "key": "k"})
    conn.execute("UPDATE public.earthx_listed_entry SET account = 'paid'")


def test_the_table_holds_one_row_per_id_and_one_per_key_at_the_source(conn: psycopg.Connection) -> None:
    conn.execute(_PUBLISHED, {"id": "example-x", "key": "k"})
    _refused(conn, _PUBLISHED, {"id": "example-x", "key": "k2"}, psycopg.errors.UniqueViolation)
    _refused(conn, _PUBLISHED, {"id": "example-y", "key": "k"}, psycopg.errors.UniqueViolation)


def test_the_region_table_refuses_a_bad_code_and_a_bad_level(conn: psycopg.Connection) -> None:
    statement = (
        "INSERT INTO public.earthx_region (code, level, name, outline) VALUES (%(code)s, %(level)s, 'n', "
        "ST_Multi(ST_MakeEnvelope(0, 0, 1, 1, 4326)))"
    )
    _refused(conn, statement, {"code": "xa", "level": "state"}, psycopg.errors.CheckViolation)
    _refused(conn, statement, {"code": "XAA", "level": "state"}, psycopg.errors.CheckViolation)
    _refused(conn, statement, {"code": "XA", "level": "province"}, psycopg.errors.CheckViolation)


def test_the_region_table_refuses_an_outline_that_is_no_area(conn: psycopg.Connection) -> None:
    _refused(
        conn,
        "INSERT INTO public.earthx_region (code, level, name, outline) VALUES ('XA', 'state', 'n', "
        "ST_SetSRID(ST_MakePoint(0, 0), 4326))",
        {},
        psycopg.Error,
    )


# --- review of M5-40: order of catalog-load and the collation of the keys --------------------------------------------


def test_a_hand_entry_that_went_full_is_superseded_not_a_tombstone(conn: psycopg.Connection, tmp_path: Path) -> None:
    # In the order of `load.main`: the file leaves listed/ in the same commit as the full entry arrives.
    _put(conn, tmp_path, listed_entry("example-atlas"))
    supersede(conn, ["example-atlas"])
    _put(conn, tmp_path, full_ids=["example-atlas"])
    row = _row(conn, "example-atlas")
    assert row["state"] == "superseded" and row["content"] is not None and row["removed_reason"] is None


def test_catalog_load_supersedes_before_it_writes_the_hand_entries() -> None:
    import inspect

    from earthx.catalog import load

    source = inspect.getsource(load.main)
    assert source.index("supersede(") < source.index("write_hand_entries(")


@pytest.mark.parametrize("column", ["dataset_id", "sort_title"])
def test_the_keys_of_the_order_compare_by_bytes(conn: psycopg.Connection, column: str) -> None:
    # Python orders by code point; a collation like en_US skips spaces and punctuation and would page differently.
    collation = conn.execute(
        "SELECT collation_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = 'earthx_listed_entry' AND column_name = %s",
        (column,),
    ).fetchone()[0]
    assert collation == "C"


# --- keywords (Otto, 15.11.2026) --------------------------------------------------------------------------------------


def test_a_hand_entry_stores_its_keywords_normalized_in_column_and_document(
    conn: psycopg.Connection, tmp_path: Path
) -> None:
    _put(conn, tmp_path, listed_entry("example-atlas", keywords=("Höhenmodell", " DGM  1m ", "höhenmodell", "2024")))
    row = _row(conn, "example-atlas")
    assert row["keywords"] == ["höhenmodell", "dgm 1m"]
    assert row["content"]["keywords"] == ["höhenmodell", "dgm 1m"]


def test_a_hand_entry_with_only_technical_keywords_gets_the_words_of_its_category(
    conn: psycopg.Connection, tmp_path: Path
) -> None:
    _put(conn, tmp_path, listed_entry("example-atlas", category="boundaries", keywords=("https://example.org/x", "42")))
    assert _row(conn, "example-atlas")["keywords"] == ["boundaries", "addresses", "cadastre"]


@pytest.mark.parametrize("keywords", ["'{}'", "NULL"])
def test_the_table_refuses_a_published_row_without_keywords(conn: psycopg.Connection, keywords: str) -> None:
    conn.execute(_PUBLISHED, {"id": "example-x", "key": "k"})
    _refused(conn, f"UPDATE public.earthx_listed_entry SET keywords = {keywords}", {}, psycopg.errors.CheckViolation)


# --- the hand entries of the repo (M5-17) ----------------------------------------------------------------------------


def test_the_hand_entries_of_the_repo_are_written_with_their_access_and_regions(conn: psycopg.Connection) -> None:
    # A `catalog-load` of another test on this worker's database may have committed them already.
    conn.execute("DELETE FROM public.earthx_listed_entry")
    write_regions(conn, load_regions())
    listed, blocked = write_hand_entries(conn, load_listed(), [], full_ids=[])
    assert (sorted(listed), blocked) == (["corine-land-cover", "landsat-c2-l2"], ())
    corine, landsat = _row(conn, "corine-land-cover"), _row(conn, "landsat-c2-l2")
    assert (corine["account"], corine["delivery"], corine["data_kind"]) == ("free_account", "download", "vector")
    assert (landsat["account"], landsat["delivery"], landsat["data_kind"]) == ("requester_pays", "download", "raster")
    # Exactly the EEA-39 and their subdivisions: no neighbour of the simplified outlines, no enclave (plan §4b, F4).
    assert {code for code in corine["regions"] if "-" not in code} == EEA_39
    assert {"DE-BY", "AT-9", "CH-ZH", "LI-11"} <= set(corine["regions"])
    assert {code.split("-")[0] for code in corine["regions"]} == EEA_39
    assert {"DE", "US", "AU", "BR", "AQ"} <= set(landsat["regions"])
    assert (corine["state"], landsat["state"]) == ("published", "published")


# --- coverage_states (M5-17 F4) --------------------------------------------------------------------------------------


def _covering(states: tuple[str, ...], bbox=(5.0, 45.0, 17.5, 55.5)) -> ListedEntry:
    return listed_entry("example-dach", spatial_extent=_box(*bbox), coverage_states=states)


def test_the_footprint_of_named_states_is_their_outline_and_not_the_box(
    conn: psycopg.Connection, tmp_path: Path
) -> None:
    write_regions(conn, load_regions())
    _put(conn, tmp_path, _covering(("AT", "CH", "DE", "LI")))
    row = _row(conn, "example-dach")
    assert {code for code in row["regions"] if "-" not in code} == {"AT", "CH", "DE", "LI"}
    # Prague lies in the box, not in the outline of the four states.
    inside = conn.execute(
        "SELECT ST_Intersects(footprint, ST_MakeEnvelope(14.3, 50.0, 14.6, 50.2, 4326)) FROM public.earthx_listed_entry "
        "WHERE dataset_id = 'example-dach'"
    ).fetchone()[0]
    assert inside is False


def test_named_states_are_cut_to_the_box(conn: psycopg.Connection, tmp_path: Path) -> None:
    write_regions(conn, load_regions())
    _put(conn, tmp_path, _covering(("FR",), bbox=(-5.5, 41.0, 10.0, 51.5)))
    west, south, east, north = conn.execute(
        "SELECT ST_XMin(footprint), ST_YMin(footprint), ST_XMax(footprint), ST_YMax(footprint) "
        "FROM public.earthx_listed_entry WHERE dataset_id = 'example-dach'"
    ).fetchone()
    assert west >= -5.5 and south >= 41.0 and east <= 10.0 and north <= 51.5
    assert _regions_of(conn, "example-dach") == ["FR"]


def test_a_state_the_table_lacks_is_an_error(conn: psycopg.Connection, tmp_path: Path) -> None:
    write_regions(conn, [region for region in load_regions() if region.code != "LI"])
    with pytest.raises(ConfigError, match="earthx_region lacks"):
        _put(conn, tmp_path, _covering(("AT", "LI")))


def test_a_state_outside_the_box_is_an_error(conn: psycopg.Connection, tmp_path: Path) -> None:
    write_regions(conn, load_regions())
    with pytest.raises(ConfigError, match="outside spatial_extent"):
        _put(conn, tmp_path, _covering(("AT", "PT")))


def test_a_new_outline_file_keeps_the_regions_to_the_named_states(conn: psycopg.Connection) -> None:
    regions = load_regions()
    conn.execute("DELETE FROM public.earthx_listed_entry")
    write_regions(conn, regions)
    write_hand_entries(conn, load_listed(), [], full_ids=[])
    # A changed outline file derives the regions of every entry anew, from the stored footprint.
    write_regions(conn, [region for region in regions if region.code != "AT-9"])
    states = {code for code in _row(conn, "corine-land-cover")["regions"] if "-" not in code}
    assert states == EEA_39
    assert "AT-9" not in _row(conn, "corine-land-cover")["regions"]


def test_the_box_stays_the_footprint_without_named_states(conn: psycopg.Connection, tmp_path: Path) -> None:
    write_regions(conn, load_regions())
    _put(conn, tmp_path, listed_entry("example-box", spatial_extent=_box(5.0, 45.0, 17.5, 55.5)))
    assert {"CZ", "PL"} <= set(_regions_of(conn, "example-box"))

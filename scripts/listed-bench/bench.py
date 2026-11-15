#!/usr/bin/env python3
"""The read path of listed entries at 10⁶ synthetic rows (M5-40 plan §3, §5.6).

    PGDATABASE=<scratch database> PYTHONPATH=backend python scripts/listed-bench/bench.py --n 1000000

The connection comes from the libpq variables (``PGHOST``, ``PGUSER``, ``PGPASSWORD``, ``PGDATABASE``). The database
must be a scratch database with PostGIS and ``bench`` in its name: the script applies the earthx migrations, writes the
region outlines, empties ``earthx_listed_entry`` and fills it with ``--n`` synthetic rows (no real data, no network). It
refuses any other database and a table with rows it did not write. Drop the database afterwards.

The rows follow the procedure of plan §3, with a fixed seed: 85 % boxes in the area of DE, AT and CH, 10 % in Europe,
5 % anywhere, edges log-uniform between 0.003° and 6°, 0.5 % global; 65 % with a period, a fifth of them open; data
kind, account and delivery by fixed shares; a description of about 1.3 KB, so that the documents leave the row as real
ones do. Regions are derived by the same rule as ``catalog-load``.

Measured with the functions ``api`` calls (``catalog.listed_search``): a page of 50, the page after an entry near
the end (keyset), and the count up to 10 001, for the filters of the plan. Five runs each, median and maximum in ms,
one JSON line per measurement, then a table.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from datetime import UTC, datetime
from functools import partial

import psycopg
from psycopg import sql

from earthx.catalog.listed import load_regions
from earthx.catalog.listed_search import ListedFilter, count_listed, listed_page
from earthx.catalog.listed_store import REGIONS_OF, write_regions
from earthx.catalog.schema import apply_migrations

RUNS = 5
CITY = {"type": "Polygon", "coordinates": [[[7.3, 46.9], [7.5, 46.9], [7.5, 47.0], [7.3, 47.0], [7.3, 46.9]]]}
COUNTRY = {"type": "Polygon", "coordinates": [[[5.9, 47.3], [15.0, 47.3], [15.0, 55.1], [5.9, 55.1], [5.9, 47.3]]]}

_FILL = """
INSERT INTO public.earthx_listed_entry (
    dataset_id, source_id, source_key, state, content, content_sha256, sort_title, footprint, time_span, regions,
    data_kind, category, account, delivery, publisher, link_host, published_at)
SELECT 'syn-' || lpad(g.i::text, 7, '0'), 'bench-' || (g.i %% 8), g.i::text, 'published',
       jsonb_build_object('type', 'Collection', 'id', 'syn-' || lpad(g.i::text, 7, '0'), 'title', g.title,
                          'description', repeat('synthetic description ', 60), 'links', '[]'::jsonb),
       md5(g.i::text), g.title, ST_MakeEnvelope(g.west, g.south, g.east, g.north, 4326),
       CASE WHEN g.r_time < 0.35 THEN NULL
            WHEN g.r_time < 0.55 THEN tstzrange(g.t0, NULL, '[]')
            ELSE tstzrange(g.t0, g.t0 + (g.r_t1 * 3650) * interval '1 day', '[]') END,
       '{}', (ARRAY['raster','vector','vector','vector','table','document','service','other'])[1 + floor(g.r_kind * 8)::int],
       (ARRAY['optical','elevation','land_cover','water','nature','boundaries','infrastructure','other'])
           [1 + floor(g.r_acc * 8)::int],
       (ARRAY['none','none','none','none','none','none','free_account','paid','requester_pays','anonymous_token'])
           [1 + floor(g.r_acc * 10)::int],
       (ARRAY['download','download','download','service','service','order','on_request'])[1 + floor(g.r_del * 7)::int],
       'publisher ' || (g.i %% 300), 'host' || (g.i %% 50) || '.example.org', now()
FROM (
    SELECT b.i, b.r_time, b.r_t1, b.r_kind, b.r_acc, b.r_del,
           'synthetic ' || lpad((b.r_title * 1e9)::bigint::text, 10, '0') AS title,
           timestamptz '1950-01-01' + (b.r_t0 * 76 * 365) * interval '1 day' AS t0,
           CASE WHEN b.w >= 360 THEN -180 ELSE greatest(-180, b.cx - b.w / 2) END AS west,
           CASE WHEN b.w >= 360 THEN -90 ELSE greatest(-90, b.cy - b.w * (0.5 + b.r_asp) / 2) END AS south,
           CASE WHEN b.w >= 360 THEN 180 ELSE least(180, b.cx + b.w / 2) END AS east,
           CASE WHEN b.w >= 360 THEN 90 ELSE least(90, b.cy + b.w * (0.5 + b.r_asp) / 2) END AS north
    FROM (
        SELECT r.*,
               CASE WHEN r.r_geo < 0.85 THEN 5.5 + r.r_lon * 11.5 WHEN r.r_geo < 0.95 THEN -25 + r.r_lon * 70
                    ELSE -180 + r.r_lon * 360 END AS cx,
               CASE WHEN r.r_geo < 0.85 THEN 45.8 + r.r_lat * 9.3 WHEN r.r_geo < 0.95 THEN 34 + r.r_lat * 37
                    ELSE -80 + r.r_lat * 160 END AS cy,
               CASE WHEN r.r_geo >= 0.995 THEN 360.0 ELSE power(10, -2.5 + r.r_size * 3.3) END AS w
        FROM (SELECT i, random() AS r_geo, random() AS r_lon, random() AS r_lat, random() AS r_size,
                     random() AS r_asp, random() AS r_time, random() AS r_t0, random() AS r_t1, random() AS r_kind,
                     random() AS r_acc, random() AS r_del, random() AS r_title
              FROM generate_series(1, %(n)s) AS i) r
    ) b
) g
"""


class NotAScratchDatabase(SystemExit):
    """The database is not one this script may fill and empty."""


def _check_scratch(conn: psycopg.Connection) -> None:
    """Refuse a database whose name does not say ``bench``, and one that holds listed rows not written here: the
    script empties ``earthx_listed_entry``, and a deletion of real data needs Otto (CLAUDE.md)."""
    name = conn.execute("SELECT current_database()").fetchone()[0]
    if "bench" not in name:
        raise NotAScratchDatabase(f"refused: the database {name!r} has no 'bench' in its name")
    exists = conn.execute("SELECT to_regclass('public.earthx_listed_entry') IS NOT NULL").fetchone()[0]
    if (
        exists
        and conn.execute(
            "SELECT EXISTS (SELECT 1 FROM public.earthx_listed_entry WHERE dataset_id NOT LIKE 'syn-%')"
        ).fetchone()[0]
    ):
        raise NotAScratchDatabase("refused: earthx_listed_entry holds rows this script did not write")


def _fill(n: int) -> dict[str, float]:
    timings = {}
    with psycopg.connect() as conn:
        _check_scratch(conn)
        apply_migrations(conn)
        write_regions(conn, load_regions())
        conn.execute("TRUNCATE public.earthx_listed_entry")
        started = time.perf_counter()
        conn.execute("SELECT setseed(0.540)")
        conn.execute(_FILL, {"n": n})
        timings["insert_s"] = time.perf_counter() - started
        conn.commit()
        started = time.perf_counter()
        conn.execute(
            sql.SQL("UPDATE public.earthx_listed_entry SET regions = {}").format(
                sql.SQL(REGIONS_OF.format(footprint="footprint"))
            )
        )
        timings["regions_s"] = time.perf_counter() - started
        conn.commit()
    with psycopg.connect(autocommit=True) as conn:
        conn.execute("VACUUM ANALYZE public.earthx_listed_entry")
    return timings


def _filters() -> dict[str, ListedFilter]:
    year = (datetime(2020, 1, 1, tzinfo=UTC), datetime(2020, 12, 31, 23, 59, 59, tzinfo=UTC))
    decade = (datetime(2015, 1, 1, tzinfo=UTC), datetime(2025, 12, 31, tzinfo=UTC))
    return {
        "no filter": ListedFilter(),
        "box of a city": ListedFilter(area=CITY),
        "box of a country": ListedFilter(area=COUNTRY),
        "one year": ListedFilter(period=year),
        "region DE-BY": ListedFilter(regions=("DE-BY",)),
        "city + 2015-2025": ListedFilter(area=CITY, period=decade),
        "country + DE-BY + one year": ListedFilter(area=COUNTRY, regions=("DE-BY",), period=year),
    }


async def _time(call) -> tuple[float, float, object]:
    times, result = [], None
    for _ in range(RUNS):
        started = time.perf_counter()
        result = await call()
        times.append((time.perf_counter() - started) * 1000)
    return statistics.median(times), max(times), result


async def _measure() -> list[dict[str, object]]:
    rows = []
    async with await psycopg.AsyncConnection.connect(autocommit=True) as conn:
        for name, where in _filters().items():
            page = await _time(partial(listed_page, conn, where, after=None, limit=50))
            last = page[2][-1] if page[2] else None
            deep = None
            if last is not None:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT sort_title, dataset_id FROM public.earthx_listed_entry WHERE state = 'published' "
                        "ORDER BY sort_title, dataset_id OFFSET (SELECT count(*) * 9 / 10 FROM "
                        "public.earthx_listed_entry) LIMIT 1"
                    )
                    key = await cur.fetchone()
                deep = await _time(partial(listed_page, conn, where, after=(key[0], key[1]), limit=50))
            count = await _time(partial(count_listed, conn, where, cap=10_001))
            row = {
                "filter": name,
                "page_ms": round(page[0], 1),
                "page_max_ms": round(page[1], 1),
                "deep_page_ms": None if deep is None else round(deep[0], 1),
                "count_ms": round(count[0], 1),
                "counted": count[2],
                "returned": len(page[2]),
            }
            print(json.dumps(row), flush=True)
            rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--n", type=int, default=1_000_000, help="synthetic rows (default 10^6)")
    parser.add_argument("--keep", action="store_true", help="measure the rows already there, do not fill again")
    args = parser.parse_args()
    if not args.keep:
        print(json.dumps({"rows": args.n, **{k: round(v, 1) for k, v in _fill(args.n).items()}}), flush=True)
    rows = asyncio.run(_measure())
    print("\n| Filter | Seite | Seite nahe dem Ende | Zählung bis 10 001 (Treffer) |\n|---|---|---|---|")
    for row in rows:
        print(
            f"| {row['filter']} | {row['page_ms']} ms | {row['deep_page_ms']} ms | "
            f"{row['count_ms']} ms ({row['counted']}) |"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

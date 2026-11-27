"""Plans and order of broad search words on the local platform (M5-66), for Otto's measurement.

Run inside the container of `api`, which holds the code and the connection (PG* variables):

    Get-Content .\\scripts\\m5-66-explain.py | docker compose exec -T api python - > ..\\earthx-ausgaben\\m5-66\\explain.txt

Writes to stdout only:
  1. settings of Postgres that decide the plans, and the sizes of the two tables of the search;
  2. per query (data, map, water; without a filter and with region DE): the time of `search_datasets` alone, and
     `EXPLAIN (ANALYZE, BUFFERS)` of both arms with the parameters the search uses;
  3. for three queries with a category or a region: a hash of the ids of the first page (as `m5-66-messung.ps1` makes
     it) as built, without a depth, and the way of `main` before M5-66 (ranks over all hits, filters afterwards).

No id, title or area is printed: arrays in a plan (the ids of full entries of a category) are masked, and a page shows
only as the hash. The only texts are the three words. Nothing is written to the database; every statement runs in a
transaction that is rolled back.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import time

import psycopg
from psycopg import sql

from earthx.catalog import search as S
from earthx.catalog.datasets import registry
from earthx.catalog.glossary import normalize, parse_query
from earthx.catalog.listed_search import full_entries

QUERIES = [("data", ()), ("map", ()), ("water", ()), ("water", ("DE",)), ("map", ("DE",))]
ORDER = [("map", "water", ()), ("water", "water", ()), ("map", "boundaries", ("DE",))]
_ARRAY = re.compile(r"'\{[^']*\}'")


def _masked(line: str) -> str:
    return _ARRAY.sub("'{...}'", line)


def _page_hash(ids) -> str:
    return hashlib.sha256("\n".join(ids[:20]).encode("utf-8")).hexdigest()[:16]


def _full_ids(category):
    return None if category is None else [c.dataset_id for c in registry() if c.category == category]


async def _explain(conn, statement, params) -> list[str]:
    async with conn.cursor() as cur:
        await cur.execute(sql.SQL("EXPLAIN (ANALYZE, BUFFERS) ") + statement, params, prepare=False)
        return [_masked(row[0]) for row in await cur.fetchall()]


async def _plans(conn, text: str, regions: tuple[str, ...]) -> None:
    kept = S.Kept(regions=regions)
    best = 1e9
    for _ in range(3):
        started = time.perf_counter()
        await S.search_datasets(conn, text, kept=kept)
        best = min(best, time.perf_counter() - started)
    print(f"\n=== {text}{' + region ' + ','.join(regions) if regions else ''}: search_datasets best of 3 "
          f"{best * 1000:.0f} ms")
    units = parse_query(text, None)
    terms = {f"term_{n}_{i}": term for n, unit in enumerate(units) for i, term in enumerate(unit.terms)}
    params = {
        **S._filter_params(None, None),
        **terms,
        **S._kept_params(kept),
        "depth": S.DEPTH,
        "count_up_to": S.COUNT_UP_TO,
        "share": S.MIN_SHARE,
        "named_numbers": [],
        "normal": normalize(text),
        "numbers": [],
        "codes": [],
    }
    async with conn.transaction(force_rollback=True):
        await conn.execute("SET LOCAL client_min_messages = warning")
        await conn.execute("SELECT set_config('pg_trgm.word_similarity_threshold', %s, true)", (str(S.TRIGRAM_THRESHOLD),))
        start = S.Start.NO_AREA
        print("--- full text")
        print("\n".join(await _explain(conn, S._full_text_sql(units, S.JOINING, start=start, named_numbers=False, kept=kept), params)))
        print("--- trigrams")
        print("\n".join(await _explain(conn, S._trigram_sql(start=start, numbers=False, codes=False, kept=kept), params)))


async def _old_way(conn, text, category, regions) -> list[str]:
    """The ids as `main` before M5-66 gave them: the search over all hits, the filters afterwards (route)."""
    result = await S.search_datasets(conn, text, depth=10**9, count_up_to=10**9)
    full_ids = _full_ids(category)
    full = [i for i in result.ids if i not in result.listed and (full_ids is None or i in full_ids)]
    if regions and full:
        kept = {dataset_id for _, dataset_id in await full_entries(conn, full, regions)}
        full = [i for i in full if i in kept]
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT dataset_id FROM public.earthx_listed_entry WHERE dataset_id = ANY(%s) AND state = 'published'"
            " AND (%s::text IS NULL OR category = %s) AND (cardinality(%s::text[]) = 0 OR regions && %s::text[])",
            (sorted(result.listed), category, category, list(regions), list(regions)),
        )
        listed = {row[0] for row in await cur.fetchall()}
    keep = set(full) | listed
    return [i for i in result.ids if i in keep]


async def main() -> None:
    async with await psycopg.AsyncConnection.connect() as conn:
        print("=== settings")
        for name in ("server_version", "jit", "work_mem", "shared_buffers", "effective_cache_size",
                     "max_parallel_workers_per_gather", "random_page_cost"):
            print(f"{name}: {(await (await conn.execute(f'SHOW {name}')).fetchone())[0]}")
        for table in ("earthx_dataset_search", "earthx_listed_entry"):
            size = (await (await conn.execute(
                "SELECT pg_size_pretty(pg_relation_size(%s)), pg_size_pretty(pg_total_relation_size(%s))",
                (f"public.{table}", f"public.{table}"))).fetchone())
            print(f"{table}: heap {size[0]}, with toast and indexes {size[1]}")
        await conn.commit()
        for text, regions in QUERIES:
            await _plans(conn, text, regions)
        print("\n=== order of the first page (hash as in m5-66-messung.ps1)")
        for text, category, regions in ORDER:
            kept = S.Kept(category=category, full_ids=_full_ids(category), regions=regions)
            built = (await S.search_datasets(conn, text, kept=kept)).ids
            unlimited = (await S.search_datasets(conn, text, kept=kept, depth=10**9)).ids
            old = await _old_way(conn, text, category, regions)
            print(f"{text} + category {category}{' + region ' + ','.join(regions) if regions else ''}: "
                  f"as built {_page_hash(built)}, without depth {_page_hash(unlimited)}, way of main {_page_hash(old)}")


asyncio.run(main())

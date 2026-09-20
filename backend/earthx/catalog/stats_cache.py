"""The statistics cache of the tile path (adr/0006 §5 "Zu Frage 3").

Same shape and the same three properties as ``search_cache.py`` — the connection
stays the caller's, a failure is the caller's to ignore, every statement runs in
its own savepoint — with two differences that follow from what is cached:

* **The lifetime is 30 days**, and it is housekeeping rather than freshness: the
  statistics of an immutable COG do not change. What expires is disk, not truth.
* **The key is built here**, not by the caller. It is a hash over the values that
  decide the answer (dataset, item, asset, band selection, percentiles), so that
  two callers asking the same question cannot key it two ways — and so that no
  address and no area of interest ends up in a database column
  (projektplan.md 7, point 6).

`access` uses this through a structural protocol of its own; it may not import
`catalog`'s module directly in a way that would tie the render path to Postgres.
Whoever has both — `api`, when it wires the tiler process — hands it over.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

TABLE = "public.earthx_stats_cache"

# adr/0006 §5 "Zu Frage 3", Otto's answer 3 of 20.09.2026.
TTL_S = 30 * 24 * 60 * 60

_SELECT = f"SELECT payload FROM {TABLE} WHERE cache_key = %s AND expires_at > now()"

_UPSERT = f"""
INSERT INTO {TABLE} (cache_key, dataset_id, payload, expires_at)
VALUES (%s, %s, %s, now() + make_interval(secs => %s))
ON CONFLICT (cache_key) DO UPDATE
    SET dataset_id = EXCLUDED.dataset_id,
        payload    = EXCLUDED.payload,
        expires_at = EXCLUDED.expires_at,
        created_at = now()
"""


def stats_cache_key(dataset_id: str, item_id: str, asset: str, parameters: dict[str, Any]) -> str:
    """One key for one question.

    ``parameters`` carries everything that changes the numbers — band indexes or
    expression, the percentiles, the preview size rio-tiler computes them on. It is
    serialised with sorted keys, so the same question written in two orders is one
    entry and not two.
    """
    payload = json.dumps(
        {"dataset": dataset_id, "item": item_id, "asset": asset, "parameters": parameters},
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class PostgresStatsCache:
    """Key-value with an expiry, one row per cached statistic."""

    def __init__(self, conn: psycopg.AsyncConnection) -> None:
        self._conn = conn

    async def get(self, key: str) -> dict[str, Any] | None:
        """The stored value, or None when it is absent or past its expiry."""
        async with self._conn.transaction(), self._conn.cursor() as cur:
            await cur.execute(_SELECT, (key,))
            row = await cur.fetchone()
        return None if row is None else row[0]

    async def set(self, key: str, value: dict[str, Any], *, dataset_id: str, ttl_s: float = TTL_S) -> None:
        """Store a value, replacing whatever was under that key."""
        async with self._conn.transaction(), self._conn.cursor() as cur:
            await cur.execute(_UPSERT, (key, dataset_id, Jsonb(value), float(ttl_s)))

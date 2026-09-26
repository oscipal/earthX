"""The Postgres cache and the shared rate slot of M3-07a's place search.

Two tables, because they expire differently: the cache holds finished answers with
their own TTL (``search_cache.py``'s pattern, minus ``dataset_id`` — a place search
is not tied to a dataset); the rate slot is a single pointer per named upstream,
moved forward by whoever asks next, and never expires on its own.

Same three properties as ``search_cache.py``: the connection stays the caller's, a
failure here is the caller's to decide about, and every statement runs in its own
savepoint. That last property matters differently for the two: a broken cache read
or write is meant to be swallowed by the caller (E5, `adapters.nominatim._cache_get`/
`_cache_set`); a broken rate-slot reservation is not (a caller that cannot reserve
must not send either) — the savepoint just keeps either failure from aborting
whatever transaction the caller is already in.

No search text or result ever reaches these tables: the cache key is a hash built
in ``adapters/nominatim.py``, and the rate slot has no room for one at all.
"""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.types.json import Jsonb

CACHE_TABLE = "public.earthx_geocode_cache"
SLOT_TABLE = "public.earthx_rate_slots"

_SELECT_CACHE = f"SELECT payload FROM {CACHE_TABLE} WHERE cache_key = %s AND expires_at > now()"

_UPSERT_CACHE = f"""
INSERT INTO {CACHE_TABLE} (cache_key, payload, expires_at)
VALUES (%s, %s, now() + make_interval(secs => %s))
ON CONFLICT (cache_key) DO UPDATE
    SET payload    = EXCLUDED.payload,
        expires_at = EXCLUDED.expires_at,
        created_at = now()
"""

# `next_slot` is read back as it stands *after* the move: for a fresh row that is
# `now() + 1s`; for an existing one, `greatest(old, now()) + 1s`. Subtracting the one
# second back out gives the instant this caller may send at — `clock_timestamp()` is
# read again in the same statement so the caller measures its wait against the same
# clock the reservation was made on, not its own possibly-skewed one.
_RESERVE_SLOT = f"""
INSERT INTO {SLOT_TABLE} (name, next_slot)
VALUES (%s, clock_timestamp() + interval '1 second')
ON CONFLICT (name) DO UPDATE
    SET next_slot = greatest({SLOT_TABLE}.next_slot, clock_timestamp()) + interval '1 second'
RETURNING (next_slot - interval '1 second') AS assigned_slot, clock_timestamp() AS reserved_at
"""

_PUSH_BACK_SLOT = f"""
INSERT INTO {SLOT_TABLE} (name, next_slot)
VALUES (%s, clock_timestamp() + make_interval(secs => %s))
ON CONFLICT (name) DO UPDATE
    SET next_slot = greatest({SLOT_TABLE}.next_slot, clock_timestamp()) + make_interval(secs => %s)
"""


class PostgresGeocodeCache:
    """Key-value with an expiry, one row per cached place-search answer."""

    def __init__(self, conn: psycopg.AsyncConnection) -> None:
        self._conn = conn

    async def get(self, key: str) -> dict[str, Any] | None:
        """The stored value, or None when it is absent or past its expiry."""
        async with self._conn.transaction(), self._conn.cursor() as cur:
            await cur.execute(_SELECT_CACHE, (key,))
            row = await cur.fetchone()
        return None if row is None else row[0]

    async def set(self, key: str, value: dict[str, Any], *, ttl_s: float) -> None:
        """Store a value for ``ttl_s`` seconds, replacing whatever was under it."""
        async with self._conn.transaction(), self._conn.cursor() as cur:
            await cur.execute(_UPSERT_CACHE, (key, Jsonb(value), float(ttl_s)))


class PostgresRateSlot:
    """The one pointer per named upstream, shared across every ``api`` process.

    Not a lock: :meth:`reserve` never blocks and holds no connection open while a
    caller waits on the delay it returns — the caller sleeps on its own time, then
    sends (docs/plans/m3-07a-ortssuche-backend.md §9).
    """

    def __init__(self, conn: psycopg.AsyncConnection) -> None:
        self._conn = conn

    async def reserve(self, name: str) -> float:
        """Seconds until the slot just reserved, at least 0. Always reserves."""
        async with self._conn.transaction(), self._conn.cursor() as cur:
            await cur.execute(_RESERVE_SLOT, (name,))
            assigned_slot, reserved_at = await cur.fetchone()
        return max(0.0, (assigned_slot - reserved_at).total_seconds())

    async def push_back(self, name: str, *, seconds: float) -> None:
        """Move the shared pointer forward by at least ``seconds`` more (a `429`)."""
        async with self._conn.transaction(), self._conn.cursor() as cur:
            await cur.execute(_PUSH_BACK_SLOT, (name, float(seconds), float(seconds)))

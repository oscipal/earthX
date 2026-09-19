"""The application cache of E4, on the database pgstac already brings.

It fits the ``SearchCache`` protocol of ``earthx/adapters/cache.py`` — structurally,
not by inheritance, because ``catalog`` must not import ``adapters``
(architekturplan.md 3.1). Whoever uses both hands this object to the adapter: the
tests here, the federating client in ``api`` from M1-07 on.

Two properties worth stating, because both are what makes a cache harmless:

* **The connection stays the caller's.** This class opens nothing, commits nothing
  and closes nothing. What it writes becomes durable when the caller commits, which
  is also why the tests can roll everything back.
* **A failure here is the caller's to ignore.** Errors are not swallowed at this end;
  the adapter catches them and asks the source instead (E5, adr/0001 §9.3). Silence
  in this module would hide a broken cache forever.
* **Each statement runs in its own savepoint.** A failed statement aborts the whole
  transaction it runs in, and from M1-07 that is the transaction serving the request:
  the search would answer from the source, and everything after it would die with
  ``InFailedSqlTransaction``. The savepoint keeps the failure inside the cache — which
  is the only reason "a broken cache is merely slower" holds for the process and not
  just for the adapter.

Expiry is measured with ``now()``, the transaction's own clock. Inside one
transaction, writing with a lifetime of zero seconds therefore reads back as expired
— which is how the tests make the expiry happen without waiting for it.
"""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.types.json import Jsonb

TABLE = "public.earthx_search_cache"

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


class PostgresSearchCache:
    """Key-value with an expiry, one row per cached answer."""

    def __init__(self, conn: psycopg.AsyncConnection) -> None:
        self._conn = conn

    async def get(self, key: str) -> dict[str, Any] | None:
        """The stored value, or None when it is absent or past its expiry."""
        async with self._conn.transaction(), self._conn.cursor() as cur:
            await cur.execute(_SELECT, (key,))
            row = await cur.fetchone()
        return None if row is None else row[0]

    async def set(self, key: str, value: dict[str, Any], *, ttl_s: float, dataset_id: str) -> None:
        """Store a value for ``ttl_s`` seconds, replacing whatever was under that key."""
        async with self._conn.transaction(), self._conn.cursor() as cur:
            await cur.execute(_UPSERT, (key, dataset_id, Jsonb(value), float(ttl_s)))

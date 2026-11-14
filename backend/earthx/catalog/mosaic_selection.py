"""The selection behind a mosaic tile URL (M5-30b part 3, adr/0032 §10.2 option U1).

A selection is a fixed list of scenes of one dataset, read from the named assets. Its id is the hash of that content,
so the same content has the same id and one id never means another picture: the URL stays the whole description of
the image (adr/0006 §5), although the list no longer sits in it. What a selection stores besides the content is what the
tiles derive from it once (order, outlines, extent); `api` builds that and this module keeps it for seven days.

As the other caches of this package, the functions take the caller's connection, run each statement in a transaction of
its own and leave a failure to the caller. The hourly cleanup of `jobs` deletes expired rows.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

__all__ = ["SELECTION_ID", "TABLE", "TERM_S", "canonical_content", "load", "renew", "save", "selection_id"]

TABLE = "public.earthx_mosaic_selection"

#: Seven days (adr/0032 §10.2); creating a selection that exists moves the end to seven days from then.
TERM_S = 7 * 24 * 60 * 60

#: The shape of an id: 32 lowercase hex characters, the first half of a SHA-256.
SELECTION_ID = re.compile(r"\A[0-9a-f]{32}\Z")

_LOAD = f"SELECT dataset_id, content FROM {TABLE} WHERE selection_id = %s AND expires_at > now()"

_RENEW = f"""
UPDATE {TABLE} SET expires_at = now() + make_interval(secs => %s)
WHERE selection_id = %s AND expires_at > now()
RETURNING 1
"""

_SAVE = f"""
INSERT INTO {TABLE} (selection_id, dataset_id, content, expires_at)
VALUES (%s, %s, %s, now() + make_interval(secs => %s))
ON CONFLICT (selection_id) DO UPDATE
    SET dataset_id = EXCLUDED.dataset_id,
        content    = EXCLUDED.content,
        expires_at = EXCLUDED.expires_at,
        created_at = now()
"""


def canonical_content(dataset_id: str, assets: Iterable[str], items: Iterable[str]) -> str:
    """The content of a selection as JSON: sorted keys, compact, the assets and the item ids sorted and each once."""
    return json.dumps(
        {"dataset": dataset_id, "assets": sorted(set(assets)), "items": sorted(set(items))},
        sort_keys=True,
        separators=(",", ":"),
    )


def selection_id(dataset_id: str, assets: Iterable[str], items: Iterable[str]) -> str:
    """The id of this content: the first 32 hex characters of the SHA-256 of :func:`canonical_content`."""
    return hashlib.sha256(canonical_content(dataset_id, assets, items).encode("utf-8")).hexdigest()[:32]


async def load(conn: psycopg.AsyncConnection, selection: str) -> tuple[str, dict[str, Any]] | None:
    """``(dataset id, content)`` of an unexpired selection, or ``None`` where it never existed or has expired."""
    async with conn.transaction(), conn.cursor() as cur:
        await cur.execute(_LOAD, (selection,))
        row = await cur.fetchone()
    return None if row is None else (row[0], row[1])


async def renew(conn: psycopg.AsyncConnection, selection: str, *, term_s: float = TERM_S) -> bool:
    """Move the end of an unexpired selection to ``term_s`` from now; ``False`` if there is none to move."""
    async with conn.transaction(), conn.cursor() as cur:
        await cur.execute(_RENEW, (float(term_s), selection))
        return await cur.fetchone() is not None


async def save(
    conn: psycopg.AsyncConnection, selection: str, dataset_id: str, content: dict[str, Any], *, term_s: float = TERM_S
) -> None:
    """Store a selection, replacing a row of the same id (an expired one that the cleanup has not reached yet)."""
    async with conn.transaction(), conn.cursor() as cur:
        await cur.execute(_SAVE, (selection, dataset_id, Jsonb(content), float(term_s)))

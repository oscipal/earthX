"""Permalinks: an order and a view under an identifier of their own (M4-19e; adr/0015 §13).

A permalink is made when someone presses "Share", not with a job, and holds no job, no result
and no link into the object store (Q9). The identifier is random, never derived from the order
(Q8). The order carries the area, so a row is personal data: it is never logged, and it lives a
fixed term from its creation. Looking at it does not lengthen that; the hourly cleanup
(:mod:`earthx.jobs.cleanup`) deletes what has expired.

Whoever creates a permalink gets a key once, to delete it before its term ends. Only the SHA-256
of the key is stored. A wrong key, an unknown identifier and an expired one are the same ``False``
or ``None`` here, so no caller can tell them apart.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

__all__ = ["TTL", "Created", "create", "delete", "is_permalink_id", "read"]

#: How long a permalink lives, counted from its creation (adr/0015 §13; Otto, 20.10.2026).
TTL = timedelta(days=30)

_ID = re.compile(r"[A-Za-z0-9_-]{22}")


@dataclass(frozen=True, slots=True)
class Created:
    permalink_id: str
    expires_at: datetime
    delete_key: str


def is_permalink_id(value: str) -> bool:
    return _ID.fullmatch(value) is not None


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def create(conn: psycopg.Connection, body: dict[str, Any]) -> Created:
    """Store ``body`` and return its identifier and the key that deletes it (shown nowhere else)."""
    permalink_id = secrets.token_urlsafe(16)
    delete_key = secrets.token_urlsafe(16)
    row = conn.execute(
        """
        INSERT INTO public.earthx_permalink (permalink_id, body, delete_key_hash, expires_at)
        VALUES (%s, %s, %s, clock_timestamp() + %s)
        RETURNING expires_at
        """,
        (permalink_id, Jsonb(body), _hash(delete_key), TTL),
    ).fetchone()
    assert row is not None
    return Created(permalink_id, row[0], delete_key)


def read(conn: psycopg.Connection, permalink_id: str) -> tuple[dict[str, Any], datetime] | None:
    """The body and the expiry of a permalink that has not expired, else ``None``."""
    row = conn.execute(
        "SELECT body, expires_at FROM public.earthx_permalink WHERE permalink_id = %s AND expires_at > clock_timestamp()",
        (permalink_id,),
    ).fetchone()
    return None if row is None else (row[0], row[1])


def delete(conn: psycopg.Connection, permalink_id: str, delete_key: str) -> bool:
    """Delete a permalink that has not expired, if ``delete_key`` is its key."""
    row = conn.execute(
        "SELECT delete_key_hash FROM public.earthx_permalink WHERE permalink_id = %s AND expires_at > clock_timestamp()",
        (permalink_id,),
    ).fetchone()
    if row is None or not hmac.compare_digest(row[0], _hash(delete_key)):
        return False
    conn.execute("DELETE FROM public.earthx_permalink WHERE permalink_id = %s", (permalink_id,))
    return True

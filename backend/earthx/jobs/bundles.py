"""Bundles: the list of jobs behind "Download all (ZIP)" under an identifier of its own (UI-01e; adr/0015 §13).

A bundle is made when someone presses "Download all (ZIP)" and holds the ``jobID``s only: no area, no
title, no byte (the ZIP is laid out when it is read, from the state of the jobs). A ``jobID`` is the way to a
result (Q9), so a row is personal data: it is never logged. The identifier is random, never derived from the
jobs, so two equal lists have two identifiers.

Its term is the earliest end of the jobs that went in, fixed at creation. Looking at it does not lengthen that;
the hourly cleanup (:mod:`earthx.jobs.cleanup`) deletes what has expired, the row whole. An unknown, a
malformed and an expired identifier are the same ``None`` here, so no caller can tell them apart.
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime

import psycopg
from psycopg.types.json import Jsonb

__all__ = ["MAX_PARTS", "create", "is_bundle_id", "read"]

#: How many jobs a bundle holds: the largest batch (M4-13c-4).
MAX_PARTS = 25

_ID = re.compile(r"[A-Za-z0-9_-]{22}")


def is_bundle_id(value: str) -> bool:
    return _ID.fullmatch(value) is not None


def create(conn: psycopg.Connection, job_ids: list[str], expires_at: datetime) -> str:
    """Store ``job_ids`` until ``expires_at`` and return the identifier of the bundle."""
    bundle_id = secrets.token_urlsafe(16)
    conn.execute(
        "INSERT INTO public.earthx_bundle (bundle_id, job_ids, expires_at) VALUES (%s, %s, %s)",
        (bundle_id, Jsonb(job_ids), expires_at),
    )
    return bundle_id


def read(conn: psycopg.Connection, bundle_id: str) -> tuple[list[str], datetime] | None:
    """The ``jobID``s and the expiry of a bundle that has not expired, else ``None``."""
    row = conn.execute(
        "SELECT job_ids, expires_at FROM public.earthx_bundle WHERE bundle_id = %s AND expires_at > clock_timestamp()",
        (bundle_id,),
    ).fetchone()
    return None if row is None else (row[0], row[1])

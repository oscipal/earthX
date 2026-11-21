"""Rows of ``earthx_listed_entry`` that no hand entry makes, for the tests of M5-40.

A harvested row has another ``source_id`` than ``listed`` (M5-19 and M5-21 write them; nothing does yet), so a test puts
one in by hand. The values are invented.
"""

from __future__ import annotations

import json
from typing import Any

import psycopg

from earthx.catalog.listed import content_sha256


def insert_row(
    conn: psycopg.Connection,
    dataset_id: str,
    *,
    source_id: str = "src-1",
    source_key: str | None = None,
    state: str = "published",
    title: str = "Harvested example",
    publisher: str = "Example Harvest Office",
    host: str = "harvest.example.org",
    bbox: tuple[float, float, float, float] = (11.2, 48.2, 11.6, 48.4),
) -> None:
    """One published (or ``state``) row of a source other than ``listed``, with every field a published row needs."""
    content: dict[str, Any] = {"type": "Collection", "id": dataset_id, "title": title, "earthx:entry": "listed"}
    conn.execute(
        """
        INSERT INTO public.earthx_listed_entry (
            dataset_id, source_id, source_key, state, content, content_sha256, sort_title, footprint, regions,
            keywords, data_kind, category, account, delivery, publisher, link_host, verdict, waiting_reason, duplicate_of
        ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, lower(%s), ST_MakeEnvelope(%s, %s, %s, %s, 4326), '{}',
                  '{harvested}', 'vector', 'other', 'none', 'download', %s, %s,
                  CASE %s WHEN 'needs_rule' THEN 'needs_rule' WHEN 'not_geodata' THEN 'not_geodata'
                      WHEN 'in_review' THEN 'ok' END,
                  CASE WHEN %s = 'needs_rule' THEN 'not_granted' END, CASE WHEN %s = 'duplicate' THEN 'main-entry' END)
        """,
        (
            dataset_id,
            source_id,
            source_key or dataset_id,
            state,
            json.dumps(content),
            content_sha256(content),
            title,
            *bbox,
            publisher,
            host,
            state,
            state,
            state,
        ),
    )

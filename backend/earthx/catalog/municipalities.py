"""The municipalities of Switzerland for place texts (M5-20 plan §13b, F9 = 1): ``backend/catalog/municipalities.json``.

Written by ``scripts/write-municipality-outlines.py`` from swissBOUNDARIES3D (© swisstopo, free use with attribution,
opendata.swiss ``terms_by``; graded by Otto, 19.11.2026): per municipality its code ``CH-<canton>-<BFS number>``, its
official name, its canton and a simplified outline. The file in the repository holds none until Otto runs the script
on a local copy of the data. ``catalog-load`` writes them into ``earthx_municipality`` (migration ``033``); the report
of the harvest reads the names. A municipality is never a region of an entry: an entry it names gets the regions of
its canton and state, and the municipality's outline as footprint.
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import psycopg

from earthx.catalog.datasets import CATALOG_DIR
from earthx.catalog.entry_files import EntryFileError
from earthx.catalog.listed import load_regions

__all__ = [
    "MUNICIPALITIES_FILE",
    "MUNICIPALITY_CODE",
    "Municipality",
    "load_municipalities",
    "read_municipalities",
    "write_municipalities",
]

MUNICIPALITIES_FILE = CATALOG_DIR / "municipalities.json"
#: ``CH-ZH-0261``: state, canton, BFS number with four digits.
MUNICIPALITY_CODE = re.compile(r"[A-Z]{2}-[A-Z]{2}-\d{4}")
_KEYS = frozenset({"source", "release", "file", "sha256", "script", "attribution", "tolerance_deg", "municipalities"})
_FIELDS = frozenset({"code", "name", "canton", "outline"})


@dataclass(frozen=True, slots=True)
class Municipality:
    code: str
    name: str
    canton: str
    outline: Mapping[str, Any]


def read_municipalities(path: Path, cantons: Collection[str]) -> tuple[Municipality, ...]:
    """The municipalities of ``path``, checked against the subdivision codes ``cantons`` of ``regions.json``."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EntryFileError(f"{path.name}: cannot be read as JSON ({type(error).__name__})") from None
    if not isinstance(data, dict) or set(data) != _KEYS or not isinstance(data["municipalities"], list):
        raise EntryFileError(f"{path.name}: holds exactly {', '.join(sorted(_KEYS))}")
    found = []
    for index, item in enumerate(data["municipalities"]):
        where = f"{path.name}: municipalities[{index}]"
        if not isinstance(item, dict) or set(item) != _FIELDS:
            raise EntryFileError(f"{where} holds exactly {', '.join(sorted(_FIELDS))}")
        code, canton, name, outline = item["code"], item["canton"], item["name"], item["outline"]
        if not isinstance(code, str) or not MUNICIPALITY_CODE.fullmatch(code):
            raise EntryFileError(f"{where}.code is <state>-<canton>-<BFS number of four digits>")
        if canton not in cantons or not code.startswith(f"{canton}-"):
            raise EntryFileError(f"{where}.canton is the subdivision of regions.json its code begins with")
        if not isinstance(name, str) or not name.strip():
            raise EntryFileError(f"{where}.name is a non-blank text")
        if not isinstance(outline, dict) or outline.get("type") not in ("Polygon", "MultiPolygon"):
            raise EntryFileError(f"{where}.outline is a Polygon or MultiPolygon")
        found.append(Municipality(code, name, canton, outline))
    if len({m.code for m in found}) != len(found):
        raise EntryFileError(f"{path.name}: a municipality code stands twice")
    return tuple(found)


@cache
def load_municipalities() -> tuple[Municipality, ...]:
    """The municipalities of the image, read once per process."""
    cantons = {region.code for region in load_regions() if region.level == "subdivision"}
    return read_municipalities(MUNICIPALITIES_FILE, cantons)


def write_municipalities(conn: psycopg.Connection, municipalities: Sequence[Municipality]) -> int:
    """Bring ``earthx_municipality`` in line with ``municipalities``; returns how many rows changed."""
    # One statement for all of them: a round trip per municipality cost a third of a second per run (M5-66).
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO public.earthx_municipality AS stored (code, canton, name, outline)
            SELECT m.code, m.canton, m.name, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(m.outline), 4326))
            FROM unnest(%s::text[], %s::text[], %s::text[], %s::text[]) AS m(code, canton, name, outline)
            ON CONFLICT (code) DO UPDATE SET canton = EXCLUDED.canton, name = EXCLUDED.name,
                outline = EXCLUDED.outline
            WHERE (stored.canton, stored.name, ST_AsBinary(stored.outline))
                  IS DISTINCT FROM (EXCLUDED.canton, EXCLUDED.name, ST_AsBinary(EXCLUDED.outline))
            """,
            (
                [item.code for item in municipalities],
                [item.canton for item in municipalities],
                [item.name for item in municipalities],
                [json.dumps(item.outline) for item in municipalities],
            ),
        )
        changed = cur.rowcount
        cur.execute(
            "DELETE FROM public.earthx_municipality WHERE NOT (code = ANY(%s))", ([m.code for m in municipalities],)
        )
        changed += cur.rowcount
    return changed

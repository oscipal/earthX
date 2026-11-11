"""Reduce the Natural Earth countries to what the search text needs: names and coarse outlines.

    python scripts/write-place-outlines.py <ne_50m_admin_0_countries.geojson>

Reads a local copy of "Admin 0 - Countries" at 1:50m (Natural Earth, public domain) and writes
``backend/catalog/places.json``: per country the code, the English and German name, the continent and the outline
simplified to ``TOLERANCE_DEG`` (docs/plans/m5/m5-22-suche-lexikalisch.md F4). The file is checked against the
release and checksum below before anything is written, so the output always names what it was made from.

The script fetches nothing: download the file of the pinned release yourself, from the tag of the repository
``nvkelso/natural-earth-vector`` (``geojson/ne_50m_admin_0_countries.geojson``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

RELEASE = "5.1.2"
SOURCE_FILE = "ne_50m_admin_0_countries.geojson"
SOURCE_SHA256 = "3e458fc036ad0a66411f2c1e6cac49c5d7bfb81cb1123bc513b22511a2b7fdeb"
TOLERANCE_DEG = 0.1
DECIMALS = 2
OUTPUT = Path(__file__).resolve().parents[1] / "backend" / "catalog" / "places.json"

# Natural Earth names the continents in English only. "Seven seas (open ocean)" holds islands, no continent.
CONTINENTS_DE = {
    "Africa": "Afrika",
    "Antarctica": "Antarktis",
    "Asia": "Asien",
    "Europe": "Europa",
    "North America": "Nordamerika",
    "Oceania": "Ozeanien",
    "South America": "Südamerika",
}


def _rounded(value: object, decimals: int) -> object:
    if isinstance(value, float):
        return round(value, decimals)
    if isinstance(value, (list, tuple)):
        return [_rounded(item, decimals) for item in value]
    return value


def _coarse(outline: BaseGeometry) -> dict:
    """The outline with ``DECIMALS`` decimals, repaired where rounding made it cross itself, or with two more decimals
    where that leaves no valid area (the Vatican)."""
    for decimals in (DECIMALS, DECIMALS + 2):
        geometry = mapping(outline)
        coarse = shape({"type": geometry["type"], "coordinates": _rounded(geometry["coordinates"], decimals)})
        if not coarse.is_valid:
            coarse = coarse.buffer(0)
        if coarse.is_valid and coarse.area > 0 and coarse.geom_type in ("Polygon", "MultiPolygon"):
            return mapping(coarse)
    raise SystemExit(f"an outline has no valid area even with {DECIMALS + 2} decimals")


def reduce(source: dict) -> dict:
    countries = []
    for feature in source["features"]:
        props = feature["properties"]
        outline = shape(feature["geometry"]).simplify(TOLERANCE_DEG, preserve_topology=True)
        if outline.is_empty:
            raise SystemExit(f"{props['ADMIN']}: the outline vanished at {TOLERANCE_DEG}°")
        geometry = _coarse(outline)
        countries.append(
            {
                "code": props["ADM0_A3"],
                "en": props["NAME_EN"],
                "de": props["NAME_DE"],
                "continent": props["CONTINENT"] if props["CONTINENT"] in CONTINENTS_DE else None,
                "outline": geometry,
            }
        )
    countries.sort(key=lambda country: country["code"])
    return {
        "source": "Natural Earth, 1:50m Cultural Vectors, Admin 0 - Countries (public domain)",
        "release": RELEASE,
        "file": SOURCE_FILE,
        "sha256": SOURCE_SHA256,
        "script": "scripts/write-place-outlines.py",
        "tolerance_deg": TOLERANCE_DEG,
        "continents": CONTINENTS_DE,
        "countries": countries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path, help=f"a local copy of {SOURCE_FILE}, release {RELEASE}")
    args = parser.parse_args()
    raw = args.source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != SOURCE_SHA256:
        print(f"{args.source.name}: SHA-256 {digest} is not that of release {RELEASE}", file=sys.stderr)
        return 1
    reduced = reduce(json.loads(raw))
    OUTPUT.write_text(json.dumps(reduced, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{OUTPUT.name}: {len(reduced['countries'])} countries, {OUTPUT.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

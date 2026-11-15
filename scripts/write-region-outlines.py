"""Reduce the Natural Earth states and subdivisions to the regions of listed entries: codes and outlines.

    python scripts/write-region-outlines.py <ne_50m_admin_0_countries.geojson> <ne_10m_admin_1_states_provinces.geojson>

Reads local copies of "Admin 0 - Countries" at 1:50m and "Admin 1 - States, Provinces" at 1:10m (Natural Earth, public
domain) and writes ``backend/catalog/regions.json``: every state with an ISO 3166-1 code and the subdivisions of
``SUBDIVIDED`` with their ISO 3166-2 code, each with its name and an outline simplified to the tolerance of its level
(adr/0033 §5, M5-40 plan F8). Both files are checked against the release and checksums below before anything is
written, so the output always names what it was made from.

The script fetches nothing: download the files of the pinned release yourself, from the tag of the repository
``nvkelso/natural-earth-vector`` (``geojson/<file>``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

RELEASE = "5.1.2"
STATES_FILE = "ne_50m_admin_0_countries.geojson"
STATES_SHA256 = "3e458fc036ad0a66411f2c1e6cac49c5d7bfb81cb1123bc513b22511a2b7fdeb"
SUBDIVISIONS_FILE = "ne_10m_admin_1_states_provinces.geojson"
SUBDIVISIONS_SHA256 = "22d0e3ad85eb3e27f17cabf8ba2d50e554fbc27a87796ff891d958185da62fb5"
#: The states whose subdivisions (Länder, Bundesländer, Kantone, Gemeinden of Liechtenstein) are regions too.
SUBDIVIDED = ("AT", "CH", "DE", "LI")
#: Tolerance in degrees and decimals kept, per level; small enough that no municipality of Liechtenstein vanishes.
LEVELS = {"state": (0.02, 3), "subdivision": (0.002, 4)}
OUTPUT = Path(__file__).resolve().parents[1] / "backend" / "catalog" / "regions.json"


def _rounded(value: object, decimals: int) -> object:
    if isinstance(value, float):
        return round(value, decimals)
    if isinstance(value, (list, tuple)):
        return [_rounded(item, decimals) for item in value]
    return value


def _outline(geometry: BaseGeometry, level: str, code: str) -> dict:
    tolerance, decimals = LEVELS[level]
    simple = geometry.simplify(tolerance, preserve_topology=True)
    for places in (decimals, decimals + 2):
        raw = mapping(simple)
        coarse = shape({"type": raw["type"], "coordinates": _rounded(raw["coordinates"], places)})
        if not coarse.is_valid:
            coarse = coarse.buffer(0)
        if coarse.is_valid and coarse.area > 0 and coarse.geom_type in ("Polygon", "MultiPolygon"):
            return mapping(coarse)
    raise SystemExit(f"{code}: the outline has no valid area even with {decimals + 2} decimals")


def _state_code(props: dict) -> str | None:
    """ISO 3166-1 alpha-2; Natural Earth writes ``-99`` for France and Norway in ``ISO_A2`` and the code in
    ``ISO_A2_EH``. A territory without any code (Somaliland, Northern Cyprus, Siachen) is no region."""
    for key in ("ISO_A2", "ISO_A2_EH"):
        if len(props[key]) == 2 and props[key].isalpha():
            return props[key]
    return None


def reduce(states: dict, subdivisions: dict) -> dict:
    parts: dict[str, list[BaseGeometry]] = {}
    names: dict[str, str] = {}
    for feature in states["features"]:
        code = _state_code(feature["properties"])
        if code is None:
            continue
        parts.setdefault(code, []).append(shape(feature["geometry"]))
        # A code with several features (Australia and its territories) keeps the name of the sovereign part.
        if feature["properties"]["ISO_A2"] == code or code not in names:
            names[code] = feature["properties"]["NAME_EN"]
    regions = [
        {"code": code, "name": names[code], "level": "state", "outline": _outline(unary_union(parts[code]), "state", code)}
        for code in sorted(parts)
    ]
    found = []
    for feature in subdivisions["features"]:
        props = feature["properties"]
        if props["iso_a2"] not in SUBDIVIDED:
            continue
        code = props["iso_3166_2"]
        if not code.startswith(f"{props['iso_a2']}-"):
            raise SystemExit(f"{props['name']}: no ISO 3166-2 code")
        found.append(
            {"code": code, "name": props["name"], "level": "subdivision",
             "outline": _outline(shape(feature["geometry"]), "subdivision", code)}
        )
    if len({region["code"] for region in found}) != len(found):
        raise SystemExit("a subdivision code occurs twice")
    regions.extend(sorted(found, key=lambda region: region["code"]))
    return {
        "source": "Natural Earth, Admin 0 - Countries 1:50m and Admin 1 - States, Provinces 1:10m (public domain)",
        "release": RELEASE,
        "files": {STATES_FILE: STATES_SHA256, SUBDIVISIONS_FILE: SUBDIVISIONS_SHA256},
        "script": "scripts/write-region-outlines.py",
        "tolerance_deg": {level: tolerance for level, (tolerance, _) in LEVELS.items()},
        "regions": regions,
    }


def _read(path: Path, expected: str) -> dict:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected:
        raise SystemExit(f"{path.name}: SHA-256 {digest} is not that of release {RELEASE}")
    return json.loads(raw)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("states", type=Path, help=f"a local copy of {STATES_FILE}, release {RELEASE}")
    parser.add_argument("subdivisions", type=Path, help=f"a local copy of {SUBDIVISIONS_FILE}, release {RELEASE}")
    args = parser.parse_args()
    reduced = reduce(_read(args.states, STATES_SHA256), _read(args.subdivisions, SUBDIVISIONS_SHA256))
    OUTPUT.write_text(json.dumps(reduced, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{OUTPUT.name}: {len(reduced['regions'])} regions, {OUTPUT.stat().st_size} bytes", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

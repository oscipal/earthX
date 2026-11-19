"""Reduce the municipalities of swissBOUNDARIES3D to names, cantons and outlines for place texts (M5-20 F9 = 1).

    python scripts/write-municipality-outlines.py <swissBOUNDARIES3D.gpkg> --release <year-month>

Reads a local copy of swissBOUNDARIES3D (swisstopo, GeoPackage, LV95) and writes ``backend/catalog/municipalities.json``:
per municipality its code ``CH-<canton>-<BFS number>``, its official name, its canton and its outline in WGS84,
simplified and rounded. Licence: free use with attribution "© swisstopo" (opendata.swiss terms_by), graded by Otto on
19.11.2026; the attribution stands in the file and in backend/THIRD_PARTY_NOTICES.md.

The script fetches nothing: download the GeoPackage of the current release from swisstopo yourself. The names of the
layer and its fields are from swisstopo's documentation [not checked against a file in a session]; where a name
differs, the script stops and lists what the file holds, and ``--layer``/``--kind`` set them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

OUTPUT = Path(__file__).resolve().parents[1] / "backend" / "catalog" / "municipalities.json"
#: The cantons by their BFS number (Bundesamt für Statistik), as ISO 3166-2 codes.
CANTONS = {
    1: "ZH", 2: "BE", 3: "LU", 4: "UR", 5: "SZ", 6: "OW", 7: "NW", 8: "GL", 9: "ZG", 10: "FR", 11: "SO", 12: "BS",
    13: "BL", 14: "SH", 15: "AR", 16: "AI", 17: "SG", 18: "GR", 19: "AG", 20: "TG", 21: "TI", 22: "VD", 23: "VS",
    24: "NE", 25: "GE", 26: "JU",
}
#: About 100 m: enough to find a municipality, small enough for the file (some 2 100 of them).
TOLERANCE_DEG = 0.001
DECIMALS = 4
_ENVELOPE_BYTES = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}


def gpkg_geometry(blob: bytes) -> BaseGeometry:
    """The geometry of a GeoPackage blob: its header (magic, flags, SRS, envelope) dropped, the WKB read."""
    if blob[:2] != b"GP":
        raise ValueError("no GeoPackage geometry")
    flags = blob[3]
    envelope = _ENVELOPE_BYTES[(flags >> 1) & 0b111]
    return shapely.force_2d(shapely.from_wkb(blob[8 + envelope :]))


def _columns(db: sqlite3.Connection, table: str) -> dict[str, str]:
    return {row[1].lower(): row[1] for row in db.execute(f'PRAGMA table_info("{table}")')}


def read(path: Path, layer: str, kind: str | None) -> dict[int, tuple[str, int, list[BaseGeometry]]]:
    """BFS number → (name, canton number, parts in LV95) of the layer ``layer``, only rows of ``kind`` where set."""
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    tables = {row[0].lower(): row[0] for row in db.execute("SELECT table_name FROM gpkg_contents")}
    if layer.lower() not in tables:
        raise SystemExit(f"no layer {layer!r}; the file holds: {', '.join(sorted(tables.values()))}")
    table = tables[layer.lower()]
    srs = db.execute("SELECT srs_id FROM gpkg_geometry_columns WHERE table_name = ?", (table,)).fetchone()
    if srs is None or srs[0] != 2056:
        raise SystemExit(f"layer {table}: SRS {srs and srs[0]} is not LV95 (EPSG:2056)")
    geometry = db.execute("SELECT column_name FROM gpkg_geometry_columns WHERE table_name = ?", (table,)).fetchone()[0]
    columns = _columns(db, table)
    needed = ["bfs_nummer", "name", "kantonsnummer"] + (["objektart"] if kind else [])
    if missing := [name for name in needed if name not in columns]:
        raise SystemExit(f"layer {table} lacks {', '.join(missing)}; it holds: {', '.join(sorted(columns.values()))}")
    query = (
        f'SELECT "{columns["bfs_nummer"]}", "{columns["name"]}", "{columns["kantonsnummer"]}", "{geometry}"'
        f' FROM "{table}"' + (f' WHERE "{columns["objektart"]}" = ?' if kind else "")
    )
    found: dict[int, tuple[str, int, list[BaseGeometry]]] = {}
    for bfs, name, canton, blob in db.execute(query, (kind,) if kind else ()):
        if blob is None or canton not in CANTONS:
            continue
        entry = found.setdefault(int(bfs), (str(name), int(canton), []))
        entry[2].append(gpkg_geometry(blob))
    if not found:
        raise SystemExit(f"layer {table}: no municipality" + (f" of kind {kind!r}" if kind else ""))
    return found


def _rounded(value: object) -> object:
    if isinstance(value, float):
        return round(value, DECIMALS)
    if isinstance(value, (list, tuple)):
        return [_rounded(item) for item in value]
    return value


def outline(parts: list[BaseGeometry], transformer: Transformer, code: str) -> dict:
    lv95 = unary_union(parts)
    wgs84 = shapely.transform(lv95, lambda xy: np.column_stack(transformer.transform(xy[:, 0], xy[:, 1])))
    simple = wgs84.simplify(TOLERANCE_DEG, preserve_topology=True)
    raw = mapping(simple)
    coarse = shape({"type": raw["type"], "coordinates": _rounded(raw["coordinates"])})
    if not coarse.is_valid:
        coarse = coarse.buffer(0)
    if not coarse.is_valid or coarse.is_empty or coarse.geom_type not in ("Polygon", "MultiPolygon"):
        raise SystemExit(f"{code}: no valid outline after simplifying")
    return mapping(coarse)


def reduce(found: dict[int, tuple[str, int, list[BaseGeometry]]], release: str, path: Path, sha256: str) -> dict:
    transformer = Transformer.from_crs("EPSG:2056", "EPSG:4326", always_xy=True)
    municipalities = []
    for bfs in sorted(found):
        name, canton_number, parts = found[bfs]
        canton = f"CH-{CANTONS[canton_number]}"
        code = f"{canton}-{bfs:04d}"
        municipalities.append({"code": code, "name": name, "canton": canton, "outline": outline(parts, transformer, code)})
    return {
        "source": "swisstopo, swissBOUNDARIES3D, municipalities (Hoheitsgebiet)",
        "release": release,
        "file": path.name,
        "sha256": sha256,
        "script": "scripts/write-municipality-outlines.py",
        "attribution": "© swisstopo",
        "tolerance_deg": TOLERANCE_DEG,
        "municipalities": municipalities,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("gpkg", type=Path, help="a local copy of swissBOUNDARIES3D as GeoPackage")
    parser.add_argument("--release", required=True, help="the release the file is of, as swisstopo names it")
    parser.add_argument("--layer", default="tlm_hoheitsgebiet", help="the layer of the municipalities")
    parser.add_argument("--kind", default="Gemeindegebiet", help="the value of objektart of a municipality; '' for all")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    sha256 = hashlib.sha256(args.gpkg.read_bytes()).hexdigest()
    reduced = reduce(read(args.gpkg, args.layer, args.kind or None), args.release, args.gpkg, sha256)
    args.output.write_text(json.dumps(reduced, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    count = len(reduced["municipalities"])
    print(f"{args.output.name}: {count} municipalities, {args.output.stat().st_size} bytes", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""scripts/write-municipality-outlines.py against a synthetic GeoPackage (M5-20 F9 = 1); nothing is downloaded."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import struct
import sys
from pathlib import Path

import pytest
import shapely
from shapely.geometry import Polygon

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "write-municipality-outlines.py"
_spec = importlib.util.spec_from_file_location("write_municipality_outlines", SCRIPT)
assert _spec is not None and _spec.loader is not None
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)


def _blob(polygon: Polygon) -> bytes:
    """A GeoPackage geometry: header with an XY envelope (flags 0b0011: little endian, envelope 32 bytes), then WKB
    with Z, as swissBOUNDARIES3D (3D) writes it."""
    minx, miny, maxx, maxy = polygon.bounds
    header = b"GP" + bytes([0, 0b0011]) + struct.pack("<i", 2056) + struct.pack("<4d", minx, maxx, miny, maxy)
    return header + shapely.to_wkb(shapely.force_3d(polygon, 500.0), flavor="iso")


def _gpkg(path: Path, rows: list[tuple[int, str, int, str, Polygon]], *, srs: int = 2056) -> Path:
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE gpkg_contents (table_name TEXT)")
    db.execute("CREATE TABLE gpkg_geometry_columns (table_name TEXT, column_name TEXT, srs_id INTEGER)")
    db.execute("INSERT INTO gpkg_contents VALUES ('TLM_HOHEITSGEBIET')")
    db.execute("INSERT INTO gpkg_geometry_columns VALUES ('TLM_HOHEITSGEBIET', 'geom', ?)", (srs,))
    db.execute(
        "CREATE TABLE TLM_HOHEITSGEBIET (BFS_NUMMER INTEGER, NAME TEXT, KANTONSNUMMER INTEGER, OBJEKTART TEXT, geom BLOB)"
    )
    for bfs, name, canton, kind, polygon in rows:
        db.execute("INSERT INTO TLM_HOHEITSGEBIET VALUES (?, ?, ?, ?, ?)", (bfs, name, canton, kind, _blob(polygon)))
    db.commit()
    db.close()
    return path


def _square(east: float, north: float, size: float = 2000.0) -> Polygon:
    return Polygon([(east, north), (east + size, north), (east + size, north + size), (east, north + size)])


def test_municipalities_come_out_in_wgs84_with_their_canton(tmp_path: Path) -> None:
    rows = [
        (351, "Bern", 2, "Gemeindegebiet", _square(2_599_000, 1_199_000)),
        # A municipality in two parts is one.
        (261, "Zürich", 1, "Gemeindegebiet", _square(2_682_000, 1_247_000)),
        (261, "Zürich", 1, "Gemeindegebiet", _square(2_685_000, 1_247_000)),
        # A lake share is no municipality.
        (9073, "Bielersee", 2, "Kantonsgebiet", _square(2_580_000, 1_215_000)),
    ]
    found = script.read(_gpkg(tmp_path / "s.gpkg", rows), "tlm_hoheitsgebiet", "Gemeindegebiet")
    reduced = script.reduce(found, "2025", tmp_path / "s.gpkg", "0" * 64)
    codes = [(m["code"], m["name"], m["canton"]) for m in reduced["municipalities"]]
    assert codes == [("CH-ZH-0261", "Zürich", "CH-ZH"), ("CH-BE-0351", "Bern", "CH-BE")]
    bern = shapely.geometry.shape(reduced["municipalities"][1]["outline"])
    # LV95 2 600 000 / 1 200 000 is the old observatory of Bern, 7.4386° E 46.9511° N.
    assert bern.contains(shapely.Point(7.4386, 46.9511))
    assert reduced["attribution"] == "© swisstopo" and reduced["release"] == "2025"
    json.dumps(reduced)


def test_a_layer_or_field_that_is_not_there_names_what_is(tmp_path: Path) -> None:
    path = _gpkg(tmp_path / "s.gpkg", [(351, "Bern", 2, "Gemeindegebiet", _square(2_599_000, 1_199_000))])
    with pytest.raises(SystemExit, match="the file holds: TLM_HOHEITSGEBIET"):
        script.read(path, "tlm_gemeinde", None)


def test_another_reference_system_is_refused(tmp_path: Path) -> None:
    path = _gpkg(tmp_path / "s.gpkg", [(351, "Bern", 2, "Gemeindegebiet", _square(2_599_000, 1_199_000))], srs=4326)
    with pytest.raises(SystemExit, match="not LV95"):
        script.read(path, "tlm_hoheitsgebiet", None)


def test_no_municipality_of_the_kind(tmp_path: Path) -> None:
    path = _gpkg(tmp_path / "s.gpkg", [(351, "Bern", 2, "Gemeindegebiet", _square(2_599_000, 1_199_000))])
    with pytest.raises(SystemExit, match="no municipality"):
        script.read(path, "tlm_hoheitsgebiet", "Gemeinde")


def test_the_output_loads_with_the_checks_of_the_catalogue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from earthx.catalog.municipalities import read_municipalities

    gpkg = _gpkg(tmp_path / "s.gpkg", [(351, "Bern", 2, "Gemeindegebiet", _square(2_599_000, 1_199_000))])
    output = tmp_path / "municipalities.json"
    monkeypatch.setattr(sys, "argv", ["x", str(gpkg), "--release", "2025", "--output", str(output)])
    assert script.main() == 0
    (item,) = read_municipalities(output, {"CH-BE"})
    assert item.code == "CH-BE-0351"

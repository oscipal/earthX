"""The municipalities of Switzerland for place texts (M5-20 F9 = 1): the file and its checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from earthx.catalog.entry_files import EntryFileError
from earthx.catalog.municipalities import MUNICIPALITIES_FILE, load_municipalities, read_municipalities

SQUARE = {"type": "Polygon", "coordinates": [[[7.4, 46.9], [7.5, 46.9], [7.5, 47.0], [7.4, 47.0], [7.4, 46.9]]]}
CANTONS = {"CH-BE", "CH-ZH"}


def _write(tmp_path: Path, items: list[dict[str, Any]], **head: Any) -> Path:
    data = {
        "source": "swisstopo",
        "release": "2025",
        "file": "x.gpkg",
        "sha256": "0" * 64,
        "script": "scripts/write-municipality-outlines.py",
        "attribution": "© swisstopo",
        "tolerance_deg": 0.001,
        "municipalities": items,
        **head,
    }
    path = tmp_path / "municipalities.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _item(**changes: Any) -> dict[str, Any]:
    return {"code": "CH-BE-0351", "name": "Bern", "canton": "CH-BE", "outline": SQUARE, **changes}


def test_the_shipped_file_is_otto_s_run_of_swissboundaries3d() -> None:
    # Otto ran the script on release 2026-01 (20.11.2026); every municipality of Switzerland, with its attribution.
    head = json.loads(MUNICIPALITIES_FILE.read_text(encoding="utf-8"))
    assert head["attribution"] == "© swisstopo" and head["release"] and len(head["sha256"]) == 64
    municipalities = load_municipalities()
    assert 2000 < len(municipalities) < 2300
    assert {m.canton for m in municipalities} == {f"CH-{c}" for c in "AG AI AR BE BL BS FR GE GL GR JU LU NE NW OW SG SH SO SZ TG TI UR VD VS ZG ZH".split()}


def test_a_municipality_loads(tmp_path: Path) -> None:
    (item,) = read_municipalities(_write(tmp_path, [_item()]), CANTONS)
    assert (item.code, item.name, item.canton) == ("CH-BE-0351", "Bern", "CH-BE")


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"code": "CH-BE-351"}, "BFS number of four digits"),
        ({"code": "CH-ZH-0351"}, "canton is the subdivision"),
        ({"canton": "CH-XX", "code": "CH-XX-0351"}, "canton is the subdivision"),
        ({"name": " "}, "name is a non-blank text"),
        ({"outline": {"type": "Point", "coordinates": [7.4, 46.9]}}, "Polygon or MultiPolygon"),
    ],
)
def test_a_wrong_municipality(tmp_path: Path, changes: dict[str, Any], message: str) -> None:
    with pytest.raises(EntryFileError, match=message):
        read_municipalities(_write(tmp_path, [_item(**changes)]), CANTONS)


def test_a_code_twice(tmp_path: Path) -> None:
    with pytest.raises(EntryFileError, match="stands twice"):
        read_municipalities(_write(tmp_path, [_item(), _item()]), CANTONS)


def test_a_missing_or_unknown_key(tmp_path: Path) -> None:
    with pytest.raises(EntryFileError, match="holds exactly"):
        read_municipalities(_write(tmp_path, [], note="x"), CANTONS)

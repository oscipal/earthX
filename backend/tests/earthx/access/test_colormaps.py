"""The colormaps of the tiles and their list (UI-03d, Otto 2.11.2026).

Every colormap is in one group and has a reversed one; the 35 colour ramps a fresh QGIS brings
(``resources/symbology-style.xml``, release-3_40 at 4178dfd8 and master at 19a6ceae, identical names) are all there; the
two added from seaborn are its tables, with their licence beside them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from earthx.access import colormaps
from earthx.access.colormaps import CLASS_TABLES, COLORMAPS, GROUPS, PREVIEW_STOPS, REVERSED, catalog

#: The `<colorramp>` names of QGIS's default style library, lower case as the tiler names them.
QGIS_DEFAULT_RAMPS = (
    "blues", "brbg", "bugn", "bupu", "gnbu", "greens", "greys", "inferno", "magma", "orrd", "oranges", "prgn", "piyg",
    "plasma", "pubu", "pubugn", "puor", "purd", "purples", "rdbu", "rdgy", "rdpu", "rdylbu", "rdylgn", "reds",
    "spectral", "viridis", "rocket", "mako", "turbo", "cividis", "ylgn", "ylgnbu", "ylorbr", "ylorrd",
)  # fmt: skip

DATA = Path(colormaps.__file__).with_name("colormap_data")


def _base_names() -> set[str]:
    return {name for name in COLORMAPS.list() if not name.endswith(REVERSED) and name not in CLASS_TABLES}


class TestTheGroups:
    def test_every_colormap_is_in_exactly_one_group(self) -> None:
        grouped = [name for members in GROUPS.values() for name in members]
        assert len(grouped) == len(set(grouped))
        assert set(grouped) == _base_names()

    def test_the_groups_are_the_five_of_the_list_in_their_order(self) -> None:
        assert [group["name"] for group in catalog()["groups"]] == ["sequential", "diverging", "cyclic", "qualitative", "other"]


class TestReversed:
    def test_every_colormap_has_a_reversed_one(self) -> None:
        names = set(COLORMAPS.list())
        assert all(f"{name}{REVERSED}" in names for name in _base_names())
        assert all(entry["reversed"] == f"{entry['name']}{REVERSED}" for group in catalog()["groups"] for entry in group["colormaps"])

    @pytest.mark.parametrize("name", ["viridis", "rocket", "cfastie", "schwarzwald"])
    def test_the_reversed_one_is_the_table_the_other_way_round(self, name: str) -> None:
        table, back = COLORMAPS.get(name), COLORMAPS.get(f"{name}{REVERSED}")
        assert [tuple(map(int, table[k])) for k in sorted(table)] == [tuple(map(int, back[k])) for k in sorted(back, reverse=True)]
        # Counter-check: a colormap is not its own reverse.
        assert tuple(map(int, table[min(table)])) != tuple(map(int, back[min(back)]))


class TestQgis:
    def test_every_default_ramp_of_qgis_is_a_colormap_of_the_tiles(self) -> None:
        assert len(QGIS_DEFAULT_RAMPS) == 35
        assert set(QGIS_DEFAULT_RAMPS) <= set(COLORMAPS.list())

    def test_a_name_that_is_none_is_not_there(self) -> None:
        assert "batlow" not in COLORMAPS.list()

    @pytest.mark.parametrize(("name", "first", "last"), [("rocket", (3, 5, 26), (250, 235, 221)), ("mako", (11, 4, 5), (222, 245, 229))])
    def test_the_added_ones_end_where_the_ramps_of_qgis_end(self, name: str, first: tuple, last: tuple) -> None:
        table = COLORMAPS.get(name)
        assert tuple(map(int, table[0][:3])) == first and tuple(map(int, table[255][:3])) == last

    @pytest.mark.parametrize("name", ["rocket", "mako"])
    def test_the_added_ones_say_where_they_come_from_and_their_licence_is_beside_them(self, name: str) -> None:
        data = json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))
        assert data["license"] == "BSD-3-Clause" and "seaborn" in data["source"] and "Waskom" in data["copyright"]
        assert len(data["rgb"]) == 256 and all(0 <= value <= 255 for colour in data["rgb"] for value in colour)
        assert "Michael L. Waskom" in (DATA / "LICENSE-seaborn.txt").read_text(encoding="utf-8")


class TestThePreview:
    def test_each_preview_has_its_stops_from_the_first_colour_to_the_last(self) -> None:
        for group in catalog()["groups"]:
            for entry in group["colormaps"]:
                assert len(entry["colors"]) == PREVIEW_STOPS
                assert all(len(colour) == 7 and colour.startswith("#") for colour in entry["colors"])
        viridis = next(e for g in catalog()["groups"] for e in g["colormaps"] if e["name"] == "viridis")
        assert viridis["colors"][0] == "#440154" and viridis["colors"][-1] == "#fde724"


class TestClassTables:
    """M5-07 plan F4: a class layer is painted with its source's own colours, and no stretch."""

    def test_the_worldcover_table_holds_the_colours_of_the_file(self) -> None:
        table = COLORMAPS.get("esa-worldcover")
        assert sorted(table) == [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100]
        assert tuple(map(int, table[10])) == (0, 100, 0, 255)
        assert tuple(map(int, table[100])) == (250, 230, 160, 255)
        # No data stays see-through.
        assert int(table[0][3]) == 0

    def test_a_class_table_is_no_ramp_of_the_list(self) -> None:
        listed = {entry["name"] for group in catalog()["groups"] for entry in group["colormaps"]}
        names = set(COLORMAPS.list())
        for name in CLASS_TABLES:
            assert name not in listed
            assert f"{name}{REVERSED}" not in names

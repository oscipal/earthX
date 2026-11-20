"""The classes of a band whose values are classes (M5-62): value, name and the colour from the source or the palette."""

from __future__ import annotations

from dataclasses import replace

import pytest

from earthx.catalog.collection import CLASSIFICATION_EXTENSION, to_stac_collection
from earthx.catalog.registry import (
    CLASS_PALETTE,
    MAX_CLASS_NAME_CHARS,
    BandClass,
    BandClasses,
    ClassColours,
    ConfigError,
    MaskClass,
)
from tests.catalog.entries import REGISTRY

WORLDCOVER = [entry for entry in REGISTRY if entry.dataset_id.startswith("esa-worldcover-")]
WORLDCOVER_NAMES = [
    (10, "Tree cover"), (20, "Shrubland"), (30, "Grassland"), (40, "Cropland"), (50, "Built-up"),
    (60, "Bare / sparse vegetation"), (70, "Snow and ice"), (80, "Permanent water bodies"), (90, "Herbaceous wetland"),
    (95, "Mangroves"), (100, "Moss and lichen"),
]  # fmt: skip


def _classes(*names: str, colours: ClassColours = ClassColours.PALETTE, nodata: int | None = None) -> BandClasses:
    return BandClasses(colours, nodata, tuple(BandClass(value, name) for value, name in enumerate(names, start=1)))


@pytest.fixture
def classed(valid_config):
    """The test entry with one band of classes and no unit, ``red``."""
    return replace(valid_config, band_units={**valid_config.band_units, "red": None})


class TestTheEntries:
    @pytest.mark.parametrize("entry", WORLDCOVER, ids=lambda entry: entry.dataset_id)
    def test_worldcover_names_its_classes_and_takes_the_colours_of_its_file(self, entry) -> None:
        classes = entry.band_classes["map"]
        assert classes.colours is ClassColours.FILE
        assert classes.nodata == 0
        assert [(row.value, row.name) for row in classes.rows()] == WORLDCOVER_NAMES
        assert classes.rows()[0].colour == "#006400"
        assert classes.rows()[-1].colour == "#fae6a0"

    def test_both_states_of_worldcover_have_the_same_classes(self) -> None:
        first, second = WORLDCOVER
        assert first.band_classes == second.band_classes

    def test_the_scene_classification_takes_the_palette(self) -> None:
        sentinel = next(entry for entry in REGISTRY if entry.dataset_id == "sentinel-2-c1-l2a")
        rows = sentinel.class_rows("scl")
        assert rows is not None and len(rows) == 11
        assert [row.colour for row in rows] == list(CLASS_PALETTE[:11])
        assert (rows[1].value, rows[1].name) == (2, "Topographic shadows")

    @pytest.mark.parametrize("entry", REGISTRY, ids=lambda entry: entry.dataset_id)
    def test_a_band_without_classes_has_no_rows(self, entry) -> None:
        for key in entry.band_units:
            if key not in entry.band_classes:
                assert entry.class_rows(key) is None


class TestTheRules:
    def test_a_band_with_classes_takes_rows_with_the_palette(self, classed) -> None:
        entry = replace(classed, band_classes={"red": _classes("Water", "Land")})
        assert [(row.value, row.name, row.colour) for row in entry.class_rows("red")] == [
            (1, "Water", CLASS_PALETTE[0]),
            (2, "Land", CLASS_PALETTE[1]),
        ]

    def test_a_colour_by_hand_wins_over_the_palette(self, classed) -> None:
        classes = BandClasses(ClassColours.PALETTE, None, (BandClass(1, "Water", "#0000ff"), BandClass(2, "Land")))
        entry = replace(classed, band_classes={"red": classes})
        assert [row.colour for row in entry.class_rows("red")] == ["#0000ff", CLASS_PALETTE[1]]

    @pytest.mark.parametrize("colours", [ClassColours.FILE, ClassColours.STAC])
    def test_colours_from_the_source_are_given_for_every_class(self, classed, colours) -> None:
        with pytest.raises(ConfigError, match="every class has one"):
            replace(classed, band_classes={"red": _classes("Water", colours=colours)})

    def test_more_classes_than_the_palette_need_colours_of_their_own(self, classed) -> None:
        names = [f"Class {index}" for index in range(len(CLASS_PALETTE) + 1)]
        with pytest.raises(ConfigError, match="more than the palette"):
            replace(classed, band_classes={"red": _classes(*names)})

    @pytest.mark.parametrize(
        ("key", "units"),
        [("nir", None), ("green", None), ("r*", {"r*": None})],
        ids=["no band", "a band with a unit", "a pattern"],
    )
    def test_only_a_band_without_a_unit_has_classes(self, valid_config, key, units) -> None:
        described = {**valid_config.band_descriptions, **{name: "Other" for name in units or {}}}
        entry = replace(valid_config, band_units={**valid_config.band_units, **(units or {})}, band_descriptions=described)
        with pytest.raises(ConfigError):
            replace(entry, band_classes={key: _classes("Water")})

    @pytest.mark.parametrize(
        ("classes", "match"),
        [
            (BandClasses(ClassColours.PALETTE, None, ()), "ascending"),
            (BandClasses(ClassColours.PALETTE, None, (BandClass(2, "A"), BandClass(1, "B"))), "ascending"),
            (BandClasses(ClassColours.PALETTE, None, (BandClass(1, "A"), BandClass(1, "B"))), "ascending"),
            (BandClasses(ClassColours.PALETTE, None, (BandClass(1.5, "A"),)), "whole numbers"),  # type: ignore[arg-type]
            (BandClasses(ClassColours.PALETTE, 1, (BandClass(1, "A"),)), "nodata"),
            (BandClasses(ClassColours.PALETTE, None, (BandClass(1, " "),)), "one-line name"),
            (BandClasses(ClassColours.PALETTE, None, (BandClass(1, "A\nB"),)), "one-line name"),
            (BandClasses(ClassColours.PALETTE, None, (BandClass(1, "A" * (MAX_CLASS_NAME_CHARS + 1)),)), "longer"),
            (BandClasses(ClassColours.FILE, None, (BandClass(1, "A", "#00FF00"),)), "#rrggbb"),
            (BandClasses(ClassColours.FILE, None, (BandClass(1, "A", "green"),)), "#rrggbb"),
            (BandClasses(ClassColours.FILE, None, (BandClass(1, "A", "#00ff00"), BandClass(2, "B", "#00ff00"))), "same colour"),
            (BandClasses(ClassColours.PALETTE, None, (BandClass(1, "A"), BandClass(2, "B", CLASS_PALETTE[0]))), "same colour"),
        ],
        ids=[
            "none", "descending", "twice", "not whole", "nodata a class", "blank name", "two lines", "long name",
            "capitals", "a colour name", "same colour from the file", "same colour as the palette",
        ],
    )  # fmt: skip
    def test_a_wrong_list_of_classes_is_refused(self, classed, classes, match) -> None:
        with pytest.raises(ConfigError, match=match):
            replace(classed, band_classes={"red": classes})

    def test_the_mask_names_the_same_classes_as_the_band(self) -> None:
        worldcover = WORLDCOVER[0]
        renamed = replace(worldcover.mask, classes=(MaskClass(10, "Trees"), *worldcover.mask.classes[1:]))
        with pytest.raises(ConfigError, match="classes of the mask differ"):
            replace(worldcover, mask=renamed)

    def test_the_mask_may_add_the_value_without_a_class(self) -> None:
        sentinel = next(entry for entry in REGISTRY if entry.dataset_id == "sentinel-2-c1-l2a")
        assert sentinel.mask.classes[0] == MaskClass(0, "No data")
        assert sentinel.band_classes["scl"].nodata == 0


class TestTheCollection:
    @pytest.mark.parametrize("entry", WORLDCOVER, ids=lambda entry: entry.dataset_id)
    def test_a_band_of_classes_publishes_them_as_the_classification_extension(self, entry) -> None:
        collection = to_stac_collection(entry)
        assert CLASSIFICATION_EXTENSION in collection["stac_extensions"]
        (band,) = collection["earthx:bands"]
        assert band["classification:classes"][0] == {
            "value": 10, "name": "tree_cover", "title": "Tree cover", "color_hint": "006400",
        }  # fmt: skip
        assert band["classification:classes"][5]["name"] == "bare_sparse_vegetation"

    def test_an_entry_without_classes_names_neither_extension_nor_classes(self, valid_config) -> None:
        collection = to_stac_collection(valid_config)
        assert CLASSIFICATION_EXTENSION not in collection["stac_extensions"]
        assert all("classification:classes" not in band for band in collection["earthx:bands"])

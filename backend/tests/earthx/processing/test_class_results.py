"""M5-62 F9: a job's result keeps the classes of a band of classes only while its values stay those of the source (plan §6),
per band (Otto, 24.11.2026): a step that changes other bands leaves them.

Synthetic ``uint8`` class bands, served like the other core tests. A kept band carries ``classification:classes`` in the
result's ``bands`` and, in a type that holds one, the colour table in the COG; a step that changes values leaves neither.
By the same rule each band says whether it holds the values of the source (M5-68, ``earthx:source_values``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy
import pytest
import rasterio

from earthx.processing import run
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import recipe_of_data, resolved
from tests.earthx.processing.testops import OPERATORS

WIDTH, HEIGHT = 300, 200
CLASSES = [
    {"value": 10, "name": "Tree cover", "colour": "#006400"},
    {"value": 20, "name": "Shrubland", "colour": "#ffbb22"},
    {"value": 60, "name": "Bare / sparse vegetation", "colour": "#b4b4b4"},
]
STAC = [
    {"value": 10, "name": "tree_cover", "title": "Tree cover", "color_hint": "006400"},
    {"value": 20, "name": "shrubland", "title": "Shrubland", "color_hint": "FFBB22"},
    {"value": 60, "name": "bare_sparse_vegetation", "title": "Bare / sparse vegetation", "color_hint": "B4B4B4"},
]


def _classes(width: int, height: int) -> numpy.ndarray:
    rows, cols = numpy.indices((height, width))
    data = numpy.choose((rows + cols) % 3, [10, 20, 60]).astype("uint8")
    data[:8, :8] = 0
    return data


@pytest.fixture(scope="module")
def bands(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("classes")
    return {
        "map": sources.build_band_cog(root / "map.tif", _classes(WIDTH, HEIGHT), scale=None, offset=None),
        "other": sources.build_band_cog(root / "other.tif", _classes(WIDTH, HEIGHT), scale=None, offset=None),
    }


@pytest.fixture(autouse=True)
def served(bands: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return sources.serve({sources.url(name): path for name, path in bands.items()}, monkeypatch)


def _entry(asset: str, classes: list[dict[str, Any]] | None) -> dict[str, Any]:
    entry = resolved("ITEM_A", asset, href=sources.url(asset), scale=None, offset=None)
    entry["bands"] = [{"data_type": "uint8", "nodata": 0, "scale": None, "offset": None}]
    if classes is not None:
        entry["classes"] = classes
    return entry


def _recipe(
    steps: list[dict[str, Any]],
    *,
    dtype: str = "uint8",
    assets: tuple[str, ...] = ("map",),
    classes: list[dict[str, Any]] | None = CLASSES,
    bands: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "recipe_version": 2,
        "inputs": [
            {
                "name": "land",
                "dataset": "synthetic",
                "groups": [["ITEM_A"]],
                "assets": list(assets),
                "resolved": [_entry(asset, classes if asset == "map" else None) for asset in assets],
            }
        ],
        "aoi": sources.whole(WIDTH, HEIGHT),
        "steps": steps,
        "output": {"kind": "raster", "format": "cog", "dtype": dtype, "bands": bands or list(assets)},
    }


def _run(data: dict[str, Any], workdir: Path):
    return run(recipe_of_data(data, OPERATORS), workdir=workdir, progress=lambda done, total: None, operators=OPERATORS)


def _colour_table(path: Path) -> dict[int, tuple[int, int, int, int]] | None:
    with rasterio.open(path) as dataset:
        try:
            return dataset.colormap(1)
        except ValueError:  # rasterio's word for a band without a colour table
            return None


def _band_classes(result) -> list[Any]:
    return [band.get("classification:classes") for band in result.properties["bands"]]


MASK_EQ_20 = {"op": "mask_values", "op_version": 1, "params": {"band": "map", "condition": "eq", "values": [20.0]}}
BAND_MATH = {"op": "band_math", "op_version": 2, "params": {"expression": "map * 2", "name": "doubled"}}
SCALE_2 = {"op": "scale", "op_version": 1, "params": {"factor": 2.0}}


def _mask(source: str, classes: list[int]) -> dict[str, Any]:
    """"Mask by classes" as the panel sends it (version 2: the layer stays in the stock)."""
    return {"op": "mask", "op_version": 2, "params": {"source": source, "classes": classes}}


def _mask_values(condition: str, values: list[float]) -> dict[str, Any]:
    return {"op": "mask_values", "op_version": 1, "params": {"band": "map", "condition": condition, "values": values}}


def _reproject(resampling: str) -> dict[str, Any]:
    return {"op": "reproject", "op_version": 4, "params": {"crs": sources.CRS, "resolution": 20.0, "resampling": resampling}}


def _without(*values: int) -> list[dict[str, Any]]:
    return [row for row in STAC if row["value"] not in values]


class TestValuesKept:
    def test_a_result_without_steps_keeps_the_classes_and_their_colour_table(self, tmp_path: Path) -> None:
        result = _run(_recipe([]), tmp_path)
        assert _band_classes(result) == [STAC]
        table = _colour_table(result.path)
        assert table is not None
        assert (table[10], table[20], table[60]) == ((0, 100, 0, 255), (255, 187, 34, 255), (180, 180, 180, 255))
        assert table[0][3] == 0  # nodata see-through

    @pytest.mark.parametrize(
        ("step", "left"),
        [
            # Otto's browser test (24.11.2026): WorldCover, "Mask by classes", Tree cover hidden.
            (_mask("map", [10]), _without(10)),
            (_mask("map", [10, 60]), _without(10, 60)),
            (MASK_EQ_20, _without(20)),
            (_mask_values("lt", [15.0]), _without(10)),
            (_mask_values("gt", [15.0]), _without(20, 60)),
            (_mask_values("between", [15.0, 65.0]), _without(20, 60)),
            (_reproject("nearest"), STAC),
            (_reproject("mode"), STAC),
        ],
        ids=["mask-tree-cover", "mask-two", "values-eq", "values-lt", "values-gt", "values-between", "nearest", "mode"],
    )
    def test_a_step_that_passes_the_values_on_keeps_them_less_what_it_hides(
        self, tmp_path: Path, step: dict, left: list
    ) -> None:
        result = _run(_recipe([step]), tmp_path)
        assert _band_classes(result) == [left]
        table = _colour_table(result.path)
        assert table is not None
        colour = {row["value"]: tuple(int(row["color_hint"][i : i + 2], 16) for i in (0, 2, 4)) for row in STAC}
        kept = {row["value"] for row in left}
        assert all(table[value][:3] == colour[value] for value in kept)
        assert all(table[value][:3] != colour[value] for value in set(colour) - kept)  # hidden: not in the table

    def test_a_mask_by_another_band_leaves_the_classes_of_the_band_of_classes(self, tmp_path: Path) -> None:
        result = _run(_recipe([_mask("other", [10])], assets=("map", "other")), tmp_path)
        assert _band_classes(result) == [STAC, None]

    def test_a_mask_that_hides_every_class_leaves_none(self, tmp_path: Path) -> None:
        result = _run(_recipe([_mask("map", [10, 20, 60])]), tmp_path)
        assert _band_classes(result) == [None]
        assert _colour_table(result.path) is None

    def test_a_float_result_keeps_the_classes_but_has_no_colour_table(self, tmp_path: Path) -> None:
        # GeoTIFF holds a colour table only for uint8 and uint16 (plan A3).
        result = _run(_recipe([], dtype="float32"), tmp_path)
        assert _band_classes(result) == [STAC]
        assert _colour_table(result.path) is None

    def test_two_bands_keep_their_classes_but_the_file_has_no_colour_table(self, tmp_path: Path) -> None:
        result = _run(_recipe([], assets=("map", "other")), tmp_path)  # "other" carries none
        assert _band_classes(result) == [STAC, None]
        assert _colour_table(result.path) is None


class TestValuesChanged:
    @pytest.mark.parametrize("step", [BAND_MATH, SCALE_2, _reproject("bilinear")], ids=["band_math", "scale", "bilinear"])
    def test_a_step_that_changes_values_leaves_no_classes_and_no_colour_table(self, tmp_path: Path, step: dict) -> None:
        bands = ["doubled"] if step is BAND_MATH else None
        result = _run(_recipe([step], bands=bands), tmp_path)
        assert _band_classes(result) == [None]
        assert all("classification:classes" not in band for band in result.properties["bands"])
        assert _colour_table(result.path) is None

    def test_band_math_beside_the_band_of_classes_leaves_it_its_classes(self, tmp_path: Path) -> None:
        # Classes hold per band (Otto, 24.11.2026): NDVI by Band math beside SCL passed on keeps the classes of SCL.
        result = _run(_recipe([BAND_MATH], bands=["map", "doubled"]), tmp_path)
        assert _band_classes(result) == [STAC, None]
        assert _colour_table(result.path) is None  # two bands: no colour table

    def test_a_step_that_names_no_band_changes_every_one(self, tmp_path: Path) -> None:
        result = _run(_recipe([SCALE_2], assets=("map", "other")), tmp_path)
        assert _band_classes(result) == [None, None]


class TestNoClasses:
    def test_a_band_without_classes_has_neither(self, tmp_path: Path) -> None:
        result = _run(_recipe([], classes=None), tmp_path)
        assert _band_classes(result) == [None]
        assert _colour_table(result.path) is None


def test_a_step_that_acts_on_some_bands_takes_the_classes_of_those_only() -> None:
    """Normalize names the bands it acts on (``BandUse.acts_on``); the others keep their classes."""
    from types import SimpleNamespace

    from rasterio.transform import Affine

    from earthx.catalog.registry import ClassRow
    from earthx.processing.core import _keep_classes
    from earthx.processing.operators import BandMeta, BandUse, RasterMeta

    rows = (ClassRow(10, "Tree cover", "#006400"),)
    meta = RasterMeta(None, Affine.identity(), 1, 1, (BandMeta("map", "uint8", 0, classes=rows), BandMeta("scl", "uint8", 0, classes=rows)))
    operator = SimpleNamespace(hides=None, passes_values=lambda params: False, bands_used=lambda params: BandUse(acts_on=frozenset({"scl"})))
    kept = _keep_classes(meta, [SimpleNamespace(operator=operator, params=None)])
    assert [band.classes for band in kept.bands] == [rows, None]


def _source_values(result) -> list[bool]:
    return [band.get("earthx:source_values") is True for band in result.properties["bands"]]


class TestSourceValues:
    """M5-68 (plan M5-60 §15.2): each band of the result says whether its values are those of the source band of its name,
    unchanged, by the rule the classes follow; the panel gives it the look of that band. A band without classes says it too."""

    def test_a_result_without_steps_holds_the_values_of_the_source(self, tmp_path: Path) -> None:
        result = _run(_recipe([], classes=None), tmp_path)
        assert _source_values(result) == [True]

    @pytest.mark.parametrize("step", [MASK_EQ_20, _mask("map", [10]), _reproject("nearest")], ids=["values", "classes", "nearest"])
    def test_a_step_that_passes_the_values_on_keeps_them(self, tmp_path: Path, step: dict) -> None:
        assert _source_values(_run(_recipe([step], classes=None), tmp_path)) == [True]

    def test_band_math_beside_a_band_leaves_it_its_values(self, tmp_path: Path) -> None:
        result = _run(_recipe([BAND_MATH], bands=["map", "doubled"], classes=None), tmp_path)
        assert _source_values(result) == [True, False]
        assert "earthx:source_values" not in result.properties["bands"][1]

    @pytest.mark.parametrize("step", [SCALE_2, _reproject("bilinear")], ids=["names-no-band", "bilinear"])
    def test_a_step_that_changes_every_band_leaves_none(self, tmp_path: Path, step: dict) -> None:
        result = _run(_recipe([step], assets=("map", "other"), classes=None), tmp_path)
        assert _source_values(result) == [False, False]
        assert all("earthx:source_values" not in band for band in result.properties["bands"])

    def test_a_scaled_band_holds_its_physical_values_and_keeps_the_look(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stored = (numpy.indices((HEIGHT, WIDTH))[1] % 50 + 1000).astype("uint16")
        path = sources.build_band_cog(tmp_path / "red.tif", stored, scale=0.0001, offset=-0.1)
        sources.serve({sources.url("red"): path}, monkeypatch)
        data = _recipe([], assets=("red",), classes=None, dtype="float32")
        data["inputs"][0]["resolved"] = [resolved("ITEM_A", "red", href=sources.url("red"), scale=0.0001, offset=-0.1)]
        work = tmp_path / "work"
        work.mkdir()
        result = _run(data, work)
        band = result.properties["bands"][0]
        assert band["data_type"] == "float32" and band["earthx:source_values"] is True
        assert band["statistics"]["minimum"] == pytest.approx(0.0, abs=1e-6)


def test_a_step_that_acts_on_some_bands_changes_the_values_of_those_only() -> None:
    """Normalize names the bands it acts on; Band math that writes a band of the source's name changes that band."""
    from types import SimpleNamespace

    from rasterio.transform import Affine

    from earthx.processing.core import _source_values as source_values
    from earthx.processing.operators import BandMeta, BandUse, RasterMeta

    meta = RasterMeta(None, Affine.identity(), 1, 1, (BandMeta("red", "float32", None), BandMeta("nir", "float32", None)))

    def step(use: BandUse, passes: bool = False) -> SimpleNamespace:
        return SimpleNamespace(operator=SimpleNamespace(passes_values=lambda params: passes, bands_used=lambda params: use), params=None)

    assert source_values(meta, [step(BandUse(acts_on=frozenset({"nir"})))]) == {"red"}
    assert source_values(meta, [step(BandUse(adds="red"))]) == {"nir"}
    assert source_values(meta, [step(BandUse(), passes=True), step(BandUse(adds="ndvi"))]) == {"red", "nir"}
    assert source_values(meta, [step(BandUse())]) == frozenset()

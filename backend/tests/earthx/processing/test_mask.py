"""The ``mask`` operator: parameters, kernel, applicability, and runs over a 20 m layer (plan M4-18 §3.2, §3.6, §8)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy
import pytest
import rasterio
from pydantic import ValidationError
from rasterio.transform import Affine
from rio_tiler.models import ImageData

from earthx.catalog.datasets import COP_DEM_GLO_30, SENTINEL_2_L2A, SENTINEL_2_L2A_ZARR3
from earthx.catalog.datasets import REGISTRY as DATASETS
from earthx.catalog.registry import LicenseTier
from earthx.processing import run
from earthx.processing.errors import RecipeInvalid
from earthx.processing.operators import MASK, REGISTRY, BandMeta, MaskParams, RasterMeta, applicable
from earthx.processing.recipe import recipe_from_data
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import resolved

WIDTH, HEIGHT = 1300, 1100
STEP = {"op": "mask", "op_version": 1, "params": {"source": "scl", "classes": [3, 8, 9, 10]}}


def scl_layer(width: int, height: int) -> numpy.ndarray:
    """Classes 1..11 in diagonal stripes, with a nodata (0) corner."""
    rows, cols = numpy.indices((height, width))
    data = (1 + (rows // 3 + cols // 2) % 11).astype("uint8")
    data[:4, :4] = 0
    return data


def _params(*classes: int, source: str = "scl") -> MaskParams:
    return MaskParams(source=source, classes=list(classes))


def _image(names: list[str], *arrays: numpy.ndarray, masks: list | None = None) -> ImageData:
    stack = numpy.ma.stack(
        [numpy.ma.masked_array(a, mask=None if masks is None else masks[i]) for i, a in enumerate(arrays)]
    )
    return ImageData(stack, bounds=(0, 0, 1, 1), crs="EPSG:32632", band_names=names)


def _meta(*names: str, resampled: bool = False) -> RasterMeta:
    bands = tuple(BandMeta(name, "float32", None) for name in names)
    return RasterMeta("EPSG:32632", Affine(10, 0, 0, 0, -10, 0), 4, 4, bands, resampled)


class TestParameters:
    def test_a_valid_mask(self) -> None:
        params = MaskParams.model_validate_json('{"source": "scl", "classes": [3, 8, 9, 10]}', strict=True)
        assert params.classes == [3, 8, 9, 10]

    @pytest.mark.parametrize(
        "data",
        [
            {"source": "scl", "classes": []},
            {"source": "scl", "classes": [8, 3]},
            {"source": "scl", "classes": [3, 3]},
            {"source": "scl", "classes": [-1]},
            {"source": "scl", "classes": [65536]},
            {"source": "scl", "classes": [True]},
            {"source": "scl", "classes": ["3"]},
            {"source": "scl", "classes": [3.0]},
            {"source": "scl", "classes": list(range(65))},
            {"source": "", "classes": [3]},
            {"source": "s cl", "classes": [3]},
            {"source": "scäl", "classes": [3]},
            {"source": "x" * 65, "classes": [3]},
            {"source": 3, "classes": [3]},
            {"source": "scl"},
            {"classes": [3]},
            {"source": "scl", "classes": [3], "extra": 1},
            {"source": "scl", "classes": 3},
        ],
    )
    def test_misuse_is_refused(self, data: dict) -> None:
        with pytest.raises(ValidationError):
            MaskParams.model_validate_json(json.dumps(data), strict=True)

    def test_the_schema_carries_the_bounds_and_no_pattern(self) -> None:
        schema = REGISTRY.params_schema("mask", 1)
        assert schema["additionalProperties"] is False and "pattern" not in json.dumps(schema)
        assert schema["properties"]["classes"]["minItems"] == 1 and schema["properties"]["classes"]["maxItems"] == 64


class TestKernel:
    def test_the_listed_classes_and_the_layers_own_nodata_hide_every_band(self) -> None:
        scl = numpy.array([[0, 3, 4], [8, 5, 11]], dtype="uint8")
        red = numpy.arange(6, dtype="float32").reshape(2, 3)
        nir = red * 2
        image = _image(["red", "scl", "nir"], red, scl, nir, masks=[None, scl == 0, None])
        result = MASK.run(image, _params(3, 8))
        expected_hidden = numpy.array([[True, True, False], [True, False, False]])
        assert list(result.band_names) == ["red", "nir"]
        for band in range(2):
            numpy.testing.assert_array_equal(result.array.mask[band], expected_hidden)
        numpy.testing.assert_array_equal(result.array.data[0], red)
        numpy.testing.assert_array_equal(result.array.data[1], nir)

    def test_values_and_types_of_the_other_bands_are_untouched(self) -> None:
        scl = numpy.zeros((3, 3), dtype="uint8") + 4
        red = numpy.linspace(-1, 1, 9, dtype="float32").reshape(3, 3)
        result = MASK.run(_image(["red", "scl"], red, scl), _params(8))
        assert result.array.dtype == numpy.float32 and not result.array.mask.any()
        numpy.testing.assert_array_equal(result.array.data[0], red)

    def test_a_band_that_was_masked_stays_masked(self) -> None:
        scl = numpy.full((2, 2), 4, dtype="uint8")
        red = numpy.ones((2, 2), dtype="float32")
        mask = numpy.array([[True, False], [False, False]])
        result = MASK.run(_image(["red", "scl"], red, scl, masks=[mask, None]), _params(9))
        numpy.testing.assert_array_equal(result.array.mask[0], mask)

    def test_a_class_decoded_as_a_float_is_still_matched_exactly(self) -> None:
        """The Zarr layer arrives as float after CF decoding; whole numbers compare equal, NaN is the layer's nodata."""
        scl = numpy.array([[3.0, numpy.nan, 4.0]], dtype="float32")
        red = numpy.ones((1, 3), dtype="float32")
        image = _image(["red", "scl"], red, scl, masks=[None, numpy.isnan(scl)])
        numpy.testing.assert_array_equal(MASK.run(image, _params(3)).array.mask[0], [[True, True, False]])

    def test_a_class_nobody_has_hides_nothing(self) -> None:
        scl = numpy.full((2, 2), 4, dtype="uint8")
        result = MASK.run(_image(["red", "scl"], numpy.ones((2, 2), dtype="float32"), scl), _params(9))
        assert not result.array.mask.any()

    def test_the_layer_is_not_among_the_bands(self) -> None:
        with pytest.raises(RecipeInvalid, match="not among the bands"):
            MASK.run(_image(["red"], numpy.ones((2, 2), dtype="float32")), _params(3))

    def test_the_layer_alone_leaves_nothing_to_mask(self) -> None:
        with pytest.raises(RecipeInvalid, match="nothing to mask"):
            MASK.run(_image(["scl"], numpy.ones((2, 2), dtype="uint8")), _params(3))


class TestMetadata:
    def test_the_layer_leaves_the_bands_and_the_flag_stays(self) -> None:
        meta = MASK.transform(_meta("red", "scl", "nir", resampled=True), _params(3))
        assert [band.name for band in meta.bands] == ["red", "nir"] and meta.resampled is True

    def test_a_missing_layer_is_found_before_a_block_is_read(self) -> None:
        with pytest.raises(RecipeInvalid):
            MASK.transform(_meta("red"), _params(3))

    def test_lineage_and_properties_name_layer_and_classes(self) -> None:
        assert MASK.lineage(_params(3, 8)) == "mask: scl classes 3, 8"
        assert MASK.properties(_params(3, 8)) == {"earthx:mask": {"source": "scl", "classes": [3, 8]}}

    def test_the_cost_factor_is_the_measured_one(self) -> None:
        assert MASK.cost_factor(_params(3)) == 0.2

    def test_the_sentence_of_the_methods_text_names_layer_and_classes_and_no_address(self) -> None:
        sentence = MASK.method(_params(3, 8, 9, 10))
        assert sentence == (
            "Pixels were hidden in every band where the classification layer scl held class 3, 8, 9, 10 "
            "or had no value; the layer itself was left out."
        )

    def test_it_runs_as_a_tile_and_as_a_job(self) -> None:
        assert {tier.value for tier in MASK.tiers} == {"T1", "T2"} and MASK.kind == "pixel"


class TestApplicable:
    @pytest.mark.parametrize("config", [SENTINEL_2_L2A, SENTINEL_2_L2A_ZARR3], ids=lambda c: c.dataset_id)
    def test_the_sentinel_2_entries_allow_their_own_classes(self, config) -> None:
        assert applicable(MASK, config, _params(*range(12))) == []

    def test_the_dem_has_no_layer(self) -> None:
        reasons = applicable(MASK, COP_DEM_GLO_30, _params(3))
        assert reasons == ["cop-dem-glo-30 does not allow masking"]

    def test_a_mask_over_a_reflectance_band_is_no_mask(self) -> None:
        reasons = applicable(MASK, SENTINEL_2_L2A, _params(3, source="red"))
        assert reasons == ["sentinel-2-c1-l2a masks with its layer 'scl', not 'red'"]

    def test_a_class_the_layer_does_not_know(self) -> None:
        reasons = applicable(MASK, SENTINEL_2_L2A, _params(3, 12, 200))
        assert reasons == ["the layer 'scl' of sentinel-2-c1-l2a has no class 12, 200"]

    def test_the_flag_alone_is_not_enough_below_the_processing_tier(self) -> None:
        display = replace(SENTINEL_2_L2A, license=replace(SENTINEL_2_L2A.license, tier=LicenseTier.DISPLAY))
        assert applicable(MASK, display, _params(3))

    def test_without_parameters_only_the_flags_are_checked(self) -> None:
        assert applicable(MASK, SENTINEL_2_L2A) == [] and applicable(MASK, COP_DEM_GLO_30)


# --- a run over a 20 m layer ------------------------------------------------------------------


def _recipe(assets: tuple[str, ...], steps: list, dtype: str = "float32") -> dict:
    entries = []
    for asset in assets:
        if asset == "scl":
            entry = resolved("ITEM_A", asset, href=sources.url(asset), scale=None, offset=None)
            entry["bands"] = [{"data_type": "uint8", "nodata": 0, "scale": None, "offset": None}]
        else:
            entry = resolved("ITEM_A", asset, href=sources.url(asset))
        entries.append(entry)
    return {
        "recipe_version": 1,
        "inputs": [
            {"name": "s2", "dataset": "synthetic", "groups": [["ITEM_A"]], "assets": list(assets), "resolved": entries}
        ],
        "aoi": sources.whole(WIDTH, HEIGHT),
        "steps": steps,
        "output": {"kind": "raster", "format": "cog", "dtype": dtype},
    }


def _run(data: dict, workdir: Path):
    return run(recipe_from_data(data, REGISTRY), workdir=workdir, progress=lambda done, total: None, operators=REGISTRY)


@pytest.fixture(scope="module")
def files(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("mask")
    return {
        "red": sources.build_band_cog(root / "red.tif", sources.ramp(WIDTH, HEIGHT, 1200)),
        "scl": sources.build_band_cog(
            root / "scl.tif", scl_layer(WIDTH // 2, HEIGHT // 2), scale=None, offset=None, resolution=20.0
        ),
    }


@pytest.fixture
def served(files: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return sources.serve({sources.url(name): path for name, path in files.items()}, monkeypatch)


@pytest.mark.usefixtures("served")
class TestRunWithA20mLayer:
    def test_the_layer_is_repeated_with_nearest_so_no_new_value_appears_and_the_result_is_marked(
        self, tmp_path: Path, files: dict[str, Path]
    ) -> None:
        classes = [3, 8, 9, 10]
        result = _run(_recipe(("red", "scl"), [{**STEP, "params": {"source": "scl", "classes": classes}}]), tmp_path)
        small = scl_layer(WIDTH // 2, HEIGHT // 2)
        repeated = numpy.repeat(numpy.repeat(small, 2, axis=0), 2, axis=1)
        # The only values a coarser layer can take on the finer grid are the ones it holds.
        assert set(numpy.unique(repeated)) == set(numpy.unique(small))
        with rasterio.open(result.path) as dataset:
            data = dataset.read(1, masked=True)
        red = sources.ramp(WIDTH, HEIGHT, 1200)
        expected_hidden = numpy.isin(repeated, classes) | (repeated == 0) | (red == sources.NODATA)
        assert result.meta.resampled is True and result.properties["earthx:resampled"] is True
        assert [band.name for band in result.meta.bands] == ["red"]
        numpy.testing.assert_array_equal(numpy.ma.getmaskarray(data), expected_hidden)
        assert 0 < expected_hidden.sum() < expected_hidden.size
        assert result.valid_pixels == int((~expected_hidden).sum())
        assert result.properties["earthx:mask"] == {"source": "scl", "classes": classes}
        assert result.properties["processing:lineage"] == "mask: scl classes 3, 8, 9, 10"

    def test_a_mask_then_band_math_uses_only_the_valid_pixels(self, tmp_path: Path) -> None:
        double = {"op": "band_math", "op_version": 1, "params": {"expression": "red * 2"}}
        result = _run(_recipe(("red", "scl"), [STEP, double]), tmp_path)
        assert result.properties["processing:lineage"] == "mask: scl classes 3, 8, 9, 10; band math: red * 2"
        assert result.valid_pixels < WIDTH * HEIGHT - 64

    def test_the_layer_missing_from_the_order_stops_before_the_first_block(self, tmp_path: Path) -> None:
        ticks: list[int] = []
        with pytest.raises(RecipeInvalid, match="not among the bands"):
            run(
                recipe_from_data(_recipe(("red",), [STEP]), REGISTRY),
                workdir=tmp_path,
                progress=lambda done, total: ticks.append(done),
                operators=REGISTRY,
            )
        assert ticks == [] and list(tmp_path.iterdir()) == []

    def test_the_same_bytes_twice(self, tmp_path: Path) -> None:
        for name in ("a", "b"):
            (tmp_path / name).mkdir()
        first = _run(_recipe(("red", "scl"), [STEP]), tmp_path / "a")
        second = _run(_recipe(("red", "scl"), [STEP]), tmp_path / "b")
        with rasterio.open(first.path) as a, rasterio.open(second.path) as b:
            assert a.read(masked=True).tobytes() == b.read(masked=True).tobytes()


def test_every_registry_entry_without_a_layer_refuses_the_operator() -> None:
    for config in DATASETS:
        reasons = applicable(MASK, config, _params(3))
        assert (reasons == []) == (config.mask is not None), config.dataset_id

"""The rule for assets that are not one grid, and the names of the bands (plan M4-09 §3.2, F2).

``common_grid`` looks at the grid of each source only, so the sources here are bare objects with a CRS, a
transform and a size; the reading itself is covered by the runs in ``test_band_math_run`` and the tile route.
"""

from __future__ import annotations

import pytest
from rasterio.crs import CRS
from rasterio.transform import Affine

from earthx.processing.errors import GridMismatch
from earthx.processing.recipe import ResolvedInput
from earthx.processing.source import Source, common_grid, expected_band_names
from tests.earthx.processing.recipes import resolved

ORIGIN = (600000.0, 5700000.0)


def _source(resolution: float | tuple[float, float], size: tuple[int, int], *, crs: str = "EPSG:32632", origin=ORIGIN):
    x, y = (resolution, resolution) if isinstance(resolution, float) else resolution
    source = Source.__new__(Source)
    source.crs = CRS.from_user_input(crs)
    source.transform = Affine(x, 0, origin[0], 0, -y, origin[1])
    source.width, source.height = size
    return source


class TestCommonGrid:
    def test_one_grid_is_not_resampled(self) -> None:
        finest, resampled = common_grid([_source(10.0, (100, 80)), _source(10.0, (100, 80))])
        assert (finest.transform.a, resampled) == (10.0, False)

    def test_a_single_source_is_its_own_grid(self) -> None:
        assert common_grid([_source(10.0, (100, 80))])[1] is False

    @pytest.mark.parametrize("factor", [2, 3, 6])
    def test_a_coarser_pixel_that_is_a_whole_multiple_on_the_same_extent_is_nested(self, factor: int) -> None:
        fine = _source(10.0, (120, 60))
        coarse = _source(10.0 * factor, (120 // factor, 60 // factor))
        for order in ([fine, coarse], [coarse, fine]):
            finest, resampled = common_grid(order)
            assert finest is fine and resampled is True

    def test_three_assets_on_three_levels(self) -> None:
        finest, resampled = common_grid([_source(20.0, (60, 30)), _source(10.0, (120, 60)), _source(60.0, (20, 10))])
        assert (finest.transform.a, resampled) == (10.0, True)

    def test_a_different_crs_is_not_nested(self) -> None:
        with pytest.raises(GridMismatch):
            common_grid([_source(10.0, (120, 60)), _source(20.0, (60, 30), crs="EPSG:32633")])

    @pytest.mark.parametrize(
        "other",
        [
            _source(15.0, (80, 40)),  # not a whole multiple
            _source(25.0, (48, 24)),  # not a whole multiple
            _source(20.0, (59, 30)),  # the extent is smaller
            _source(20.0, (60, 31)),  # and larger
            _source(20.0, (60, 30), origin=(600010.0, 5700000.0)),  # shifted by half a coarse pixel
            _source(20.0, (60, 30), origin=(600000.0, 5700020.0)),  # shifted by a whole coarse pixel
            _source((20.0, 15.0), (60, 40)),  # a whole multiple in one direction only
        ],
        ids=["1.5x", "2.5x", "smaller", "larger", "shift-half", "shift-whole", "one-axis"],
    )
    def test_other_grids_are_a_grid_mismatch(self, other: Source) -> None:
        with pytest.raises(GridMismatch):
            common_grid([_source(10.0, (120, 60)), other])

    def test_a_pixel_that_is_a_whole_multiple_in_each_direction_separately_is_nested(self) -> None:
        finest, resampled = common_grid([_source(10.0, (120, 60)), _source((20.0, 10.0), (60, 60))])
        assert (finest.transform.a, resampled) == (10.0, True)

    def test_the_finest_of_three_decides(self) -> None:
        finest, _ = common_grid([_source(10.0, (120, 60)), _source(5.0, (240, 120))])
        assert finest.transform.a == 5.0

    def test_a_rotated_grid_is_not_nested(self) -> None:
        rotated = _source(20.0, (60, 30))
        rotated.transform = rotated.transform * Affine.rotation(3)
        with pytest.raises(GridMismatch):
            common_grid([_source(10.0, (120, 60)), rotated])

    def test_the_text_names_no_address_and_no_asset(self) -> None:
        with pytest.raises(GridMismatch) as error:
            common_grid([_source(10.0, (120, 60)), _source(15.0, (80, 40))])
        assert "http" not in str(error.value)


def _entry(**options) -> ResolvedInput:
    return ResolvedInput.model_validate(resolved("ITEM_A", **options))


class TestExpectedBandNames:
    def test_a_cog_asset_with_one_band_is_named_like_the_asset(self) -> None:
        assert expected_band_names(_entry(asset="red")) == ["red"]

    def test_a_cog_asset_the_item_says_has_three_bands_is_numbered(self) -> None:
        entry = _entry(asset="visual")
        entry.bands.extend([entry.bands[0], entry.bands[0]])
        assert expected_band_names(entry) == ["visual_1", "visual_2", "visual_3"]

    def test_a_cog_asset_with_no_description_is_unknown(self) -> None:
        entry = _entry(asset="data", scale=None, offset=None)
        entry.bands.clear()
        assert expected_band_names(entry) is None

    def test_a_zarr_asset_is_named_by_its_variables(self) -> None:
        entry = _entry(asset="SR_10m:b04,b08", reader="zarr", variable="b04,b08")
        assert expected_band_names(entry) == ["b04", "b08"]

    def test_a_zarr_asset_without_a_variable_is_unknown(self) -> None:
        entry = _entry(asset="SR_10m", reader="zarr")
        assert expected_band_names(entry) is None

"""A file placed by ground control points lies the same in tile, job and runner, and only where the registry says so.

DS-04a (adr/0018 F1): the registry names ``gcp_tps``, :class:`~earthx.readers.cog.CogReader` reads the file through a
thin-plate spline, and every path reads that one grid. The synthetic file (`mini_gcp`) bends too much for an affine fit,
so a test that passes with the spline would fail with rio-tiler's own placing.
"""

from __future__ import annotations

import json
import warnings
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

import morecantile
import numpy
import pytest
import rasterio
from rasterio import transform as rio_transform
from rasterio.errors import NotGeoreferencedWarning
from rasterio.vrt import WarpedVRT

from earthx.catalog.registry import ConfigError, DataFormat, Georeferencing
from earthx.processing import failure_kind, run
from earthx.processing.operators import REGISTRY as OPERATORS
from earthx.processing.recipe import ResolvedAssetModel, recipe_from_data, recipe_hash
from earthx.readers import GeoreferenceMismatch, source_failure_kind
from earthx.readers.cog import AssetPath, CogReader, warp_options
from tests.catalog.entries import SENTINEL_2_L2A
from tests.catalog.synthetic_zarr import SYNTHETIC_ZARR
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import recipe_data, resolved
from tests.earthx.readers import mini_gcp
from tests.earthx.readers.mini_cog import build_mini_cog

URL = sources.url("gcp")


@pytest.fixture(scope="module")
def gcp_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    with warnings.catch_warnings():
        # The file has no geotransform on purpose; rasterio says so while writing it.
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        return mini_gcp.build_mini_gcp(tmp_path_factory.mktemp("gcp") / "gcp.tif")


def path(local: Path, georeferencing: str = "gcp_tps") -> AssetPath:
    return AssetPath(str(local), dataset_id="d", item_id="i", asset="vv", georeferencing=georeferencing)


@contextmanager
def tps_reader(local: Path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with CogReader(path(local)) as reader:
            yield reader


def misses(dataset: Any) -> list[float]:
    """For every GCP, how many source pixels away the pixel lies that ``dataset`` shows at the GCP's position."""
    band = dataset.read(1)
    found: list[float] = []
    for gcp in mini_gcp.gcps():
        row, col = dataset.index(gcp.x, gcp.y)
        inside = 0 <= row < dataset.height and 0 <= col < dataset.width
        if not inside or band[row, col] == mini_gcp.NODATA:
            found.append(float("inf"))
            continue
        source_row, source_col = mini_gcp.source_pixel(band[row, col])
        found.append(max(abs(source_row - (gcp.row - 0.5)), abs(source_col - (gcp.col - 0.5))))
    return found


class TestTheReaderPlacesByTheSpline:
    def test_every_gcp_lands_on_its_own_pixel_within_one(self, gcp_file: Path) -> None:
        with tps_reader(gcp_file) as reader:
            assert max(misses(reader.dataset)) <= 1

    def test_an_affine_fit_through_the_same_gcps_misses_them(self, gcp_file: Path) -> None:
        """rio-tiler's own placing; the reason the reader does not leave the file to it (adr/0018 §4.1)."""
        with rasterio.open(gcp_file) as src:
            gcps, crs = src.gcps
            vrt = WarpedVRT(src, src_crs=crs, src_transform=rio_transform.from_gcps(gcps), nodata=0, src_nodata=0)
            with vrt:
                assert max(misses(vrt)) > 1

    def test_the_grid_is_the_gcps_crs_and_carries_no_gcps_any_more(self, gcp_file: Path) -> None:
        with tps_reader(gcp_file) as reader:
            assert reader.crs == mini_gcp.GCP_CRS
            assert reader.dataset.gcps[0] == []
            assert reader.dataset.nodata == mini_gcp.NODATA

    def test_a_tile_shows_the_pixel_of_every_gcp_at_its_position(self, gcp_file: Path) -> None:
        tms = morecantile.tms.get("WebMercatorQuad")
        found: list[float] = []
        with tps_reader(gcp_file) as reader:
            for gcp in mini_gcp.gcps():
                tile = tms.tile(gcp.x, gcp.y, 17)
                image = reader.tile(tile.x, tile.y, tile.z, resampling_method="nearest", reproject_method="nearest")
                west, south, east, north = tms.xy_bounds(tile)
                x, y = tms.xy(gcp.x, gcp.y)
                col = int((x - west) / (east - west) * image.width)
                row = int((north - y) / (north - south) * image.height)
                value = image.data[0, row, col]
                if value == mini_gcp.NODATA:
                    found.append(float("inf"))
                    continue
                source_row, source_col = mini_gcp.source_pixel(value)
                found.append(max(abs(source_row - (gcp.row - 0.5)), abs(source_col - (gcp.col - 0.5))))
        assert max(found) <= 1

    def test_a_job_reads_the_same_pixels_as_the_reader(self, gcp_file: Path, tmp_path: Path, monkeypatch) -> None:
        """The core reads the reader's own grid with exact windows: what a tile shows at the native level."""
        sources.serve({URL: gcp_file}, monkeypatch)
        result = run(recipe_from_data(gcp_recipe(), OPERATORS), workdir=tmp_path, progress=lambda *_: None)
        with tps_reader(gcp_file) as reader, rasterio.open(result.path) as out:
            assert out.crs == reader.crs
            window = reader.dataset.window(*out.bounds).round_offsets().round_lengths()
            expected = reader.dataset.read(1, window=window)
            assert window.width == out.width and window.height == out.height
            got = out.read(1)
        valid = expected != mini_gcp.NODATA
        assert valid.any()
        assert numpy.array_equal(got[valid], expected[valid].astype(got.dtype))

    def test_two_runs_of_one_recipe_give_the_same_bytes(self, gcp_file: Path, tmp_path: Path, monkeypatch) -> None:
        """The local runner runs the same core: the same recipe gives the same file (adr/0014 §6.3)."""
        sources.serve({URL: gcp_file}, monkeypatch)
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        first = run(recipe_from_data(gcp_recipe(), OPERATORS), workdir=tmp_path / "a", progress=lambda *_: None)
        second = run(recipe_from_data(gcp_recipe(), OPERATORS), workdir=tmp_path / "b", progress=lambda *_: None)
        assert Path(first.path).read_bytes() == Path(second.path).read_bytes()


class TestAFileThatDisagreesIsNotRead:
    def test_gcps_where_the_registry_names_a_geotransform(self, gcp_file: Path) -> None:
        with pytest.raises(GeoreferenceMismatch, match="carries GCPs"), warnings.catch_warnings():
            warnings.simplefilter("ignore", NotGeoreferencedWarning)
            CogReader(path(gcp_file, "geotransform"))

    def test_no_gcps_where_the_registry_names_gcp_tps(self, tmp_path: Path) -> None:
        with pytest.raises(GeoreferenceMismatch, match="carries none"):
            CogReader(path(build_mini_cog(tmp_path / "plain.tif")))

    def test_the_failure_has_its_own_name_and_the_message_no_address(self, gcp_file: Path) -> None:
        with pytest.raises(GeoreferenceMismatch) as caught, warnings.catch_warnings():
            warnings.simplefilter("ignore", NotGeoreferencedWarning)
            CogReader(path(gcp_file, "geotransform"))
        assert source_failure_kind(caught.value) == failure_kind(caught.value) == "source_georeference"
        assert str(gcp_file) not in str(caught.value)

    def test_a_job_whose_recipe_names_a_geotransform_fails_with_that_name(
        self, gcp_file: Path, tmp_path: Path, monkeypatch
    ) -> None:
        sources.serve({URL: gcp_file}, monkeypatch)
        with pytest.raises(GeoreferenceMismatch) as caught, warnings.catch_warnings():
            warnings.simplefilter("ignore", NotGeoreferencedWarning)
            run(recipe_from_data(gcp_recipe("geotransform"), OPERATORS), workdir=tmp_path, progress=lambda *_: None)
        assert failure_kind(caught.value) == "source_georeference"


class TestTheMethodIsChecked:
    @pytest.mark.parametrize("value", ["GCP_TPS", "affine", "", None])
    def test_an_asset_path_takes_only_the_two_names(self, value: object) -> None:
        with pytest.raises(ValueError, match="georeferencing"):
            AssetPath("/vsicurl/x", dataset_id="d", item_id="i", asset="a", georeferencing=value)  # type: ignore[arg-type]

    def test_the_options_are_the_spline_or_nothing(self) -> None:
        assert warp_options("gcp_tps") == {"SRC_METHOD": "GCP_TPS"}
        assert warp_options("geotransform") == {}
        with pytest.raises(ValueError):
            warp_options("polynomial")  # type: ignore[arg-type]

    def test_the_registry_allows_the_spline_only_for_a_cog(self) -> None:
        assert replace(SENTINEL_2_L2A, georeferencing=Georeferencing.GCP_TPS).georeferencing is Georeferencing.GCP_TPS
        with pytest.raises(ConfigError, match="needs format cog"):
            replace(SYNTHETIC_ZARR, georeferencing=Georeferencing.GCP_TPS)

    def test_the_registry_takes_no_plain_string(self) -> None:
        with pytest.raises(ConfigError, match="georeferencing"):
            replace(SENTINEL_2_L2A, georeferencing="gcp_tps")

    def test_the_collection_publishes_it(self) -> None:
        from earthx.catalog.collection import to_stac_collection

        assert to_stac_collection(SENTINEL_2_L2A)["earthx:georeferencing"] == "geotransform"
        tps = replace(SENTINEL_2_L2A, georeferencing=Georeferencing.GCP_TPS, format=DataFormat.COG)
        assert to_stac_collection(tps)["earthx:georeferencing"] == "gcp_tps"


class TestTheRecipeCarriesTheMethod:
    def test_the_spline_is_in_the_recipe_and_its_hash(self) -> None:
        plain = recipe_from_data(gcp_recipe("geotransform"), OPERATORS)
        tps = recipe_from_data(gcp_recipe(), OPERATORS)
        assert recipe_hash(plain) != recipe_hash(tps)
        assert tps.model_dump(mode="json")["inputs"][0]["resolved"][0]["asset"]["georeferencing"] == "gcp_tps"

    def test_a_geotransform_stays_out_so_earlier_recipes_keep_their_hash(self) -> None:
        written = recipe_from_data(gcp_recipe("geotransform"), OPERATORS)
        assert "georeferencing" not in written.model_dump(mode="json")["inputs"][0]["resolved"][0]["asset"]
        before = gcp_recipe("geotransform")
        del before["inputs"][0]["resolved"][0]["asset"]["georeferencing"]
        assert recipe_hash(recipe_from_data(before, OPERATORS)) == recipe_hash(written)

    def test_the_asset_the_readers_get_carries_it(self) -> None:
        entry = gcp_recipe()["inputs"][0]["resolved"][0]["asset"]
        assert ResolvedAssetModel.model_validate_json(json.dumps(entry)).to_asset().georeferencing == "gcp_tps"

    @pytest.mark.parametrize("value", ["GCP_TPS", "tps", 1, None])
    def test_another_value_is_refused(self, value: object) -> None:
        entry = {**gcp_recipe()["inputs"][0]["resolved"][0]["asset"], "georeferencing": value}
        with pytest.raises(ValueError):
            ResolvedAssetModel.model_validate_json(json.dumps(entry))

    def test_a_zarr_asset_placed_by_the_spline_is_refused_where_the_readers_take_it(self) -> None:
        entry = {
            **gcp_recipe()["inputs"][0]["resolved"][0]["asset"],
            "reader": "zarr",
            "variable": "b04",
        }
        with pytest.raises(ValueError, match="only for a COG"):
            ResolvedAssetModel.model_validate_json(json.dumps(entry)).to_asset()


def gcp_recipe(georeferencing: str = "gcp_tps") -> dict[str, Any]:
    """A recipe without steps over the middle of the GCP file, its one band unscaled ``uint16``."""
    entry = resolved("ITEM_G", "vv", scale=None, offset=None, href=URL)
    entry["asset"].update(crs=None, georeferencing=georeferencing)
    west, north = mini_gcp.position(24.5, 24.5)
    east, south = mini_gcp.position(72.5, 72.5)
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    return recipe_data(
        inputs=[{"name": "s1", "dataset": "synthetic", "groups": [["ITEM_G"]], "assets": ["vv"], "resolved": [entry]}],
        aoi={"type": "Polygon", "coordinates": [ring]},
        steps=[],
        output={"kind": "raster", "format": "cog", "dtype": "uint16", "bands": ["vv"]},
    )

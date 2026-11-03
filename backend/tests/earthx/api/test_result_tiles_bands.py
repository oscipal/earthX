"""A result with several bands: the tile shows the one ``bidx`` names (NM4-43d, adr/0020 §10).

The rig of `test_result_tiles` over a ``result.tif`` of three float32 bands, as a job with ``output.bands`` writes it:
the name of each band is its description. The browser finds a band by that name in ``properties.bands`` of the result
(with the statistics of its colour scale, M4-32) and asks for its ``bidx``.
"""

from __future__ import annotations

from pathlib import Path

import numpy
import pytest
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles

from tests.earthx.api.test_result_tiles import (  # noqa: F401 - fixtures
    SIZE,
    TILE,
    Rig,
    mask_files,
    rig,
    store,
    uploaded,
)
from tests.earthx.processing import sources

# ruff: noqa: F811
NAMES = ("NDVI", "NDWI", "red")
STEP = 100.0  # each band lies a hundred above the one before, so no two bands share a value


@pytest.fixture(scope="module")
def result_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("result-bands")
    plain = root / "plain.tif"
    rows, cols = numpy.indices((SIZE, SIZE))
    with rasterio.open(
        plain, "w", driver="GTiff", width=SIZE, height=SIZE, count=len(NAMES), dtype="float32", crs=sources.CRS,
        transform=from_origin(sources.ORIGIN_X, sources.ORIGIN_Y, sources.RESOLUTION, sources.RESOLUTION),
        nodata=-9999.0,
    ) as destination:  # fmt: skip
        for index, name in enumerate(NAMES, start=1):
            destination.write(((rows + cols) / (2 * SIZE) + index * STEP).astype("float32"), index)
            destination.set_band_description(index, name)
    target = root / "result.tif"
    cog_translate(str(plain), str(target), cog_profiles.get("deflate"), quiet=True)
    return target


def _values(content: bytes) -> numpy.ma.MaskedArray:
    """The bands of the tile, masked where its last band (the alpha) is not positive."""
    with MemoryFile(content) as memory, memory.open() as dataset:
        data, alpha = dataset.read()[:-1], dataset.read(dataset.count)
    return numpy.ma.masked_array(data, mask=numpy.broadcast_to(alpha <= 0, data.shape))


def _url(result_id: str, query: str) -> str:
    z, x, y = TILE
    return f"/results/{result_id}/tiles/WebMercatorQuad/{z}/{x}/{y}.tif?{query}"


def _tile(rig: Rig, result_id: str, query: str) -> bytes:
    response = rig.client.get(_url(result_id, query))
    assert response.status_code == 200, response.text
    return response.content


class TestTheBandNamedByBidx:
    @pytest.mark.parametrize("index", [1, 2, 3])
    def test_the_tile_holds_the_values_of_that_band_alone(self, rig: Rig, uploaded: str, index: int) -> None:
        values = _values(_tile(rig, uploaded, f"bidx={index}"))
        assert values.shape[0] == 1
        assert values.count() > 10_000
        assert values.min() >= index * STEP and values.max() < (index + 1) * STEP

    def test_without_bidx_the_tile_holds_every_band(self, rig: Rig, uploaded: str) -> None:
        assert _values(_tile(rig, uploaded, "")).shape[0] == len(NAMES)

    def test_a_band_the_file_lacks_is_refused_and_not_a_server_error(self, rig: Rig, uploaded: str) -> None:
        response = rig.client.get(_url(uploaded, f"bidx={len(NAMES) + 1}"))
        assert response.status_code == 400, response.text
        assert f"{len(NAMES)} band" in response.json()["detail"]

    @pytest.mark.parametrize("index", ["0", "-1"])
    def test_a_band_below_one_is_refused_too(self, rig: Rig, uploaded: str, index: str) -> None:
        assert rig.client.get(_url(uploaded, f"bidx={index}")).status_code == 400

    def test_the_tilejson_carries_the_band_into_the_tile_urls(self, rig: Rig, uploaded: str) -> None:
        response = rig.client.get(f"/results/{uploaded}/WebMercatorQuad/tilejson.json?bidx=2")
        assert response.status_code == 200, response.text
        assert "bidx=2" in response.json()["tiles"][0]
        assert uploaded.replace("-", "") not in response.json()["tiles"][0].split("?")[1]  # the id stays in the path

    def test_the_bands_of_the_file_are_named_by_their_descriptions(self, result_file: Path) -> None:
        with rasterio.open(result_file) as dataset:
            assert dataset.descriptions == NAMES


def _png(rig: Rig, result_id: str, query: str) -> bytes:
    z, x, y = TILE
    response = rig.client.get(f"/results/{result_id}/tiles/WebMercatorQuad/{z}/{x}/{y}.png?{query}")
    assert response.status_code == 200, response.text
    return response.content


class TestThreeBandsAsOneColourPicture:
    """NM4-64: ``bidx`` three times, with one ``rescale`` for all of them and no colormap."""

    def test_the_tile_holds_the_three_bands_in_the_order_of_bidx(self, rig: Rig, uploaded: str) -> None:
        values = _values(_tile(rig, uploaded, "bidx=3&bidx=1&bidx=2"))
        assert values.shape[0] == 3
        for channel, index in enumerate((3, 1, 2)):
            assert values[channel].count() > 10_000
            assert values[channel].min() >= index * STEP and values[channel].max() < (index + 1) * STEP

    def test_one_range_stretches_all_three_channels(self, rig: Rig, uploaded: str) -> None:
        low, high = 150.0, 350.0
        raw = _values(_tile(rig, uploaded, "bidx=1&bidx=2&bidx=3"))
        picture = _values(_png(rig, uploaded, f"bidx=1&bidx=2&bidx=3&rescale={low},{high}"))
        assert picture.shape[0] == 3
        for channel in range(3):
            valid = ~raw[channel].mask & ~picture[channel].mask
            expected = numpy.clip((raw[channel].data[valid] - low) / (high - low) * 255, 0, 255)
            assert numpy.abs(picture[channel].data[valid].astype(float) - expected).max() <= 1.0
        # Band 1 lies below the range, band 3 above it: a range of its own for each would not show that.
        assert picture[0].max() < 128 < picture[2].min()

    def test_a_range_for_each_channel_stretches_each_by_its_own(self, rig: Rig, uploaded: str) -> None:
        """UI-03d: ``rescale`` three times, in the order of ``bidx``."""
        ranges = ((100.0, 101.0), (200.0, 201.0), (300.0, 301.0))
        raw = _values(_tile(rig, uploaded, "bidx=1&bidx=2&bidx=3"))
        query = "bidx=1&bidx=2&bidx=3&" + "&".join(f"rescale={low},{high}" for low, high in ranges)
        picture = _values(_png(rig, uploaded, query))
        for channel, (low, high) in enumerate(ranges):
            valid = ~raw[channel].mask & ~picture[channel].mask
            expected = numpy.clip((raw[channel].data[valid] - low) / (high - low) * 255, 0, 255)
            assert numpy.abs(picture[channel].data[valid].astype(float) - expected).max() <= 1.0
            # Counter-check: each band lies inside its own range; one shared range would leave two of them at 0 or 255.
            assert 0 < numpy.ma.median(picture[channel]) < 255

    def test_a_colormap_on_three_bands_is_refused_and_not_a_server_error(self, rig: Rig, uploaded: str) -> None:
        z, x, y = TILE
        query = "bidx=1&bidx=2&bidx=3&rescale=0,500&colormap_name=viridis"
        response = rig.client.get(f"/results/{uploaded}/tiles/WebMercatorQuad/{z}/{x}/{y}.png?{query}")
        assert response.status_code == 400, response.text

    def test_a_colormap_on_one_band_still_draws(self, rig: Rig, uploaded: str) -> None:
        _png(rig, uploaded, "bidx=2&rescale=150,250&colormap_name=viridis")

    def test_the_colormaps_added_to_rio_tilers_draw_a_result_too(self, rig: Rig, uploaded: str) -> None:
        """UI-03d: the result route takes the colormaps of `access/colormaps.py`, reversed ones included."""
        assert _png(rig, uploaded, "bidx=2&rescale=150,250&colormap_name=mako") != _png(rig, uploaded, "bidx=2&rescale=150,250&colormap_name=mako_r")

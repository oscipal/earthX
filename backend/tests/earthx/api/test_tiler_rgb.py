"""The tile of steps of version 2 shows three bands as one colour picture (NM4-64).

``band=`` three times names the channels in the order red, green, blue. The tile reads the assets the three need and
nothing else, its values are those of a job that asks for the three bands, and the picture takes one scale for all of
them and no colormap. The synthetic item is that of `test_tiler_band`: three 10 m bands (``red``, ``nir``, ``green``)
and a 20 m classification layer.
"""

# The fixtures are imported from the module of the item and used by name: F811 would flag every use.
# ruff: noqa: F811

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

import numpy
import pytest

from tests.earthx.api.test_tiler_band import (  # noqa: F401 - fixtures
    MASK,
    NDVI,
    NDWI,
    Rig,
    _job,
    _job_tile,
    _same_as_the_job,
    _url,
    files,
    rig,
)
from tests.earthx.api.test_tiler_chain import _decode
from tests.earthx.api.test_tiler_mask_normalize import COG, ITEM
from tests.earthx.api.test_tiler_operator import NATIVE, _tiles

CHAIN_NDVI = [("band_math", NDVI)]
ASSETS = ("red", "nir", "green", "scl")
RGB = ("nir", "red", "green")  # not the order of the item, so that the order of the URL is what counts


def _bands(*names: str) -> str:
    return "&" + "&".join(f"band={quote(name)}" for name in names)


class TestTheThreeBandsEqualTheJobOnTheNativeLevel:
    """The tile through the real route against a job that asks for the same three bands, bit for bit."""

    @pytest.mark.parametrize("size", NATIVE)
    def test_three_bands_of_the_item_in_the_order_of_the_url(self, rig: Rig, tmp_path: Path, size: int) -> None:
        chain = [("mask", MASK)]
        job = _job(tmp_path, chain, list(RGB), ASSETS)
        compared = 0
        for tile in _tiles(NATIVE[size]):
            response = rig.get(_url(chain, tile=tile, size=size) + _bands(*RGB))
            assert response.status_code == 200, response.text
            from_tile = _decode(response.content)
            assert from_tile.shape[0] == 3
            from_job = _job_tile(job, tile, size)
            for channel in range(3):
                compared += _same_as_the_job(from_tile[channel], from_job[channel], (tile, channel))
        assert compared > 30_000

    @pytest.mark.parametrize("size", NATIVE)
    def test_a_band_that_a_step_added_can_be_a_channel(self, rig: Rig, tmp_path: Path, size: int) -> None:
        chain = [("band_math", NDVI), ("band_math", NDWI)]
        shown = ("NDWI", "red", "NDVI")
        job = _job(tmp_path, chain, list(shown), ("red", "nir", "green"))
        for tile in _tiles(NATIVE[size]):
            response = rig.get(_url(chain, tile=tile, size=size, assets=("red", "nir", "green")) + _bands(*shown))
            assert response.status_code == 200, response.text
            from_tile = _decode(response.content)
            assert from_tile.shape[0] == 3
            from_job = _job_tile(job, tile, size)
            for channel in range(3):
                _same_as_the_job(from_tile[channel], from_job[channel], (tile, channel))


class TestWhatTheTileReads:
    def test_it_reads_the_assets_the_three_bands_need_and_no_other(self, rig: Rig) -> None:
        response = rig.get(_url(CHAIN_NDVI, assets=("red", "nir", "green", "scl")) + _bands("red", "green", "NDVI"))
        assert response.status_code == 200, response.text
        assert rig.opened_names == {"red", "nir", "green"}

    def test_without_the_mask_the_layer_is_not_read(self, rig: Rig) -> None:
        response = rig.get(_url([("band_math", NDVI)], assets=ASSETS) + _bands("red", "green", "nir"))
        assert response.status_code == 200, response.text
        assert "scl" not in rig.opened_names


class TestTheRenderedPicture:
    """One scale for the three channels; the PNG is what the raw values say through that scale."""

    RANGE = (0.05, 0.45)

    def _png(self, rig: Rig, tile: tuple[int, int, int], *, extra: str = "") -> numpy.ndarray:
        z, x, y = tile
        url = _url(CHAIN_NDVI, tile=tile).replace(f"{x}/{y}.tif", f"{x}/{y}.png")
        response = rig.get(url + _bands(*RGB) + f"&rescale={self.RANGE[0]},{self.RANGE[1]}" + extra)
        assert response.status_code == 200, response.text
        return _decode(response.content)

    def test_all_three_channels_are_stretched_by_the_same_range(self, rig: Rig) -> None:
        tile = _tiles()[len(_tiles()) // 2]
        raw = _decode(rig.get(_url(CHAIN_NDVI, tile=tile) + _bands(*RGB)).content)
        picture = self._png(rig, tile)
        assert picture.shape[0] == 3
        low, high = self.RANGE
        checked = 0
        for channel in range(3):
            valid = ~numpy.ma.getmaskarray(raw[channel]) & ~numpy.ma.getmaskarray(picture[channel])
            expected = numpy.clip((raw[channel].data[valid] - low) / (high - low) * 255, 0, 255)
            assert numpy.abs(picture[channel].data[valid].astype(float) - expected).max() <= 1.0
            checked += int(valid.sum())
        assert checked > 10_000
        # Three different bands under one range: the channels differ, so none was stretched by a range of its own.
        assert not numpy.array_equal(picture[0].data, picture[1].data)

    def test_a_colormap_is_a_400_before_the_item_is_fetched(self, rig: Rig) -> None:
        response = rig.get(_url(CHAIN_NDVI) + _bands(*RGB) + "&rescale=0,1&colormap_name=viridis")
        assert response.status_code == 400, response.text
        assert "colormap" in response.json()["detail"]
        assert rig.fetched == []

    def test_a_colormap_given_as_json_is_a_400_too(self, rig: Rig) -> None:
        cmap = quote(json.dumps({"0": [0, 0, 0, 255], "255": [255, 255, 255, 255]}))
        assert rig.get(_url(CHAIN_NDVI) + _bands(*RGB) + f"&colormap={cmap}").status_code == 400
        assert rig.fetched == []

    def test_one_band_still_takes_a_colormap(self, rig: Rig) -> None:
        z, x, y = _tiles()[1]
        url = _url(CHAIN_NDVI, tile=(z, x, y)).replace(f"{x}/{y}.tif", f"{x}/{y}.png")
        response = rig.get(url + _bands("NDVI") + "&rescale=-1,1&colormap_name=viridis")
        assert response.status_code == 200, response.text

    def test_a_range_of_its_own_for_each_channel_is_a_400(self, rig: Rig) -> None:
        response = rig.get(_url(CHAIN_NDVI) + _bands(*RGB) + "&rescale=0,1&rescale=0,2&rescale=0,3")
        assert response.status_code == 400 and "one rescale" in response.json()["detail"]
        assert rig.fetched == []


class TestWhatIsRefused:
    @pytest.mark.parametrize("names", [("red", "nir"), ("red", "nir", "green", "NDVI")])
    def test_other_than_one_or_three_bands_is_a_400_before_the_item_is_fetched(
        self, rig: Rig, names: tuple[str, ...]
    ) -> None:
        response = rig.get(_url(CHAIN_NDVI) + _bands(*names))
        assert response.status_code == 400, response.text
        assert rig.fetched == []

    def test_a_band_twice_is_a_400(self, rig: Rig) -> None:
        response = rig.get(_url(CHAIN_NDVI) + _bands("red", "red", "nir"))
        assert response.status_code == 400 and "each band once" in response.json()["detail"]
        assert rig.fetched == []

    def test_an_empty_name_among_three_is_a_400(self, rig: Rig) -> None:
        assert rig.get(_url(CHAIN_NDVI) + "&band=red&band=&band=nir").status_code == 400
        assert rig.fetched == []

    def test_a_band_the_steps_do_not_leave_is_a_422_that_names_it(self, rig: Rig) -> None:
        response = rig.get(_url(CHAIN_NDVI) + _bands("red", "blue", "nir"))
        assert response.status_code == 422 and "'blue'" in response.json()["detail"]
        assert rig.opened == []

    def test_three_bands_next_to_a_step_of_version_1_are_a_400(self, rig: Rig) -> None:
        steps = [("band_math", {"expression": "nir - red"})]
        response = rig.get(_url(steps, versions=(1,)) + _bands(*RGB))
        assert response.status_code == 400 and "version 2" in response.json()["detail"]

    def test_three_bands_without_op_are_a_400(self, rig: Rig) -> None:
        z, x, y = _tiles()[1]
        url = f"/collections/{COG}/items/{ITEM}/tiles/WebMercatorQuad/{z}/{x}/{y}.tif?asset=red" + _bands(*RGB)
        assert rig.get(url).status_code == 400


class TestTheTileJsonAndTheStatistics:
    def test_the_tilejson_names_the_three_bands_and_the_tiles_carry_them_in_order(self, rig: Rig) -> None:
        response = rig.get(_url(CHAIN_NDVI, route="WebMercatorQuad/tilejson.json") + _bands(*RGB))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["bands"] == list(RGB) and "band" not in body
        (template,) = body["tiles"]
        carried = parse_qs(urlsplit(template).query)
        assert carried["band"] == list(RGB)
        assert set(carried) <= {"asset", "op", "op_version", "params", "band", "tilesize", "rescale"}  # no id, no hash

    def test_the_tilejson_of_one_band_is_as_before(self, rig: Rig) -> None:
        body = rig.get(_url(CHAIN_NDVI, route="WebMercatorQuad/tilejson.json") + _bands("NDVI")).json()
        assert body["band"] == "NDVI" and "bands" not in body

    def test_the_tilejson_with_a_colormap_is_a_400(self, rig: Rig) -> None:
        url = _url(CHAIN_NDVI, route="WebMercatorQuad/tilejson.json") + _bands(*RGB) + "&colormap_name=viridis"
        assert rig.get(url).status_code == 400

    def test_the_statistics_have_an_entry_per_channel_that_is_the_one_of_the_band_alone(self, rig: Rig) -> None:
        three = rig.get(_url(CHAIN_NDVI, route="statistics") + _bands(*RGB))
        assert three.status_code == 200, three.text
        entries = list(three.json().values())
        assert len(entries) == 3
        for channel, name in enumerate(RGB):
            (alone,) = rig.get(_url(CHAIN_NDVI, route="statistics") + _bands(name)).json().values()
            assert entries[channel]["mean"] == pytest.approx(alone["mean"])
            assert entries[channel]["min"] == pytest.approx(alone["min"])
            assert entries[channel]["max"] == pytest.approx(alone["max"])

    def test_two_orders_of_the_same_bands_are_two_questions_for_the_cache(self, rig: Rig) -> None:
        forward = list(rig.get(_url(CHAIN_NDVI, route="statistics") + _bands("red", "nir", "green")).json().values())
        backward = list(rig.get(_url(CHAIN_NDVI, route="statistics") + _bands("green", "nir", "red")).json().values())
        assert forward[0]["mean"] == pytest.approx(backward[2]["mean"]) and forward[0]["mean"] != backward[0]["mean"]

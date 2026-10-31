"""The mosaic tile with steps of version 2 shows three bands as one colour picture (NM4-64).

The scenes and the job of `test_tiler_mosaic_band`; ``band=`` three times names the channels, red, green, blue.
"""

# The fixtures are imported from the module of the scenes and used by name: F811 would flag every use.
# ruff: noqa: F811

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import numpy
import pytest

from tests.earthx.api.test_tiler_chain import _decode
from tests.earthx.api.test_tiler_mosaic_band import (  # noqa: F401 - fixtures
    CHAIN,
    DATASET,
    NATIVE,
    NDVI,
    Source,
    _job,
    _job_tile,
    _opened_names,
    _tiles,
    _url,
    client,
    files,
    source,
)

SHOWN = ("Ratio", "red", "NDVI")  # a result, a band of the scenes, a result; not the order of the stock


def _bands(*names: str) -> str:
    return "&" + "&".join(f"band={quote(name)}" for name in names)


class TestTheThreeBandsEqualTheMosaicJobOnTheNativeLevel:
    @pytest.mark.parametrize("size", NATIVE)
    def test_the_channels_are_the_bands_of_the_job_in_the_order_of_the_url(self, client, tmp_path: Path, size: int) -> None:
        job = _job(tmp_path, CHAIN, list(SHOWN), ("red", "nir", "scl"))
        api = client()
        compared = 0
        for tile in _tiles(NATIVE[size]):
            response = api.get(_url(tile, size=size) + _bands(*SHOWN))
            assert response.status_code == 200, response.text
            from_tile, from_job = _decode(response.content), _job_tile(job, tile, size)
            assert from_tile.shape[0] == 3 and from_tile.shape[1:] == from_job.shape[1:], tile
            for channel in range(3):
                assert numpy.array_equal(from_tile[channel].mask, numpy.ma.getmaskarray(from_job[channel])), tile
                valid = ~from_tile[channel].mask
                assert numpy.array_equal(from_tile[channel].data[valid], from_job[channel].data[valid]), (tile, channel)
                compared += int(valid.sum())
        assert compared > 100_000


class TestWhatIsRead:
    def test_the_assets_of_the_three_bands_are_opened_and_no_others(self, client, source: Source) -> None:
        tile = _tiles()[len(_tiles()) // 2]
        steps = [("band_math", NDVI)]
        response = client().get(_url(tile, steps, assets=("red", "nir", "scl")) + _bands("red", "nir", "NDVI"))
        assert response.status_code == 200, response.text
        assert _opened_names(source) == {"red", "nir"}


class TestARefusedPicture:
    def test_a_colormap_is_a_400_before_the_first_item(self, client, source: Source) -> None:
        response = client().get(_url(_tiles()[0]) + _bands(*SHOWN) + "&rescale=0,1&colormap_name=viridis")
        assert response.status_code == 400 and "colormap" in response.json()["detail"], response.text
        assert source.fetched == []

    def test_a_range_for_each_channel_is_a_400_before_the_first_item(self, client, source: Source) -> None:
        response = client().get(_url(_tiles()[0]) + _bands(*SHOWN) + "&rescale=0,1&rescale=0,2&rescale=0,3")
        assert response.status_code == 400, response.text
        assert source.fetched == []

    @pytest.mark.parametrize("names", [("red", "nir"), ("red", "red", "nir"), ("red", "nir", "NDVI", "Ratio")])
    def test_two_four_or_a_repeated_band_is_a_400_before_the_first_item(
        self, client, source: Source, names: tuple[str, ...]
    ) -> None:
        assert client().get(_url(_tiles()[0]) + _bands(*names)).status_code == 400
        assert source.fetched == []

    def test_a_channel_the_steps_do_not_leave_is_a_422_with_its_name_before_a_file_is_opened(
        self, client, source: Source
    ) -> None:
        response = client().get(_url(_tiles()[0]) + _bands("red", "EVI", "NDVI"))
        assert response.status_code == 422 and "'EVI'" in response.json()["detail"], response.text
        assert source.opened == []

    def test_three_bands_without_steps_are_a_400(self, client, source: Source) -> None:
        plain = f"/collections/{DATASET}/mosaic/tiles/WebMercatorQuad/{'/'.join(map(str, _tiles()[0]))}.tif"
        assert client().get(f"{plain}?item=A&item=B&asset=red" + _bands(*SHOWN)).status_code == 400
        assert source.fetched == []


class TestTheTileJson:
    def test_it_names_the_three_bands_and_the_tiles_carry_them_in_order(self, client) -> None:
        body = client().get(_url(None) + _bands(*SHOWN)).json()
        assert body["bands"] == list(SHOWN) and "band" not in body
        template = body["tiles"][0]
        positions = [template.index(f"band={quote(name)}") for name in SHOWN]
        assert positions == sorted(positions)
        assert "hash" not in template

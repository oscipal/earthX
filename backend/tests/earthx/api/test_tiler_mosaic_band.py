"""The mosaic tile with steps of version 2 shows one band (NM4-43d, adr/0020 §10).

The scenes and the job of `test_tiler_mosaic_operator`, with steps of version 2: ``band=`` names the band, the tile
reads only the assets that band needs, and the limit of four assets counts those. ``extra1`` … ``extra4`` are more
names for each scene's ``red`` file, which only the limits need.
"""

# The fixtures are imported from the module of the scenes and used by name: F811 would flag every use.
# ruff: noqa: F811

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from urllib.parse import quote

import numpy
import pytest
from fastapi.testclient import TestClient

from earthx.api import mosaic_tiles
from earthx.processing import run
from earthx.processing.operators import REGISTRY as OPERATORS
from earthx.processing.recipe import recipe_from_data
from tests.earthx.api.mosaic_selections import create
from tests.earthx.api.test_tiler_chain import _decode
from tests.earthx.api.test_tiler_mosaic_operator import (  # noqa: F401 - fixtures
    DATASET,
    NATIVE,
    Source,
    _job_tile,
    _recipe,
    _tiles,
    client,
    files,
    source,
)

EXTRA = tuple(f"extra{i}" for i in range(1, 5))
NDVI = {"expression": "(nir - red) / (nir + red)", "name": "NDVI"}
RATIO = {"expression": "red / nir", "name": "Ratio"}
MASK_V2 = {"source": "scl", "classes": [8, 9]}
CHAIN = [("mask", MASK_V2), ("band_math", NDVI), ("band_math", RATIO)]


def _steps(steps: Sequence[tuple[str, dict]], band: str | None) -> list[str]:
    parts = []
    for op, params in steps:
        parts += [f"op={op}", "op_version=2", f"params={quote(json.dumps(params))}"]
    return parts + ([f"band={quote(band)}"] if band is not None else [])


def _url(
    api: TestClient,
    tile: tuple[int, int, int] | None,
    steps: Sequence[tuple[str, dict]] = CHAIN,
    *,
    band: str | None = None,
    assets: Sequence[str] = ("red", "nir", "scl"),
    size: int = 256,
) -> str:
    """The URL of a tile or TileJSON of the selection of A and B read from ``assets``, created through ``api`` first."""
    selection = create(api, DATASET, ["B", "A"], assets)
    query = [*_steps(steps, band), *([f"tilesize={size}"] if size != 256 else [])]
    path = "WebMercatorQuad/tilejson.json" if tile is None else f"tiles/WebMercatorQuad/{tile[0]}/{tile[1]}/{tile[2]}.tif"
    return f"/collections/{DATASET}/mosaic/{selection}/{path}?{'&'.join(query)}"


def _get(api: TestClient, *args: Any, **options: Any) -> Any:
    return api.get(_url(api, *args, **options))


def _job(tmp_path: Path, steps: Sequence[tuple[str, dict]], bands: list[str], assets: Sequence[str]) -> Path:
    data = _recipe(assets, [])
    data["recipe_version"] = 2
    data["steps"] = [{"op": op, "op_version": 2, "params": params} for op, params in steps]
    data["output"]["bands"] = bands
    recipe = recipe_from_data(data, OPERATORS)
    return run(recipe, workdir=tmp_path, progress=lambda done, total: None, operators=OPERATORS).path


def _opened_names(source: Source) -> set[str]:
    return {Path(url.split("?")[0]).stem.split("-")[-1] for url in source.opened}


class TestTheBandEqualsTheMosaicJobOnTheNativeLevel:
    @pytest.mark.parametrize("size", NATIVE)
    @pytest.mark.parametrize(("band", "index"), [("NDVI", 0), ("Ratio", 1)])
    def test_band_chooses_one_of_two_results(self, client, tmp_path: Path, band: str, index: int, size: int) -> None:
        job = _job(tmp_path, CHAIN, ["NDVI", "Ratio"], ("red", "nir", "scl"))
        api = client()
        compared = 0
        for tile in _tiles(NATIVE[size]):
            response = _get(api, tile, band=band, size=size)
            assert response.status_code == 200, response.text
            from_tile, from_job = _decode(response.content), _job_tile(job, tile, size)[index]
            assert from_tile.shape[0] == 1 and from_tile[0].shape == from_job.shape, tile
            assert numpy.array_equal(from_tile[0].mask, numpy.ma.getmaskarray(from_job)), tile
            valid = ~from_tile[0].mask
            assert numpy.array_equal(from_tile[0].data[valid], from_job.data[valid]), tile
            compared += int(valid.sum())
        assert compared > 50_000

    def test_without_band_it_is_the_last_result(self, client, tmp_path: Path) -> None:
        job = _job(tmp_path, CHAIN, ["Ratio"], ("red", "nir", "scl"))
        tile = _tiles()[len(_tiles()) // 2]
        response = _get(client(), tile)
        assert response.status_code == 200, response.text
        from_tile, from_job = _decode(response.content)[0], _job_tile(job, tile, 256)[0]
        valid = ~from_tile.mask
        assert valid.sum() > 5_000 and numpy.array_equal(from_tile.data[valid], from_job.data[valid])


class TestOnlyWhatTheBandNeedsIsRead:
    def test_the_assets_of_the_band_are_opened_and_no_others(self, client, source: Source) -> None:
        tile = _tiles()[len(_tiles()) // 2]
        steps = [("band_math", NDVI), ("band_math", RATIO)]
        assert _get(client(), tile, steps, band="Ratio", assets=("red", "nir", "scl")).status_code == 200
        assert _opened_names(source) == {"red", "nir"}

    def test_a_mask_before_the_band_makes_its_layer_needed(self, client, source: Source) -> None:
        tile = _tiles()[len(_tiles()) // 2]
        assert _get(client(), tile, band="Ratio").status_code == 200
        assert _opened_names(source) == {"red", "nir", "scl"}

    def test_four_names_and_three_read_are_accepted(self, client, source: Source) -> None:
        for scene in source.items.values():
            scene["assets"][EXTRA[0]] = dict(scene["assets"]["red"])
        tile = _tiles()[len(_tiles()) // 2]
        steps = [("mask", MASK_V2), ("band_math", NDVI)]
        response = _get(client(), tile, steps, assets=("red", "nir", "scl", EXTRA[0]))
        assert response.status_code == 200, response.text
        assert _opened_names(source) == {"red", "nir", "scl"}

    def test_five_names_are_refused_when_the_selection_is_created_and_nothing_is_fetched(
        self, client, source: Source
    ) -> None:
        for scene in source.items.values():
            for name in EXTRA:
                scene["assets"][name] = dict(scene["assets"]["red"])
        response = client().post(
            f"/collections/{DATASET}/mosaic", json={"items": ["A", "B"], "assets": ["red", "nir", *EXTRA[:3]]}
        )
        assert response.status_code == 400, response.text
        assert str(mosaic_tiles.MAX_MOSAIC_OPERATOR_ASSETS) in response.json()["detail"]
        assert source.fetched == [] and source.batches == [] and source.opened == []


class TestARefusedBand:
    """What the steps and the stored description of the assets decide is refused by the tile and by the TileJSON alike,
    before an item is fetched (M5-30b part 3, F5)."""

    @pytest.mark.parametrize("route", ["tile", "tilejson"])
    def test_an_unknown_band_is_a_422_with_its_name_before_an_item_is_fetched(
        self, client, source: Source, route: str
    ) -> None:
        response = _get(client(), None if route == "tilejson" else _tiles()[0], band="EVI")
        assert response.status_code == 422, response.text
        assert "'EVI'" in response.json()["detail"]
        assert source.fetched == [] and source.opened == []

    def test_two_bands_and_a_band_without_steps_are_a_400_before_the_first_item(self, client, source: Source) -> None:
        api = client()
        assert api.get(_url(api, _tiles()[0], band="NDVI") + "&band=Ratio").status_code == 400
        assert _get(api, _tiles()[0], [], assets=("red",)).status_code == 200
        source.fetched.clear()
        assert api.get(_url(api, _tiles()[0], [], assets=("red",)) + "band=red").status_code == 400
        assert source.fetched == []


class TestTheTileJson:
    def test_it_names_the_band_from_the_stored_description_and_the_tiles_carry_it(self, client, source: Source) -> None:
        for band, shown in ((None, "Ratio"), ("NDVI", "NDVI")):
            body = _get(client(), None, band=band).json()
            assert body["band"] == shown and "bands" not in body and body["earthx:order"] == ["A", "B"]
            assert body["data_type"] == "float32"
            assert source.fetched == [] and source.opened == []
            assert ("band=NDVI" in body["tiles"][0]) is (band is not None)
            assert "hash" not in body["tiles"][0] and "item=" not in body["tiles"][0]

    def test_it_names_the_unit_of_the_band_the_steps_leave(self, client, source: Source) -> None:
        for name in "AB":
            for asset in ("red", "nir"):
                bands = source.items[name]["assets"][asset]["raster:bands"]
                source.items[name]["assets"][asset]["raster:bands"] = [{**bands[0], "unit": "m"}]
        shown = _get(client(), None, band="red").json()
        assert shown["band"] == "red" and shown["unit"] == "m"
        assert source.fetched == [] and source.opened == []

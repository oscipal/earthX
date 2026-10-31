"""``mask_values`` as a tile: T1 against T2, and the refusals (plan DS-06 §8.5, §10).

The tile runs the chain the planner keeps for the band it shows (NM4-43d), so a mask over a result is a tile like any
other step of version 2. The comparison with the job is bit for bit on the native level, as in ``test_tiler_band``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from earthx.api.tiler import build_app
from earthx.catalog.registry import DatasetRegistry, LicenseTier
from earthx.gateway import check_url
from earthx.processing import run
from earthx.processing.operators import REGISTRY as OPERATORS
from earthx.processing.recipe import recipe_from_data
from tests.earthx.api.test_tiler_band import (  # noqa: F401 - fixture
    ITEM_JSON,
    NDVI,
    Rig,
    _decode,
    _job_tile,
    _same_as_the_job,
    files,
)
from tests.earthx.api.test_tiler_band import _recipe as _band_recipe
from tests.earthx.api.test_tiler_band import _url as _band_url
from tests.earthx.api.test_tiler_mask_normalize import COG, COG_DATASET
from tests.earthx.api.test_tiler_operator import NATIVE, _tiles
from tests.earthx.processing import sources
from tests.earthx.readers import mini_zarr

DARK = {"band": "NDVI", "condition": "lt", "values": [0.5]}
GREEN = {"band": "green", "condition": "between", "values": [0.15, 0.3]}
OFF = replace(
    COG_DATASET,
    dataset_id="synthetic-no-value-mask",
    capabilities=replace(COG_DATASET.capabilities, value_masking=False),
)
DISPLAY_ONLY = replace(
    COG_DATASET, dataset_id="synthetic-display", license=replace(COG_DATASET.license, tier=LicenseTier.DISPLAY)
)


def _rig(served: dict, monkeypatch: pytest.MonkeyPatch, registry: DatasetRegistry) -> Iterator[Rig]:
    opened = sources.serve({sources.url(name): path for name, path in served.items()}, monkeypatch)
    for module in ("earthx.readers.cog", "earthx.readers.zarr_reader"):
        monkeypatch.setattr(
            f"{module}.check_url", lambda url, policy, **_: check_url(url, policy, resolve=mini_zarr.from_memory)
        )
    fetched: list[str] = []

    async def item_source(dataset_id: str, item_id: str) -> dict[str, Any]:
        fetched.append(item_id)
        return json.loads(json.dumps(ITEM_JSON))

    @asynccontextmanager
    async def lifespan(app):
        app.state.earthx_item_source = item_source
        yield

    app = build_app(registry, lifespan=lifespan)
    app.state.earthx_resolver = mini_zarr.from_memory
    with TestClient(app) as client:
        yield Rig(client, fetched, opened)


@pytest.fixture
def rig(files, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:  # noqa: F811
    yield from _rig(files, monkeypatch, DatasetRegistry((COG_DATASET, OFF, DISPLAY_ONLY)))


#: The version of each operator the tests name; `_band_url` sends version 2 for every step by default.
VERSIONS = {"band_math": 2, "mask_values": 1}


def _url(steps, **kwargs: Any) -> str:
    return _band_url(steps, versions=[VERSIONS[op] for op, _ in steps], **kwargs)


def _job(tmp_path: Path, steps, bands: list[str], assets) -> Path:
    data = _band_recipe(steps, bands, assets)
    for step in data["steps"]:
        step["op_version"] = VERSIONS[step["op"]]
    recipe = recipe_from_data(data, OPERATORS)
    return run(recipe, workdir=tmp_path, progress=lambda done, total: None, operators=OPERATORS).path


def _on(dataset: str, steps, **kwargs: Any) -> str:
    return _url(steps, **kwargs).replace(f"/collections/{COG}/", f"/collections/{dataset}/", 1)


class TestTheTileEqualsTheJobOnTheNativeLevel:
    @pytest.mark.parametrize("size", NATIVE)
    def test_a_mask_over_a_result_shows_the_result_without_the_pixels_it_hides(
        self, rig: Rig, tmp_path, size: int
    ) -> None:
        chain = [("band_math", NDVI), ("mask_values", DARK)]
        job = _job(tmp_path, chain, ["NDVI"], ("red", "nir"))
        compared = hidden = 0
        for tile in _tiles(NATIVE[size]):
            response = rig.get(_url(chain, band="NDVI", tile=tile, size=size, assets=("red", "nir")))
            assert response.status_code == 200, response.text
            from_tile = _decode(response.content)
            compared += _same_as_the_job(from_tile[0], _job_tile(job, tile, size)[0], tile)
            hidden += int(from_tile[0].mask.sum())
        assert compared > 10_000 and hidden > 0

    @pytest.mark.parametrize("size", NATIVE)
    def test_a_band_of_the_data_that_is_not_shown_still_decides(self, rig: Rig, tmp_path, size: int) -> None:
        chain = [("mask_values", GREEN)]
        job = _job(tmp_path, chain, ["red"], ("red", "green"))
        compared = hidden = 0
        for tile in _tiles(NATIVE[size]):
            response = rig.get(_url(chain, band="red", tile=tile, size=size, assets=("red", "green")))
            assert response.status_code == 200, response.text
            from_tile = _decode(response.content)
            compared += _same_as_the_job(from_tile[0], _job_tile(job, tile, size)[0], tile)
            hidden += int(from_tile[0].mask.sum())
        assert compared > 10_000 and hidden > 0

    def test_the_mask_hides_more_with_a_higher_threshold(self, rig: Rig) -> None:
        few = {"band": "NDVI", "condition": "lt", "values": [0.35]}
        hidden = {0.35: 0, 0.5: 0}
        for tile in _tiles():
            for threshold, params in ((0.35, few), (0.5, DARK)):
                response = rig.get(_url([("band_math", NDVI), ("mask_values", params)], band="NDVI", tile=tile))
                assert response.status_code == 200, response.text
                hidden[threshold] += int(_decode(response.content)[0].mask.sum())
        assert hidden[0.5] > hidden[0.35] > 0

    def test_it_reads_the_band_that_decides_and_nothing_else(self, rig: Rig) -> None:
        response = rig.get(_url([("mask_values", GREEN)], band="red", assets=("red", "nir", "green", "scl")))
        assert response.status_code == 200, response.text
        assert rig.opened_names == {"red", "green"}


class TestRefusals:
    def test_a_dataset_that_has_not_switched_it_on_is_a_422_naming_the_flag(self, rig: Rig) -> None:
        response = rig.get(_on(OFF.dataset_id, [("mask_values", GREEN)], band="red"))
        assert response.status_code == 422 and "value_masking" in response.json()["detail"]

    def test_the_display_tier_does_not_run_operators(self, rig: Rig) -> None:
        response = rig.get(_on(DISPLAY_ONLY.dataset_id, [("mask_values", GREEN)], band="red"))
        assert response.status_code == 422 and "does not allow processing" in response.json()["detail"]

    def test_a_band_that_is_not_in_the_chain_is_a_422_naming_it(self, rig: Rig) -> None:
        response = rig.get(_url([("mask_values", DARK)], band="red"))
        assert response.status_code == 422 and "NDVI" in response.json()["detail"]

    def test_a_result_that_a_later_step_adds_is_not_there_yet(self, rig: Rig) -> None:
        response = rig.get(_url([("mask_values", DARK), ("band_math", NDVI)], band="NDVI"))
        assert response.status_code == 422 and "NDVI" in response.json()["detail"]

    def test_the_refusals_cost_no_request_to_the_source(self, rig: Rig) -> None:
        rig.get(_on(OFF.dataset_id, [("mask_values", GREEN)], band="red"))
        rig.get(_on(DISPLAY_ONLY.dataset_id, [("mask_values", GREEN)], band="red"))
        rig.get(_url([("mask_values", {"band": "red", "condition": "between", "values": [2, 1]})], band="red"))
        assert rig.fetched == [] and rig.opened == []

    @pytest.mark.parametrize(
        "params",
        [
            {"band": "red", "condition": "le", "values": [1]},
            {"band": "red", "condition": "between", "values": [2, 1]},
            {"band": "red", "condition": "eq", "values": [3, 1]},
            {"band": "red", "condition": "lt", "values": [True]},
            {"band": "red", "condition": "lt", "values": [1e39]},
            {"band": "red", "condition": "lt"},
            {"source": "scl", "classes": [3]},
        ],
    )
    def test_malformed_parameters_are_a_400_and_never_a_500(self, rig: Rig, params: dict) -> None:
        response = rig.get(_url([("mask_values", params)], band="red"))
        assert response.status_code == 400, response.text
        assert response.json()["detail"].startswith("params: ") or "params" in response.json()["detail"]

    def test_the_step_is_for_tiles_their_tilejson_and_statistics_the_same_way(self, rig: Rig) -> None:
        route = "WebMercatorQuad/tilejson.json"
        assert rig.get(_url([("mask_values", GREEN)], band="red", route=route)).status_code == 200

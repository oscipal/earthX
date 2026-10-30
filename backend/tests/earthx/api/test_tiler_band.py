"""The tile of steps of version 2 shows one band of the stock (NM4-43d, adr/0020 §10).

``band=<name>`` names the band; without it the picture is the last band a ``band_math`` step added, else the first.
The tile reads only the assets that band needs and runs the steps the planner keeps, so its values are those of a job
that asks for the band alone. The synthetic item carries three 10 m bands (``red``, ``nir``, ``green``), a 20 m
classification layer (``scl``) and seventeen more names for the ``red`` file (``x01`` … ``x17``), which only the limits
of the tile need.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

import numpy
import pytest
from fastapi.testclient import TestClient
from rio_tiler.io import Reader

from earthx.api.tiler import MAX_BAND_CHARS, MAX_OPERATOR_ASSETS, build_app
from earthx.gateway import check_url
from earthx.processing import run
from earthx.processing.operators import REGISTRY as OPERATORS
from earthx.processing.recipe import recipe_from_data
from tests.earthx.api.test_tiler_chain import _decode
from tests.earthx.api.test_tiler_mask_normalize import COG, ITEM, REGISTRY
from tests.earthx.api.test_tiler_operator import _BAND, HEIGHT, NATIVE, WIDTH, _tiles
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import resolved
from tests.earthx.processing.test_mask import scl_layer
from tests.earthx.readers import mini_zarr

EXTRA = tuple(f"x{i:02d}" for i in range(1, 18))
NDVI = {"expression": "(nir - red) / (nir + red)", "name": "NDVI"}
NDWI = {"expression": "(green - nir) / (green + nir)", "name": "NDWI"}
MASK = {"source": "scl", "classes": [3, 8, 9, 10]}
V2 = 2

ITEM_JSON = {
    "id": ITEM,
    "type": "Feature",
    "properties": {"proj:code": sources.CRS, "datetime": "2026-01-02T10:00:00Z"},
    "assets": {
        **{name: {"href": sources.url(name), "raster:bands": [_BAND]} for name in ("red", "nir", "green")},
        "scl": {"href": sources.url("scl"), "raster:bands": [{"data_type": "uint8", "nodata": 0}]},
        **{name: {"href": sources.url("red"), "raster:bands": [_BAND]} for name in EXTRA},
    },
}


@pytest.fixture(scope="module")
def files(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("tile-band")
    made = {
        name: sources.build_band_cog(root / f"{name}.tif", sources.ramp(WIDTH, HEIGHT, base))
        for name, base in (("red", 1200), ("nir", 3400), ("green", 2100))
    }
    made["scl"] = sources.build_band_cog(
        root / "scl.tif", scl_layer(WIDTH // 2, HEIGHT // 2), scale=None, offset=None, resolution=20.0
    )
    return made


class Rig:
    """The client, the items the source was asked for and the files GDAL was asked to open."""

    def __init__(self, client: TestClient, fetched: list[str], opened: list[str]) -> None:
        self.client, self.fetched, self.opened = client, fetched, opened

    def get(self, *args: Any, **kwargs: Any) -> Any:
        return self.client.get(*args, **kwargs)

    @property
    def opened_names(self) -> set[str]:
        """Which files of the item were opened, by the name the item gives their asset."""
        return {Path(urlsplit(url).path).stem for url in self.opened}


@pytest.fixture
def rig(files: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    opened = sources.serve({sources.url(name): path for name, path in files.items()}, monkeypatch)
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

    app = build_app(REGISTRY, lifespan=lifespan)
    app.state.earthx_resolver = mini_zarr.from_memory
    with TestClient(app) as client:
        yield Rig(client, fetched, opened)


def _url(
    steps: Sequence[tuple[str, dict]],
    *,
    tile: tuple[int, int, int] | None = None,
    assets: Sequence[str] = ("red", "nir", "green", "scl"),
    band: str | None = None,
    route: str | None = None,
    size: int | None = None,
    versions: Sequence[int] | None = None,
) -> str:
    query = [f"asset={quote(name)}" for name in assets]
    for number, (op, params) in enumerate(steps):
        version = V2 if versions is None else versions[number]
        query += [f"op={op}", f"op_version={version}", f"params={quote(json.dumps(params))}"]
    if band is not None:
        query.append(f"band={quote(band)}")
    if size is not None:
        query.append(f"tilesize={size}")
    z, x, y = tile or _tiles()[1]
    path = route or f"tiles/WebMercatorQuad/{z}/{x}/{y}.tif"
    return f"/collections/{COG}/items/{ITEM}/{path}?{'&'.join(query)}"


def _recipe(steps: Sequence[tuple[str, dict]], bands: list[str], assets: Sequence[str]) -> dict:
    entries = []
    for asset in assets:
        if asset == "scl":
            entry = resolved(ITEM, asset, href=sources.url(asset), scale=None, offset=None)
            entry["bands"] = [{"data_type": "uint8", "nodata": 0, "scale": None, "offset": None}]
            entry["gsd"] = 20.0
        else:
            entry = resolved(ITEM, asset, href=sources.url(asset), scale=sources.SCALE, offset=sources.OFFSET)
        entries.append(entry)
    return {
        "recipe_version": 2,
        "inputs": [
            {"name": "s2", "dataset": "synthetic", "groups": [[ITEM]], "assets": list(assets), "resolved": entries}
        ],
        "aoi": sources.whole(WIDTH, HEIGHT, inset=0.0),
        "steps": [{"op": op, "op_version": V2, "params": params} for op, params in steps],
        "output": {"kind": "raster", "format": "cog", "dtype": "float32", "bands": bands},
    }


def _job(tmp_path: Path, steps: Sequence[tuple[str, dict]], bands: list[str], assets: Sequence[str]) -> Path:
    recipe = recipe_from_data(_recipe(steps, bands, assets), OPERATORS)
    return run(recipe, workdir=tmp_path, progress=lambda done, total: None, operators=OPERATORS).path


def _job_tile(path: Path, tile: tuple[int, int, int], size: int) -> numpy.ma.MaskedArray:
    z, x, y = tile
    with Reader(str(path)) as reader:
        return reader.tile(x, y, z, resampling_method="nearest", tilesize=size).array


def _same_as_the_job(tile: numpy.ma.MaskedArray, job: numpy.ma.MaskedArray, where: object) -> int:
    assert tile.shape == job.shape, where
    assert numpy.array_equal(tile.mask, numpy.ma.getmaskarray(job)), where
    valid = ~tile.mask
    assert numpy.array_equal(tile.data[valid], job.data[valid]), where
    return int(valid.sum())


class TestTheBandEqualsTheJobOnTheNativeLevel:
    """The tile of one band, through the real route, against a job that asks for that band alone, bit for bit."""

    CHAIN = [("mask", MASK), ("band_math", NDVI), ("band_math", NDWI)]

    @pytest.mark.parametrize("size", NATIVE)
    @pytest.mark.parametrize(("band", "index"), [("NDVI", 0), ("NDWI", 1)])
    def test_two_band_math_steps_band_chooses_one(self, rig: Rig, tmp_path: Path, band: str, index: int, size: int) -> None:
        job = _job(tmp_path, self.CHAIN, ["NDVI", "NDWI"], ("red", "nir", "green", "scl"))
        compared = 0
        for tile in _tiles(NATIVE[size]):
            response = rig.get(_url(self.CHAIN, band=band, tile=tile, size=size))
            assert response.status_code == 200, response.text
            from_tile = _decode(response.content)
            assert from_tile.shape[0] == 1
            compared += _same_as_the_job(from_tile[0], _job_tile(job, tile, size)[index], tile)
        assert compared > 10_000

    @pytest.mark.parametrize("size", NATIVE)
    def test_without_band_it_is_the_last_result(self, rig: Rig, tmp_path: Path, size: int) -> None:
        job = _job(tmp_path, self.CHAIN, ["NDWI"], ("red", "nir", "green", "scl"))
        for tile in _tiles(NATIVE[size]):
            response = rig.get(_url(self.CHAIN, tile=tile, size=size))
            assert response.status_code == 200, response.text
            from_tile = _decode(response.content)
            assert from_tile.shape[0] == 1
            _same_as_the_job(from_tile[0], _job_tile(job, tile, size)[0], tile)

    def test_without_a_band_math_step_it_is_the_first_band(self, rig: Rig, tmp_path: Path) -> None:
        chain = [("mask", MASK)]
        job = _job(tmp_path, chain, ["red"], ("red", "nir", "scl"))
        tile = _tiles()[1]
        response = rig.get(_url(chain, tile=tile, assets=("red", "nir", "scl")))
        assert response.status_code == 200, response.text
        from_tile = _decode(response.content)
        assert from_tile.shape[0] == 1
        assert _same_as_the_job(from_tile[0], _job_tile(job, tile, 256)[0], tile) > 5_000

    def test_a_band_of_the_data_is_masked_like_a_result(self, rig: Rig, tmp_path: Path) -> None:
        chain = [("mask", MASK), ("band_math", NDVI)]
        job = _job(tmp_path, chain, ["nir"], ("red", "nir", "scl"))
        tile = _tiles()[1]
        response = rig.get(_url(chain, tile=tile, assets=("red", "nir", "scl"), band="nir"))
        assert response.status_code == 200, response.text
        assert _same_as_the_job(_decode(response.content)[0], _job_tile(job, tile, 256)[0], tile) > 5_000

    def test_a_normalize_of_two_bands_shows_the_one_that_is_named(self, rig: Rig, tmp_path: Path) -> None:
        convert = {"bands": ["red", "green"], "in_min": 0.0, "in_max": 0.5, "out_min": 0.0, "out_max": 255.0, "clip": True}
        chain = [("normalize", convert)]
        job = _job(tmp_path, chain, ["red"], ("red", "green"))
        tile = _tiles()[1]
        response = rig.get(_url(chain, tile=tile, assets=("red", "green"), band="red"))
        assert response.status_code == 200, response.text
        assert _same_as_the_job(_decode(response.content)[0], _job_tile(job, tile, 256)[0], tile) > 5_000
        # The planner counts every band a `normalize` names as needed (adr/0020 §4), so the tile reads what a job reads.
        assert rig.opened_names == {"red", "green"}


class TestOnlyWhatTheBandNeedsIsRead:
    def test_a_band_reads_its_own_assets_and_no_others(self, rig: Rig) -> None:
        chain = [("mask", MASK), ("band_math", NDVI), ("band_math", NDWI)]
        assert rig.get(_url(chain, band="NDVI")).status_code == 200
        assert rig.opened_names == {"red", "nir", "scl"}
        rig.opened.clear()
        assert rig.get(_url(chain, band="NDWI")).status_code == 200
        assert rig.opened_names == {"green", "nir", "scl"}

    def test_a_band_of_the_data_without_a_step_that_needs_the_others_reads_one_file(self, rig: Rig) -> None:
        assert rig.get(_url([("band_math", NDVI)], band="green")).status_code == 200
        assert rig.opened_names == {"green"}

    def test_a_step_nobody_keeps_is_not_judged(self, rig: Rig) -> None:
        """The second step names a band the URL does not carry; the band shown does not need it."""
        chain = [("band_math", NDVI), ("band_math", {"expression": "(swir - nir) / (swir + nir)", "name": "NDMI"})]
        response = rig.get(_url(chain, band="NDVI", assets=("red", "nir")))
        assert response.status_code == 200, response.text
        assert rig.opened_names == {"red", "nir"}
        assert rig.get(_url(chain, band="NDMI", assets=("red", "nir"))).status_code == 422


class TestTheLimitsHoldAfterTheBandsAreDropped:
    def test_seventeen_assets_in_the_url_and_three_read_are_accepted(self, rig: Rig) -> None:
        chain = [("mask", MASK), ("band_math", NDVI)]
        assets = ("red", "nir", "scl", *EXTRA)
        assert len(assets) > MAX_OPERATOR_ASSETS
        response = rig.get(_url(chain, assets=assets))
        assert response.status_code == 200, response.text
        assert rig.opened_names == {"red", "nir", "scl"}

    def test_a_band_that_needs_seventeen_assets_is_a_400_before_any_file_is_opened(self, rig: Rig) -> None:
        total = {"expression": " + ".join(EXTRA), "name": "Total"}
        response = rig.get(_url([("band_math", total)], assets=EXTRA))
        assert response.status_code == 400, response.text
        assert str(len(EXTRA)) in response.json()["detail"] and str(MAX_OPERATOR_ASSETS) in response.json()["detail"]
        assert rig.opened == []

    def test_sixteen_assets_that_are_all_needed_are_accepted(self, rig: Rig) -> None:
        total = {"expression": " + ".join(EXTRA[:16]), "name": "Total"}
        response = rig.get(_url([("band_math", total)], assets=EXTRA))
        assert response.status_code == 200, response.text
        assert len(rig.opened_names) == 1  # the sixteen names are one file

    def test_steps_of_version_1_keep_the_limit_on_every_asset(self, rig: Rig) -> None:
        response = rig.get(_url([("band_math", {"expression": "x01"})], assets=EXTRA, versions=(1,)))
        assert response.status_code == 400 and str(MAX_OPERATOR_ASSETS) in response.json()["detail"]
        assert rig.opened == []


class TestARefusedBand:
    def test_an_unknown_band_is_a_422_with_its_name_and_no_file_is_opened(self, rig: Rig) -> None:
        response = rig.get(_url([("band_math", NDVI)], band="EVI"))
        assert response.status_code == 422, response.text
        detail = response.json()["detail"]
        assert "'EVI'" in detail and "NDVI" in detail  # the name asked for, and what there is
        assert rig.fetched and rig.opened == []

    @pytest.mark.parametrize("route", ["WebMercatorQuad/tilejson.json", "statistics"])
    def test_the_tilejson_and_the_statistics_refuse_it_alike(self, rig: Rig, route: str) -> None:
        response = rig.get(_url([("band_math", NDVI)], band="nope", route=route))
        assert response.status_code == 422 and "'nope'" in response.json()["detail"]
        assert rig.opened == []

    def test_the_case_of_the_name_counts(self, rig: Rig) -> None:
        assert rig.get(_url([("band_math", NDVI)], band="ndvi")).status_code == 422

    @pytest.mark.parametrize("band", ["", "x" * (MAX_BAND_CHARS + 1)], ids=["empty", "too long"])
    def test_an_empty_or_long_name_is_a_400_before_the_item_is_fetched(self, rig: Rig, band: str) -> None:
        response = rig.get(f"{_url([('band_math', NDVI)])}&band={band}")
        assert response.status_code == 400, response.text
        assert rig.fetched == []

    def test_two_bands_are_a_400_before_the_item_is_fetched(self, rig: Rig) -> None:
        response = rig.get(_url([("band_math", NDVI)], band="NDVI") + "&band=red")
        assert response.status_code == 400
        assert rig.fetched == []

    def test_a_band_without_op_is_a_400(self, rig: Rig) -> None:
        z, x, y = _tiles()[1]
        response = rig.get(f"/collections/{COG}/items/{ITEM}/tiles/WebMercatorQuad/{z}/{x}/{y}.tif?asset=red&band=red")
        assert response.status_code == 400 and "band is for tiles with op" in response.json()["detail"]

    def test_a_band_next_to_a_step_of_version_1_is_a_400(self, rig: Rig) -> None:
        response = rig.get(_url([("band_math", {"expression": "nir - red"})], versions=(1,), band="band_math"))
        assert response.status_code == 400, response.text
        assert "version 2" in response.json()["detail"]

    def test_steps_of_version_1_without_band_are_as_before(self, rig: Rig) -> None:
        response = rig.get(_url([("mask", {"source": "scl", "classes": [3]})], versions=(1,), assets=("red", "nir", "scl")))
        assert response.status_code == 200, response.text
        assert _decode(response.content).shape[0] == 2  # red and nir: the layer is gone, both stay


class TestTheTileJsonAndTheStatistics:
    CHAIN = [("band_math", NDVI), ("band_math", NDWI)]

    def test_the_tilejson_names_the_band_and_its_unit_and_the_tiles_carry_the_band(self, rig: Rig) -> None:
        for band, shown in ((None, "NDWI"), ("NDVI", "NDVI")):
            response = rig.get(_url(self.CHAIN, band=band, route="WebMercatorQuad/tilejson.json"))
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["band"] == shown
            (template,) = body["tiles"]
            carried = parse_qs(urlsplit(template).query)
            assert set(carried) <= {"asset", "op", "op_version", "params", "band", "tilesize"}  # no id, no hash
            assert carried.get("band") == ([band] if band else None)

    def test_the_statistics_are_those_of_the_band_shown(self, rig: Rig) -> None:
        both = {band: rig.get(_url(self.CHAIN, band=band, route="statistics")) for band in ("NDVI", "NDWI")}
        default = rig.get(_url(self.CHAIN, route="statistics"))
        assert all(response.status_code == 200 for response in (*both.values(), default)), default.text
        (ndvi,), (ndwi,), (last,) = (list(r.json().values()) for r in (both["NDVI"], both["NDWI"], default))
        assert ndvi["mean"] != ndwi["mean"]  # the same cache key for two bands would repeat one of them
        assert last["mean"] == ndwi["mean"]
        assert -1.0 <= ndvi["min"] <= ndvi["max"] <= 1.0 and -1.0 <= ndwi["min"] <= ndwi["max"] <= 1.0

    def test_the_statistics_of_a_band_read_what_the_band_needs(self, rig: Rig) -> None:
        assert rig.get(_url(self.CHAIN, band="NDVI", route="statistics")).status_code == 200
        assert rig.opened_names == {"red", "nir"}


class TestTheColourScaleOfABandIsTheOneOfItsResult:
    """M4-32: the scale of a result's band comes from ``properties.bands[].statistics``; the preview measures the same."""

    def test_the_result_names_each_band_with_its_statistics_and_the_preview_measures_alike(
        self, rig: Rig, tmp_path: Path
    ) -> None:
        chain = [("band_math", NDVI), ("band_math", NDWI)]
        recipe = recipe_from_data(_recipe(chain, ["NDVI", "NDWI"], ("red", "nir", "green")), OPERATORS)
        result = run(recipe, workdir=tmp_path, progress=lambda done, total: None, operators=OPERATORS)
        described = {band["name"]: band["statistics"] for band in result.properties["bands"]}
        assert list(described) == ["NDVI", "NDWI"]
        for band, statistics in described.items():
            (preview,) = rig.get(_url(chain, band=band, route="statistics", assets=("red", "nir", "green"))).json().values()
            assert preview["min"] == pytest.approx(statistics["minimum"], abs=1e-6)
            assert preview["max"] == pytest.approx(statistics["maximum"], abs=1e-6)

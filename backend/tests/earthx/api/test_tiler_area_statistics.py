"""The statistics of an order's area on the tiler (NM4-19): the job's own numbers, the AOI in the body only.

``POST /collections/{dataset}/statistics`` takes the order the panel builds for a job. The answer is compared
with a run of the core on the very recipe the intake makes of the same order: the ``statistics`` of the result's
properties, field for field. The rasters are the synthetic ones of the operator tile (``red``, ``nir`` at 10 m,
``scl`` at 20 m) and the two scenes of one overpass of M4-12a; the item source is a function.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import numpy
import pytest
import rasterio
from fastapi.testclient import TestClient
from rasterio.errors import RasterioIOError, WarpOperationError
from rasterio.warp import transform_bounds
from shapely.geometry import box, mapping

import earthx
from earthx.api import area_statistics as area_module
from earthx.api.area_statistics import (
    AREA_STATISTICS_ROUTE,
    AREA_STATISTICS_TTL_S,
    MAX_AREA_BODY_BYTES,
    MAX_AREA_FILES,
    area_statistics_cache_key,
)
from earthx.api.intake import estimate_order
from earthx.api.processing_route import MAX_BODY_BYTES
from earthx.api.tiler import area_statistics_cache, build_app
from earthx.catalog.registry import DatasetRegistry
from earthx.gateway import UpstreamError
from earthx.logging import JsonFormatter
from earthx.processing import run
from earthx.processing.operators import REGISTRY as OPERATORS
from earthx.processing.recipe import recipe_hash
from earthx.processing.statistics import MEASURE_PERCENTILES
from tests.earthx.api.test_tiler_mask_normalize import COG_DATASET, DISPLAY_ONLY, MASK
from tests.earthx.api.test_tiler_operator import _BAND, HEIGHT, NDVI, WIDTH
from tests.earthx.processing import sources
from tests.earthx.processing import test_mosaic as mosaic
from tests.earthx.processing.test_mask import scl_layer

REGISTRY = DatasetRegistry((COG_DATASET, DISPLAY_ONLY))
COG = COG_DATASET.dataset_id
DAY = "2026-06-01T10:00:00Z"
TAKE = "GS2B_20260601T100031_000000_N05.11"
ROUTE = f"/collections/{COG}/statistics"


def _footprint(crs: str, x: float, y: float, width: int, height: int) -> tuple[float, float, float, float]:
    return transform_bounds(crs, "EPSG:4326", x, y - height * 10.0, x + width * 10.0, y)


def _item(item_id: str, assets: dict[str, Any], bbox: tuple[float, float, float, float], epsg: int = 32632) -> dict:
    return {
        "id": item_id,
        "type": "Feature",
        "bbox": list(bbox),
        "geometry": mapping(box(*bbox)),
        "properties": {"datetime": DAY, "s2:datatake_id": TAKE, "proj:code": f"EPSG:{epsg}"},
        "assets": assets,
    }


SCENE = _item(
    "ITEM_A",
    {
        "red": {"href": sources.url("red"), "raster:bands": [_BAND]},
        "nir": {"href": sources.url("nir"), "raster:bands": [_BAND]},
        "scl": {"href": sources.url("scl"), "raster:bands": [{"data_type": "uint8", "nodata": 0}]},
    },
    _footprint(sources.CRS, sources.ORIGIN_X, sources.ORIGIN_Y, WIDTH, HEIGHT),
)
_RED = {"data_type": "uint16", "nodata": 0, "raster:scale": sources.SCALE, "raster:offset": sources.OFFSET}
PASS = {
    name: _item(
        f"PASS_{name}",
        {"red": {"href": sources.url(f"{name}_red"), "raster:bands": [_RED]}},
        _footprint(*mosaic.GEOMETRY[name]),
        epsg=int(mosaic.GEOMETRY[name][0].split(":")[1]),
    )
    for name in ("A", "B")
}
ITEMS = {SCENE["id"]: SCENE, **{item["id"]: item for item in PASS.values()}}

#: Inside the scene, away from its nodata corner; the box holds values the area does not (M4-32).
AOI = sources.aoi_around(sources.ORIGIN_X + 1000, sources.ORIGIN_Y - 4800, sources.ORIGIN_X + 5000, sources.ORIGIN_Y - 1000)
#: Digits of the AOI's first position, as a log line or an answer would spell them.
AOI_DIGITS = repr(AOI["coordinates"][0][0][0])[:9]


def _order(
    *,
    items: tuple[str, ...] = ("ITEM_A",),
    assets: tuple[str, ...] = ("red", "nir"),
    steps: list[dict] | None = None,
    dtype: str = "float32",
    aoi: dict | None = AOI,
    dataset: str = COG,
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "recipe_version": 1,
        "inputs": [{"name": "input", "dataset": dataset, "groups": [list(items)], "assets": list(assets)}],
        "steps": steps if steps is not None else [{"op": "band_math", "op_version": 1, "params": {"expression": NDVI}}],
        "output": {"kind": "raster", "format": "cog", "dtype": dtype},
    }
    if aoi is not None:
        document["aoi"] = aoi
    return document


class Fetches:
    """The item source: counts what it is asked."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    async def __call__(self, dataset_id: str, item_id: str) -> dict[str, Any]:
        self.asked.append(item_id)
        if item_id not in ITEMS:
            raise UpstreamError(404)
        return ITEMS[item_id]


class FakeCache:
    def __init__(self, *, fail: bool = False) -> None:
        self.stored: dict[str, tuple[dict[str, Any], float]] = {}
        self.fail = fail

    async def get(self, key: str) -> dict[str, Any] | None:
        if self.fail:
            raise RuntimeError(f"cannot read {key}")
        entry = self.stored.get(key)
        return None if entry is None else entry[0]

    async def set(self, key: str, value: dict[str, Any], *, dataset_id: str, ttl_s: float = 0) -> None:
        if self.fail:
            raise RuntimeError(f"cannot write {key}")
        self.stored[key] = (value, ttl_s)


@pytest.fixture(scope="module")
def files(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("area-bands")
    built = {
        "red": sources.build_band_cog(root / "red.tif", sources.ramp(WIDTH, HEIGHT, 1200)),
        "nir": sources.build_band_cog(root / "nir.tif", sources.ramp(WIDTH, HEIGHT, 3400)),
        "scl": sources.build_band_cog(
            root / "scl.tif", scl_layer(WIDTH // 2, HEIGHT // 2), scale=None, offset=None, resolution=20.0
        ),
    }
    for name in ("A", "B"):
        built[f"{name}_red"] = mosaic._cog(root / f"{name}.tif", name)
    return built


@pytest.fixture
def fetches() -> Fetches:
    return Fetches()


@pytest.fixture
def client(files: dict[str, Path], fetches: Fetches, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    sources.serve({sources.url(name): path for name, path in files.items()}, monkeypatch)

    @asynccontextmanager
    async def lifespan(app):
        app.state.earthx_item_source = fetches
        yield

    with TestClient(build_app(REGISTRY, lifespan=lifespan)) as test_client:
        yield test_client


@pytest.fixture
def cache(client: TestClient) -> FakeCache:
    fake = FakeCache()

    def provide() -> FakeCache:
        return fake

    client.app.dependency_overrides[area_statistics_cache] = provide
    return fake


def _post(client: TestClient, document: Any, *, route: str = ROUTE, **headers: str):
    body = document if isinstance(document, bytes) else json.dumps(document).encode()
    return client.post(route, content=body, headers={"content-type": "application/json", **headers})


def _job_statistics(document: dict[str, Any], workdir: Path) -> list[dict[str, Any]]:
    """What the result of the same order carries: the core run on the recipe the intake makes of it."""
    recipe = asyncio.run(
        estimate_order(json.dumps(document), registry=REGISTRY, operators=OPERATORS, item_source=Fetches())
    ).recipe
    workdir.mkdir(exist_ok=True)
    result = run(recipe, workdir=workdir, progress=lambda done, total: None)
    return [band["statistics"] for band in result.properties["bands"]]


EXTRA = {f"percentile_{percent}" for percent in MEASURE_PERCENTILES}


def _statistics(response) -> list[dict[str, Any]]:
    """The statistics of the answer as the result carries them: without the percentiles a measure adds (NM4-11)."""
    assert response.status_code == 200, response.text
    return [
        {name: value for name, value in band["statistics"].items() if name not in EXTRA}
        for band in response.json()["bands"]
    ]


class TestTheJobsNumbers:
    def test_an_index_over_the_area(self, client: TestClient, tmp_path: Path) -> None:
        response = _post(client, _order())
        assert _statistics(response) == _job_statistics(_order(), tmp_path / "work")
        assert response.json()["exact"] is True and response.json()["factor"] == 1
        assert response.headers["cache-control"] == "no-store"

    def test_a_masked_index(self, client: TestClient, tmp_path: Path) -> None:
        steps = [{"op": "mask", "op_version": 1, "params": MASK}, {"op": "band_math", "op_version": 1, "params": {"expression": NDVI}}]
        document = _order(assets=("red", "nir", "scl"), steps=steps)
        assert _statistics(_post(client, document)) == _job_statistics(document, tmp_path / "work")

    @pytest.mark.parametrize("dtype", ["uint16", "int16"])
    def test_the_output_type_of_the_order(self, client: TestClient, tmp_path: Path, dtype: str) -> None:
        """Reflectance below 0.5 rounded to whole numbers: every value falls onto nodata 0, and the job counts none."""
        steps = [{"op": "mask", "op_version": 1, "params": MASK}]
        document = _order(assets=("red", "scl"), steps=steps, dtype=dtype)
        measured = _statistics(_post(client, document))
        assert measured == _job_statistics(document, tmp_path / "work")
        assert measured[0] == {"count": 0, "valid_percent": 0.0}

    def test_the_mosaic_of_an_overpass(self, client: TestClient, tmp_path: Path) -> None:
        aoi = mapping(box(*_footprint(*mosaic.GEOMETRY["A"])).union(box(*_footprint(*mosaic.GEOMETRY["B"]))).envelope)
        steps = [{"op": "band_math", "op_version": 1, "params": {"expression": "red * 2"}}]
        document = _order(items=("PASS_B", "PASS_A"), assets=("red",), steps=steps, aoi=aoi)
        assert _statistics(_post(client, document)) == _job_statistics(document, tmp_path / "work")


class TestThePercentilesOfNormalize:
    def test_a_measure_carries_the_percentiles_the_methods_need(self, client: TestClient, tmp_path: Path) -> None:
        response = _post(client, _order())
        assert response.status_code == 200, response.text
        measured = response.json()["bands"][0]["statistics"]
        assert EXTRA <= measured.keys()
        # In order, and between the ends of the band.
        ladder = [measured[name] for name in ("minimum", "percentile_1", "percentile_2", "percentile_5", "percentile_25",
                                              "percentile_50", "percentile_75", "percentile_95", "percentile_98",
                                              "percentile_99", "maximum")]
        assert ladder == sorted(ladder)

    def test_the_result_of_a_job_carries_the_two_it_always_did(self, client: TestClient, tmp_path: Path) -> None:
        job = _job_statistics(_order(), tmp_path / "work")[0]
        assert {name for name in job if name.startswith("percentile_")} == {"percentile_2", "percentile_98"}

    def test_an_answer_stored_before_the_percentiles_is_not_served(self) -> None:
        """The key carries the version of the answer's form, so a cache of the older form is measured anew."""
        recipe = asyncio.run(
            estimate_order(json.dumps(_order()), registry=REGISTRY, operators=OPERATORS, item_source=Fetches())
        ).recipe
        assert area_statistics_cache_key(recipe) != hashlib.sha256(
            json.dumps(
                {"kind": "area-statistics/v1", "earthx": earthx.__version__, "recipe": recipe_hash(recipe)},
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).hexdigest()


def _order_v2(steps: list[dict], bands: list[str], *, dtype: str = "float32", aoi: dict | None = AOI) -> dict[str, Any]:
    """An order of recipe version 2: it names the bands of the output, no assets (NM4-43c)."""
    return {
        "recipe_version": 2,
        "inputs": [{"name": "input", "dataset": COG, "groups": [["ITEM_A"]]}],
        "aoi": aoi,
        "steps": steps,
        "output": {"kind": "raster", "format": "cog", "dtype": dtype, "bands": bands},
    }


def _job_result(document: dict[str, Any], workdir: Path):
    recipe = asyncio.run(
        estimate_order(json.dumps(document), registry=REGISTRY, operators=OPERATORS, item_source=Fetches())
    ).recipe
    workdir.mkdir(exist_ok=True)
    return run(recipe, workdir=workdir, progress=lambda done, total: None)


def _normalize(params: dict[str, Any]) -> dict[str, Any]:
    return {"op": "normalize", "op_version": 3, "params": params}


class TestTheFlowOfTheMethodsOfNormalize:
    """What the panel does for a statistical method: measure the start of the chain, put the numbers in the step, run.

    The numbers of the route are the ones the step is given; the job's result then does what the method says over the
    same area (NM4-11).
    """

    def _measured(self, client: TestClient, steps: list[dict], band: str = "red") -> dict[str, Any]:
        response = _post(client, _order_v2(steps, [band], dtype="float64"))
        assert response.status_code == 200, response.text
        assert response.json()["exact"] is True
        return response.json()["bands"][0]["statistics"]

    def test_a_percentile_stretch_puts_the_ends_of_the_measured_range_on_the_ends_of_the_target(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        measured = self._measured(client, [])
        step = _normalize(
            {
                "method": "percentile", "bands": ["red"], "low": 2, "high": 98, "out_min": 0.0, "out_max": 1.0,
                "clip": True,
                "measured": {
                    "factor": 1,
                    "bands": {"red": {"p_low": measured["percentile_2"], "p_high": measured["percentile_98"]}},
                },
            }
        )
        result = _job_result(_order_v2([step], ["red"]), tmp_path / "work")
        got = result.properties["bands"][0]["statistics"]
        assert got["minimum"] == 0.0 and got["maximum"] == 1.0
        # The ends are bin edges of the fixed histogram: within a bin's width (0.4 % of the range here) of 0 and 1.
        assert got["percentile_2"] == pytest.approx(0.0, abs=0.01) and got["percentile_98"] == pytest.approx(1.0, abs=0.01)
        with rasterio.open(result.path) as dataset:
            data = dataset.read(1, masked=True).compressed()
        assert (data == 0.0).mean() == pytest.approx(0.02, abs=0.01) and (data == 1.0).mean() == pytest.approx(0.02, abs=0.01)

    def test_a_z_score_is_centred_and_has_unit_deviation_over_the_area(self, client: TestClient, tmp_path: Path) -> None:
        measured = self._measured(client, [])
        step = _normalize(
            {
                "method": "zscore", "bands": ["red"],
                "measured": {"factor": 1, "bands": {"red": {"mean": measured["mean"], "stddev": measured["stddev"]}}},
            }
        )
        got = _job_result(_order_v2([step], ["red"]), tmp_path / "work").properties["bands"][0]["statistics"]
        assert got["mean"] == pytest.approx(0.0, abs=1e-4) and got["stddev"] == pytest.approx(1.0, abs=1e-4)

    def test_a_robust_scaling_has_median_zero_and_a_quartile_range_of_one(self, client: TestClient, tmp_path: Path) -> None:
        measured = self._measured(client, [])
        step = _normalize(
            {
                "method": "robust", "bands": ["red"],
                "measured": {
                    "factor": 1,
                    "bands": {
                        "red": {
                            "p25": measured["percentile_25"], "median": measured["percentile_50"],
                            "p75": measured["percentile_75"],
                        }
                    },
                },
            }
        )
        result = _job_result(_order_v2([step], ["red"]), tmp_path / "work")
        with rasterio.open(result.path) as dataset:
            data = dataset.read(1, masked=True).compressed()
        assert float(numpy.median(data)) == pytest.approx(0.0, abs=0.02)
        assert float(numpy.percentile(data, 75) - numpy.percentile(data, 25)) == pytest.approx(1.0, abs=0.05)

    def test_the_route_measures_the_start_of_a_chain_with_a_step_of_version_3(self, client: TestClient) -> None:
        first = _normalize(
            {"method": "linear", "bands": ["red"], "in_min": 0.0, "in_max": 0.5, "out_min": 0.0, "out_max": 1.0, "clip": True}
        )
        measured = self._measured(client, [first])
        assert 0.0 <= measured["minimum"] <= measured["percentile_50"] <= measured["maximum"] <= 1.0

    @pytest.mark.parametrize(
        "params",
        [
            {"method": "zscore", "bands": ["red"]},
            {"method": "zscore", "bands": ["red"], "measured": {"factor": 1, "bands": {"red": {"mean": 0.1, "stddev": -1}}}},
            {"method": "median", "bands": ["red"]},
        ],
        ids=["no numbers", "negative deviation", "unknown method"],
    )
    def test_a_step_that_does_not_validate_is_refused_before_any_read(
        self, client: TestClient, fetches: Fetches, params: dict
    ) -> None:
        response = _post(client, _order_v2([_normalize(params)], ["red"]))
        assert response.status_code in (400, 422), response.text
        assert AOI_DIGITS not in response.text

    def test_a_band_the_chain_does_not_have_is_a_422(self, client: TestClient) -> None:
        params = {"method": "linear", "bands": ["red", "swir"], "in_min": 0.0, "in_max": 1.0, "out_min": 0.0,
                  "out_max": 1.0, "clip": True}
        response = _post(client, _order_v2([_normalize(params)], ["red"]))
        assert response.status_code == 422 and "swir" in response.json()["detail"]


class TestAboveTheLimit:
    def test_a_larger_area_is_read_coarser_and_says_so(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("earthx.processing.core.MAX_AREA_PIXELS", 10_000)
        answer = _post(client, _order()).json()
        assert answer["exact"] is False and answer["factor"] > 1
        assert answer["bands"][0]["statistics"]["count"] > 0


class TestReadFailures:
    def test_a_read_failure_is_tried_once_more(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        from earthx.processing import core

        real, calls = core.area_statistics, []

        def flaky(*args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise RasterioIOError(f"HTTP response code on {sources.url('red')}")
            return real(*args, **kwargs)

        monkeypatch.setattr(core, "area_statistics", flaky)
        assert _post(client, _order()).status_code == 200
        assert len(calls) == 2

    @pytest.mark.parametrize(
        ("error", "status"), [(RasterioIOError, 502), (WarpOperationError, 500)]
    )
    def test_a_failure_names_no_address_in_the_log(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, error: type, status: int
    ) -> None:
        def failing(*args, **kwargs):
            raise error(f"HTTP response code on {sources.url('red')}")

        monkeypatch.setattr("earthx.processing.core.area_statistics", failing)
        with caplog.at_level(logging.DEBUG):
            response = _post(client, _order())
        assert response.status_code == status
        text = " ".join(JsonFormatter().format(record) for record in caplog.records)
        assert sources.HOST not in text and sources.HOST not in response.text


class TestBeforeAnyItemIsFetched:
    @pytest.mark.parametrize(
        ("document", "status", "words"),
        [
            (_order(aoi=None), 422, "with an AOI only"),
            (_order(dataset="another"), 422, "another dataset"),
            ([1, 2], 422, "JSON object"),
            (b"{not json", 400, "not JSON"),
            (_order(aoi={"type": "Point", "coordinates": [9.0, 47.0]}), 422, ""),
            (_order(aoi={"type": "Polygon", "coordinates": [[[9.0, 47.0], [9.1, 47.0], [9.1, 47.1]]]}), 422, ""),
            (_order(aoi={"type": "Polygon", "coordinates": [[[9, 47], [9.1, 47.1], [9.1, 47], [9, 47.1], [9, 47]]]}), 422, ""),
            (_order(steps=[{"op": "reproject", "op_version": 1, "params": {"crs": "EPSG:4326"}}]), 422, ""),
        ],
    )
    def test_a_malformed_order(self, client: TestClient, fetches: Fetches, document: Any, status: int, words: str) -> None:
        response = _post(client, document)
        assert response.status_code == status, response.text
        assert words in response.json()["detail"]
        assert fetches.asked == []

    def test_too_many_positions(self, client: TestClient, fetches: Fetches) -> None:
        ring = [[9.0 + i * 1e-6, 47.0] for i in range(20_000)] + [[9.0, 47.1], [9.0, 47.0]]
        response = _post(client, _order(aoi={"type": "Polygon", "coordinates": [ring]}))
        assert response.status_code == 413 and "20000 positions" in response.json()["detail"]
        assert fetches.asked == []

    def test_a_body_over_the_cap(self, client: TestClient, fetches: Fetches) -> None:
        response = _post(client, b" " * (MAX_AREA_BODY_BYTES + 1))
        assert response.status_code == 413
        assert fetches.asked == []

    def test_a_body_without_a_length_is_cut_off_while_it_is_read(self, client: TestClient, fetches: Fetches) -> None:
        def chunks() -> Iterator[bytes]:
            for _ in range(MAX_AREA_BODY_BYTES // 65536 + 2):
                yield b" " * 65536

        response = client.post(ROUTE, content=chunks(), headers={"content-type": "application/json"})
        assert response.status_code == 413
        assert fetches.asked == []

    @pytest.mark.parametrize("depth", [600, 5000, 200_000])
    def test_an_order_nested_too_deeply(self, client: TestClient, fetches: Fetches, depth: int) -> None:
        nested = "[" * depth + "]" * depth
        body = json.dumps(_order()).replace('"coordinates": [[', f'"coordinates": [{nested}, [', 1)
        response = _post(client, body.encode())
        assert response.status_code in (400, 422), response.text
        assert fetches.asked == []

    def test_the_positions_of_a_multipolygon_count_together(self) -> None:
        ring = [[9.0, 47.0]] * 10_000
        assert area_module._positions([[ring], [ring]]) == 20_000
        assert area_module._positions([[ring], [ring + [[9.0, 47.0]]]]) == 20_001
        assert area_module._positions("not an array") == 0

    def test_exactly_the_limit_of_positions_goes_on_to_the_intake(self, client: TestClient, fetches: Fetches) -> None:
        ring = [[9.0 + i * 1e-6, 47.0] for i in range(19_998)] + [[9.0, 47.1], [9.0, 47.0]]
        response = _post(client, _order(aoi={"type": "Polygon", "coordinates": [ring]}))
        assert response.status_code != 413

    def test_the_cap_is_the_job_routes(self) -> None:
        assert MAX_AREA_BODY_BYTES == MAX_BODY_BYTES

    def test_only_json(self, client: TestClient, fetches: Fetches) -> None:
        response = client.post(ROUTE, content=json.dumps(_order()), headers={"content-type": "text/plain"})
        assert response.status_code == 415 and fetches.asked == []

    def test_an_empty_body(self, client: TestClient) -> None:
        assert _post(client, b"").status_code == 400

    def test_a_get_is_no_measure_of_an_area(self, client: TestClient) -> None:
        assert client.get(ROUTE).status_code == 405


class TestAfterTheItems:
    def test_a_licence_below_processing(self, client: TestClient) -> None:
        route = f"/collections/{DISPLAY_ONLY.dataset_id}/statistics"
        response = _post(client, _order(dataset=DISPLAY_ONLY.dataset_id), route=route)
        assert response.status_code == 403

    def test_an_unknown_item(self, client: TestClient) -> None:
        assert _post(client, _order(items=("NOWHERE",))).status_code == 422

    def test_an_area_outside_the_scene(self, client: TestClient) -> None:
        far = sources.aoi_around(sources.ORIGIN_X + 50_000, sources.ORIGIN_Y - 60_000, sources.ORIGIN_X + 51_000, sources.ORIGIN_Y - 59_000)
        assert _post(client, _order(aoi=far)).status_code == 422

    def test_too_many_files(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(area_module, "MAX_AREA_FILES", 2)
        opened: list[Any] = []
        monkeypatch.setattr("earthx.processing.core._open_sources", lambda *args: opened.append(args))
        steps = [{"op": "mask", "op_version": 1, "params": MASK}, {"op": "band_math", "op_version": 1, "params": {"expression": NDVI}}]
        response = _post(client, _order(assets=("red", "nir", "scl"), steps=steps))
        assert response.status_code == 413 and "at most 2 files" in response.json()["detail"]
        assert opened == []

    def test_the_limit_of_files(self) -> None:
        assert MAX_AREA_FILES == 16


class TestTheCache:
    def test_a_second_measure_reads_nothing(self, client: TestClient, cache: FakeCache, monkeypatch: pytest.MonkeyPatch) -> None:
        first = _post(client, _order())
        monkeypatch.setattr("earthx.processing.core._open_sources", lambda *args: pytest.fail("read again"))
        assert _post(client, _order()).json() == first.json()

    def test_an_entry_lives_as_long_as_a_recipe(self, client: TestClient, cache: FakeCache) -> None:
        _post(client, _order())
        ((_, ttl),) = cache.stored.values()
        assert ttl == AREA_STATISTICS_TTL_S == 7 * 24 * 3600

    def test_another_area_is_another_key(self, client: TestClient, cache: FakeCache) -> None:
        other = sources.aoi_around(sources.ORIGIN_X + 1000, sources.ORIGIN_Y - 4000, sources.ORIGIN_X + 4000, sources.ORIGIN_Y - 1000)
        _post(client, _order())
        _post(client, _order(aoi=other))
        assert len(cache.stored) == 2

    def test_the_key_holds_no_number_of_the_area(self, client: TestClient, cache: FakeCache) -> None:
        _post(client, _order())
        (key,) = cache.stored
        assert len(key) == 64 and AOI_DIGITS not in key

    def test_the_key_is_the_recipes(self, client: TestClient, cache: FakeCache) -> None:
        _post(client, _order())
        recipe = asyncio.run(
            estimate_order(json.dumps(_order()), registry=REGISTRY, operators=OPERATORS, item_source=Fetches())
        ).recipe
        assert list(cache.stored) == [area_statistics_cache_key(recipe)]

    def test_a_cache_that_fails_still_answers(self, client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
        failing = FakeCache(fail=True)

        def provide() -> FakeCache:
            return failing

        client.app.dependency_overrides[area_statistics_cache] = provide
        with caplog.at_level(logging.WARNING, logger="earthx.api.area_statistics"):
            response = _post(client, _order())
        assert response.status_code == 200
        text = " ".join(JsonFormatter().format(record) for record in caplog.records)
        assert "RuntimeError" in text and "cannot" not in text


class TestNothingOfTheAreaLeaves:
    @pytest.fixture
    def lines(self) -> Iterator[list[str]]:
        captured: list[str] = []
        formatter = JsonFormatter()

        class Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                captured.append(formatter.format(record))

        handler = Capture(level=logging.DEBUG)
        root = logging.getLogger()
        previous = root.level
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)
        try:
            yield captured
        finally:
            root.removeHandler(handler)
            root.setLevel(previous)

    def test_no_line_names_the_area_or_the_key(self, client: TestClient, cache: FakeCache, lines: list[str]) -> None:
        """Item ids are no secret of this route: a refusal of the intake names one, as it does for a job (§17.2)."""
        assert _post(client, _order()).status_code == 200
        assert _post(client, _order(items=("NOWHERE",))).status_code == 422
        (key,) = cache.stored
        assert lines
        for line in lines:
            payload = json.loads(line)
            payload.pop("timestamp", None)
            text = json.dumps(payload)
            assert AOI_DIGITS not in text and key not in text
            if payload["message"] == "area statistics measured":
                assert "ITEM_A" not in text

    def test_the_access_log_names_the_route(self, client: TestClient, lines: list[str]) -> None:
        _post(client, _order())
        paths = [json.loads(line).get("path") for line in lines if json.loads(line).get("logger") == "earthx.request"]
        assert paths == [ROUTE]

    def test_the_route_writes_one_line_of_counts(self, client: TestClient, lines: list[str]) -> None:
        _post(client, _order())
        (measured,) = [json.loads(line) for line in lines if json.loads(line)["message"] == "area statistics measured"]
        assert (measured["dataset"], measured["scenes"], measured["assets"], measured["factor"]) == (COG, 1, 2, 1)
        assert not [line for line in lines if "order estimated" in line]

    def test_a_refusal_does_not_repeat_the_area(self, client: TestClient) -> None:
        bad = _order(aoi={"type": "Polygon", "coordinates": [[[9.123456789, 47.0], [9.2, 47.0], [9.2, 47.1]]]})
        response = _post(client, bad)
        assert response.status_code == 422 and "9.123456789" not in response.text

    def test_the_schema_offers_no_free_address(self, client: TestClient) -> None:
        operation = client.get("/openapi.json").json()["paths"][AREA_STATISTICS_ROUTE]["post"]
        names = {parameter["name"] for parameter in operation.get("parameters", [])}
        assert names == {"dataset"}


class TestFreshApps:
    def test_two_apps_give_the_same_answer(self, files: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
        sources.serve({sources.url(name): path for name, path in files.items()}, monkeypatch)
        answers = []
        for _ in range(2):

            @asynccontextmanager
            async def lifespan(app):
                app.state.earthx_item_source = Fetches()
                yield

            with TestClient(build_app(REGISTRY, lifespan=lifespan)) as fresh:
                answers.append(_post(fresh, _order()).json())
        assert answers[0] == answers[1]


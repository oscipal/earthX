"""The statistics of an operator: one measure of a preview for its colour scale (plan M4-19c §3.3; adr/0006 §3.4).

``/statistics`` takes ``op``, ``op_version`` and ``params`` like the tile and answers for what the steps make of the
assets, read as the plain statistics are (at most 1024 pixels on the long side). The numbers are compared with an
independent calculation over the synthetic rasters, not with a second run of the core. The unit of the result rides
along: on each band of the statistics and on the TileJSON of the same steps.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote

import numpy
import pytest
from fastapi.testclient import TestClient

from earthx.access.tiles import statistics_cache_key
from earthx.api.tiler import MAX_OPERATOR_PARAMS_CHARS, build_app, statistics_cache
from earthx.gateway import check_url
from earthx.processing.tile import MAX_PREVIEW_SIDE, OperatorTileReader
from earthx.readers.cog import AssetPath
from tests.earthx.api.test_tiler_chain import ITEM_JSON as CHAIN_ITEM
from tests.earthx.api.test_tiler_chain import cf_store, files  # noqa: F401  (fixtures)
from tests.earthx.api.test_tiler_mask_normalize import COG, DISPLAY_ONLY, ITEM, MASK, REGISTRY, ZARR
from tests.earthx.api.test_tiler_operator import _BAND, HEIGHT, NDVI, WIDTH
from tests.earthx.processing import sources
from tests.earthx.processing.test_mask import scl_layer
from tests.earthx.readers import mini_zarr, mini_zarr_cf

ITEM_JSON = {
    **CHAIN_ITEM,
    "assets": {
        **CHAIN_ITEM["assets"],
        "elsewhere": {"href": "https://elsewhere.example.invalid/red.tif", "raster:bands": [_BAND]},
    },
}
OP = {"op": "band_math", "op_version": "1"}


class FakeCache:
    """A statistics cache that remembers what it is given and counts its questions."""

    def __init__(self) -> None:
        self.stored: dict[str, dict[str, Any]] = {}
        self.gets: list[str] = []

    async def get(self, key: str) -> dict[str, Any] | None:
        self.gets.append(key)
        return self.stored.get(key)

    async def set(self, key: str, value: dict[str, Any], *, dataset_id: str) -> None:
        self.stored[key] = value


@pytest.fixture
def client(files: dict[str, Path], cf_store: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:  # noqa: F811
    sources.serve({sources.url(name): path for name, path in files.items()}, monkeypatch, zarr_root=cf_store)
    for module in ("earthx.readers.cog", "earthx.readers.zarr_reader"):
        monkeypatch.setattr(
            f"{module}.check_url", lambda url, policy, **_: check_url(url, policy, resolve=mini_zarr.from_memory)
        )

    async def item_source(dataset_id: str, item_id: str) -> dict[str, Any]:
        return ITEM_JSON

    @asynccontextmanager
    async def lifespan(app):
        app.state.earthx_item_source = item_source
        yield

    app = build_app(REGISTRY, lifespan=lifespan)
    app.state.earthx_resolver = mini_zarr.from_memory
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def cache(client: TestClient) -> FakeCache:
    fake = FakeCache()

    async def provide() -> Iterator[FakeCache]:
        yield fake

    client.app.dependency_overrides[statistics_cache] = provide
    return fake


def _path(
    *,
    dataset: str = COG,
    assets: tuple[str, ...] = ("red", "nir"),
    expression: str = NDVI,
    route: str = "statistics",
    extra: str = "",
    **overrides: str | None,
) -> str:
    query = {**OP, "params": json.dumps({"expression": expression}), **overrides}
    parts = [f"asset={quote(a)}" for a in assets] + [f"{k}={quote(v)}" for k, v in query.items() if v is not None]
    return f"/collections/{dataset}/items/{ITEM}/{route}?{'&'.join(parts)}{extra}"


def _physical(base: int) -> numpy.ma.MaskedArray:
    """The rasters of ``sources.ramp`` as the core reads them: reflectance, the nodata corner hidden."""
    raw = sources.ramp(WIDTH, HEIGHT, base)
    return numpy.ma.masked_array(raw * sources.SCALE + sources.OFFSET, mask=raw == sources.NODATA)


def _only_band(body: dict[str, Any]) -> dict[str, Any]:
    (entry,) = body.values()
    return entry


class TestAgainstAnIndependentCalculation:
    def test_an_index_over_two_assets(self, client: TestClient) -> None:
        response = client.get(_path())
        assert response.status_code == 200, response.text
        stats = _only_band(response.json())
        red, nir = _physical(1200), _physical(3400)
        index = ((nir - red) / (nir + red)).compressed()
        assert stats["count"] == index.size
        assert stats["min"] == pytest.approx(index.min(), rel=1e-4)
        assert stats["max"] == pytest.approx(index.max(), rel=1e-4)
        assert stats["mean"] == pytest.approx(index.mean(), rel=1e-4)
        assert stats["percentile_2"] == pytest.approx(numpy.percentile(index, 2), rel=1e-3)
        assert stats["percentile_98"] == pytest.approx(numpy.percentile(index, 98), rel=1e-3)

    def test_a_20_m_layer_is_read_onto_the_10_m_grid_of_the_other_asset(self, client: TestClient) -> None:
        response = client.get(_path(assets=("red", "scl"), expression="red + scl"))
        assert response.status_code == 200, response.text
        stats = _only_band(response.json())
        classes = scl_layer(WIDTH // 2, HEIGHT // 2).repeat(2, axis=0).repeat(2, axis=1)
        red = _physical(1200)
        total = red + numpy.ma.masked_array(classes.astype("float64"), mask=classes == 0)
        assert stats["count"] == total.count()
        assert stats["min"] == pytest.approx(total.min(), rel=1e-4)
        assert stats["max"] == pytest.approx(total.max(), rel=1e-4)

    def test_a_chain_is_measured_after_its_last_step(self, client: TestClient) -> None:
        masked = json.dumps(MASK)
        response = client.get(
            f"/collections/{COG}/items/{ITEM}/statistics?asset=red&asset=nir&asset=scl"
            f"&op=mask&op_version=1&params={quote(masked)}"
            f"&op=band_math&op_version=1&params={quote(json.dumps({'expression': NDVI}))}"
        )
        assert response.status_code == 200, response.text
        # The mask hides pixels the unmasked index has; the count is smaller than all valid pixels.
        plain = _only_band(client.get(_path()).json())
        assert 0 < _only_band(response.json())["count"] < plain["count"]

    def test_a_zarr_store_is_measured_on_its_coarsest_level(self, client: TestClient) -> None:
        response = client.get(
            _path(dataset=ZARR, assets=("r10m:b04", "r10m:b08"), expression="(b08 - b04) / (b08 + b04)")
        )
        assert response.status_code == 200, response.text
        stats = _only_band(response.json())
        raw = {name: mini_zarr_cf.raw_band(name) for name in ("b04", "b08")}
        valid = (raw["b04"] != mini_zarr_cf.FILL) & (raw["b08"] != mini_zarr_cf.FILL)
        physical = {name: array * mini_zarr_cf.SCALE + mini_zarr_cf.OFFSET for name, array in raw.items()}
        index = ((physical["b08"] - physical["b04"]) / (physical["b08"] + physical["b04"]))[valid]
        assert stats["count"] == index.size
        assert stats["min"] == pytest.approx(index.min(), rel=1e-4)
        assert stats["max"] == pytest.approx(index.max(), rel=1e-4)


class TestAFlatOrEmptyResult:
    """What a colour scale is most needed for goes through the same route: no histogram bins, no valid pixel."""

    def test_values_that_are_one_number_are_measured(self, client: TestClient) -> None:
        stats = _only_band(client.get(_path(expression="nir - red")).json())
        assert stats["min"] == pytest.approx(stats["max"], abs=1e-6) and stats["count"] > 0

    def test_a_result_with_no_valid_pixel_is_an_answer_with_a_count_of_zero(self, client: TestClient) -> None:
        everything = json.dumps({"source": "scl", "classes": list(range(1, 12))})
        response = client.get(
            f"/collections/{COG}/items/{ITEM}/statistics?asset=red&asset=scl"
            f"&op=mask&op_version=1&params={quote(everything)}"
        )
        assert response.status_code == 200, response.text
        assert _only_band(response.json())["count"] == 0


class TestHowMuchIsRead:
    def test_a_smaller_max_size_reads_fewer_pixels_over_the_same_extent(self, client: TestClient) -> None:
        stats = _only_band(client.get(_path(extra="&max_size=256")).json())
        width, height = 256, round(HEIGHT * 256 / WIDTH)
        assert stats["count"] + stats["masked_pixels"] == width * height
        full = _only_band(client.get(_path()).json())
        assert stats["min"] == pytest.approx(full["min"], abs=0.05) and stats["max"] == pytest.approx(full["max"], abs=0.05)

    def test_more_than_1024_pixels_is_a_400(self, client: TestClient) -> None:
        response = client.get(_path(extra=f"&max_size={MAX_PREVIEW_SIDE + 1}"))
        assert response.status_code == 400
        assert str(MAX_PREVIEW_SIDE) in response.json()["detail"]

    @pytest.mark.parametrize("option", ["bidx=1", "unscale=true", "nodata=0", "height=10&width=10", "resampling=bilinear"])
    def test_an_option_that_would_change_the_values_is_a_400(self, client: TestClient, option: str) -> None:
        response = client.get(_path(extra=f"&{option}"))
        assert response.status_code == 400, response.text


class TestRefusedLikeTheTile:
    def test_params_that_are_not_the_operators_form_are_a_400(self, client: TestClient) -> None:
        response = client.get(_path(params="not json"))
        assert response.status_code == 400 and response.json()["detail"].startswith("params: ")

    def test_params_that_are_too_long_are_a_400(self, client: TestClient) -> None:
        response = client.get(_path(params=json.dumps({"expression": "red" * MAX_OPERATOR_PARAMS_CHARS})))
        assert response.status_code == 400

    @pytest.mark.parametrize("expression", ["log(red)", "red ** 51", "__import__('os')"])
    def test_an_expression_outside_r5_is_a_400(self, client: TestClient, expression: str) -> None:
        assert client.get(_path(expression=expression)).status_code == 400

    def test_an_unknown_band_is_a_422_before_any_pixel(self, client: TestClient) -> None:
        response = client.get(_path(expression="nir - ghost"))
        assert response.status_code == 422 and "ghost" in response.json()["detail"]

    def test_the_three_parameters_go_together(self, client: TestClient) -> None:
        response = client.get(f"/collections/{COG}/items/{ITEM}/statistics?asset=red&op=band_math")
        assert response.status_code == 400

    def test_free_band_math_stays_refused(self, client: TestClient) -> None:
        response = client.get(f"/collections/{COG}/items/{ITEM}/statistics?asset=red&expression=b1*2")
        assert response.status_code == 400

    def test_an_operator_needs_the_processing_licence(self, client: TestClient) -> None:
        response = client.get(_path(dataset=DISPLAY_ONLY.dataset_id))
        assert response.status_code == 422 and "does not allow processing" in response.json()["detail"]

    def test_an_asset_at_a_host_the_dataset_does_not_declare_is_refused_like_a_tile(self, client: TestClient) -> None:
        response = client.get(_path(assets=("elsewhere",), expression="elsewhere"))
        assert response.status_code == 502 and "asset_hosts" in response.json()["detail"]


class TestOneMeasurePerQuestion:
    def test_a_second_ask_is_answered_from_the_cache_without_a_read(
        self, client: TestClient, cache: FakeCache, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        reads: Counter[str] = Counter()
        real = OperatorTileReader.preview

        def counting(self, **options):
            reads["preview"] += 1
            return real(self, **options)

        monkeypatch.setattr(OperatorTileReader, "preview", counting)
        first = client.get(_path())
        second = client.get(_path())
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()
        assert reads["preview"] == 1
        assert len(cache.stored) == 1

    def test_another_expression_or_step_is_another_question(self, client: TestClient, cache: FakeCache) -> None:
        for expression in (NDVI, "nir - red", "red"):
            assert client.get(_path(expression=expression)).status_code == 200
        assert len(cache.stored) == 3

    def test_a_refused_question_stores_nothing(self, client: TestClient, cache: FakeCache) -> None:
        assert client.get(_path(expression="log(red)")).status_code == 400
        assert cache.stored == {}

    def test_the_key_is_a_hash_that_names_neither_address_nor_expression(
        self, client: TestClient, cache: FakeCache
    ) -> None:
        client.get(_path())
        (key,) = cache.stored
        assert len(key) == 64 and all(c in "0123456789abcdef" for c in key)

    def test_a_plain_asset_keeps_its_key(self) -> None:
        path = AssetPath("/vsicurl/x", dataset_id="d", item_id="i", asset="a")
        assert statistics_cache_key(path, {"p": 1}) == statistics_cache_key(path, {"p": 1})
        assert statistics_cache_key(path, {"p": 1}) != statistics_cache_key(path, {"p": 2})


class TestTheUnit:
    def test_a_band_that_is_kept_keeps_its_unit(self, client: TestClient) -> None:
        assert _only_band(client.get(_path(assets=("red",), expression="red")).json())["unit"] == "1"

    def test_a_formula_has_no_unit(self, client: TestClient) -> None:
        assert _only_band(client.get(_path()).json())["unit"] is None

    def test_a_band_without_a_unit_in_the_registry_has_none(self, client: TestClient) -> None:
        assert _only_band(client.get(_path(assets=("scl",), expression="scl")).json())["unit"] is None

    def test_the_tilejson_of_the_same_steps_carries_it(self, client: TestClient) -> None:
        response = client.get(_path(assets=("red",), expression="red", route="WebMercatorQuad/tilejson.json"))
        assert response.status_code == 200, response.text
        assert response.json()["unit"] == "1"

    def test_the_tilejson_of_a_formula_names_no_unit(self, client: TestClient) -> None:
        response = client.get(_path(route="WebMercatorQuad/tilejson.json"))
        assert response.status_code == 200 and "unit" not in response.json()

    def test_a_plain_asset_statistics_gains_no_unit(self, client: TestClient) -> None:
        response = client.get(f"/collections/{COG}/items/{ITEM}/statistics?asset=red")
        assert response.status_code == 200
        assert "unit" not in _only_band(response.json())


class TestStatisticsOptionsThatCannotBeComputed:
    """A `400` with the reason, with and without `op`, and before the item is asked for (they were `500`)."""

    BAD = [
        ("p=150", "percentile from 0 to 100"),
        ("p=-1", "percentile from 0 to 100"),
        ("histogram_range=5,1", "min not above max"),
        ("histogram_bins=0", "number from 1 to 1000"),
        ("histogram_bins=100000", "number from 1 to 1000"),
        ("histogram_bins=5,1", "rises strictly"),
        ("histogram_bins=1,1,2", "rises strictly"),
        ("histogram_bins=1", None),
        ("&".join(f"p={n}" for n in range(21)), "at most 20 percentiles"),
        ("&".join(f"c={n}" for n in range(101)), "at most 100 values"),
    ]

    @staticmethod
    def _plain(option: str) -> str:
        return f"/collections/{COG}/items/{ITEM}/statistics?asset=red&{option}"

    @pytest.mark.parametrize(("option", "reason"), BAD)
    @pytest.mark.parametrize("operator", [False, True], ids=["a plain asset", "an operator"])
    def test_is_a_400_with_the_reason(self, client: TestClient, option: str, reason: str | None, operator: bool) -> None:
        url = _path(extra=f"&{option}") if operator else self._plain(option)
        response = client.get(url)
        if reason is None:  # a single bin is a valid choice
            assert response.status_code == 200
            return
        assert response.status_code == 400, response.text
        assert reason in response.json()["detail"]

    def test_is_refused_before_the_item_is_fetched(self, client: TestClient) -> None:
        asked: list[str] = []
        original = client.app.state.earthx_item_source

        async def counting(dataset_id: str, item_id: str) -> dict[str, Any]:
            asked.append(item_id)
            return await original(dataset_id, item_id)

        client.app.state.earthx_item_source = counting
        assert client.get(self._plain("p=150")).status_code == 400
        assert client.get(_path(extra="&histogram_range=5,1")).status_code == 400
        assert asked == []

    def test_names_every_problem_at_once(self, client: TestClient) -> None:
        detail = client.get(self._plain("p=150&histogram_range=5,1")).json()["detail"]
        assert "percentile" in detail and "histogram_range" in detail

    def test_leaves_the_usual_options_alone(self, client: TestClient) -> None:
        for option in ("p=5&p=95", "histogram_bins=20", "histogram_bins=0,1,2", "histogram_range=-1,1", "p=0&p=100"):
            assert client.get(self._plain(option)).status_code == 200, option

"""The bug Otto found live: a true-colour tile came back grayscale.

Root cause, read out of the code rather than guessed: the registry's
`default_render.assets` named three separate asset keys (`SR_10m:b04`,
`SR_10m:b03`, `SR_10m:b02`), but the tile route resolves exactly *one* asset per
request (`api.tiler.dataset_asset_path`, one `asset` query parameter) and the
frontend only ever takes `render.assets[0]` (`store.ts`) — so a tile request
only ever carried `b04` alone, and rio-tiler renders a single band with no
colormap as grayscale. Nothing composited three channels because nothing asked
it to; `ZarrReader` handed back one band, correctly.

The fix keeps the single-asset-per-request shape (no frontend change, no
titiler `MultiBaseTilerFactory`): a variable name inside a group asset may name
several variables, separated by `zarr_reader.VARIABLE_LIST_SEPARATOR`
(`"SR_10m:b04,b03,b02"`), and `ZarrReader` reads each one through its own
windowed `tile`/`preview`/`feature` call and merges the results — see its
docstring for why `xarray.concat` was tried and rejected (it forces a full,
un-windowed read of every band).

This module is the test that shows it working: three variables with three
distinguishable, known values, checked band by band and in the order asked for.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import numpy
import pytest
from rasterio.warp import transform_bounds
from rio_tiler.constants import WEB_MERCATOR_TMS, WGS84_CRS

from earthx.readers.zarr_reader import UnknownVariable, ZarrReader, zarr_asset
from tests.earthx.readers import mini_zarr_composite
from tests.earthx.readers.mini_zarr_composite import (
    BAND_VALUES,
    BASE_URL,
    GROUP,
    HOST,
    ITEM_CRS,
    POLICY,
    from_memory,
)

DATASET = "synthetic-zarr-composite"
ITEM = "SYNTH_COMPOSITE_20260102T100000"


@pytest.fixture(scope="module")
def store_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return mini_zarr_composite.build_mini_zarr_composite(tmp_path_factory.mktemp("zarr-composite") / "mini.zarr")


@pytest.fixture
def requests(store_root: Path, monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    return mini_zarr_composite.serve_store(store_root, monkeypatch)


def asset(variable: str):
    return zarr_asset(
        f"{BASE_URL}/{GROUP}",
        POLICY,
        dataset_id=DATASET,
        item_id=ITEM,
        asset="SR_10m",
        crs=ITEM_CRS,
        resolve=from_memory,
        variable=variable,
    )


def covering_tile(zoom: int = 15) -> tuple[int, int, int]:
    west, south, east, north = transform_bounds(ITEM_CRS, WGS84_CRS, *mini_zarr_composite.store_bounds())
    tile = WEB_MERCATOR_TMS.tile((west + east) / 2, (south + north) / 2, zoom)
    return tile.z, tile.x, tile.y


class TestACompositeTileCarriesThreeDistinctChannels:
    """The exact regression: one channel (grayscale) before the fix, three
    distinguishable ones — in the order asked for — after it."""

    def test_a_single_variable_tile_still_has_exactly_one_band(self, requests: list[httpx.Request]) -> None:
        """Unchanged behaviour: nothing about the ordinary, one-variable case moves."""
        z, x, y = covering_tile()
        with ZarrReader(asset("b04")) as reader:
            image = reader.tile(x, y, z)
        assert image.count == 1

    def test_three_variables_become_three_channels_in_the_order_named(self, requests: list[httpx.Request]) -> None:
        z, x, y = covering_tile()
        with ZarrReader(asset("b04,b03,b02")) as reader:
            image = reader.tile(x, y, z)
        assert image.count == 3
        centre = image.height // 2, image.width // 2
        for band_index, name in enumerate(("b04", "b03", "b02")):
            assert int(image.data[band_index][centre]) == BAND_VALUES[name]

    def test_preview_also_merges_all_three(self, requests: list[httpx.Request]) -> None:
        with ZarrReader(asset("b02,b04,b03")) as reader:
            image = reader.preview()
        assert image.count == 3
        centre = image.height // 2, image.width // 2
        values = [int(image.data[i][centre]) for i in range(3)]
        assert values == [BAND_VALUES["b02"], BAND_VALUES["b04"], BAND_VALUES["b03"]]

    def test_feature_also_merges_all_three(self, requests: list[httpx.Request]) -> None:
        west, south, east, north = transform_bounds(ITEM_CRS, WGS84_CRS, *mini_zarr_composite.store_bounds())
        polygon = {
            "type": "Polygon",
            "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]],
        }
        with ZarrReader(asset("b04,b03,b02")) as reader:
            image = reader.feature(polygon)
        assert image.count == 3


class TestAWindowedReadStaysWindowed:
    """The reason `xarray.concat` is not used: it forces every band to load in
    full immediately (measured while building this fix), the same trap as
    `to_dataarray`/`to_array` (adr/0007 §12.9). A composite tile must cost a few
    chunks per band, not the whole band three times over."""

    def test_a_composite_tile_costs_far_fewer_requests_than_reading_every_band_whole(
        self, requests: list[httpx.Request]
    ) -> None:
        z, x, y = covering_tile(zoom=16)  # zoomed well past native res: a small window
        with ZarrReader(asset("b04,b03,b02")) as reader:
            reader.tile(x, y, z)
        windowed = len(requests)
        requests.clear()

        with ZarrReader(asset("b04,b03,b02")) as reader:
            numpy.asarray(reader.input)  # the whole first band ...
            for extra in reader._extra_bands:
                numpy.asarray(extra.input)  # ... and the whole of each other one
        whole = len(requests)

        assert windowed < whole


class TestTheRequestCountIsLogged:
    """What a tile actually costs the source — Otto's own question, answerable
    from a log line against the real store rather than counted by hand there."""

    def test_closing_the_reader_logs_the_stores_own_request_count(
        self, requests: list[httpx.Request], caplog: pytest.LogCaptureFixture
    ) -> None:
        z, x, y = covering_tile()
        with caplog.at_level("INFO", logger="earthx.readers.zarr"):
            with ZarrReader(asset("b04,b03,b02")) as reader:
                reader.tile(x, y, z)
        (record,) = [r for r in caplog.records if r.message == "zarr asset closed"]
        assert record.requests == len(requests)
        assert record.dataset == DATASET
        assert record.asset == "SR_10m"
        assert HOST not in caplog.text


class TestTheDefinedErrors:
    def test_an_unknown_variable_inside_a_composite_names_it(self, requests: list[httpx.Request]) -> None:
        with pytest.raises(UnknownVariable, match="b99"):
            ZarrReader(asset("b04,b99,b02"))

"""M5-62, Otto's browser test of 24.11.2026: ESA WorldCover, "Mask by classes" with Tree cover hidden, "Start job".

The way of the job end to end, without the browser: the order as the panel sends it, the item as the WorldCover adapter
builds it, intake, the core, and a tile of the result read as the result route reads it (the file's own colour table,
no ``colormap_name``). The bands of the result are compared with ``tests/fixtures/classes/worldcover_mask_result.json``,
which the frontend reads in turn for the legend of the result layer (``frontend/src/resultLayer.test.ts``).
"""

from __future__ import annotations

import io
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import numpy
import pytest
from rasterio.warp import transform_bounds
from rio_tiler.io import Reader

from earthx.adapters.esa_worldcover_bucket import _item as worldcover_item
from earthx.api.intake import accept_order
from earthx.catalog.registry import DatasetRegistry
from earthx.gateway import Gateway, Policy
from earthx.processing import run
from earthx.processing.operators import REGISTRY
from tests.catalog.entries import ESA_WORLDCOVER_2021
from tests.earthx.processing import sources

pytestmark = pytest.mark.anyio

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "classes" / "worldcover_mask_result.json"
WIDTH, HEIGHT = 256, 256
TREE_COVER = 10
#: The order of the panel: "Mask by classes" on the map, Tree cover ticked; the type of the source, which the panel offers
#: because the item names it (``processingDefaults.ts::chooseDtype``).
STEP = {"op": "mask", "op_version": 2, "params": {"source": "map", "classes": [TREE_COVER]}}

CONFIG = replace(
    ESA_WORLDCOVER_2021,
    source=replace(ESA_WORLDCOVER_2021.source, endpoint=f"https://{sources.HOST}/products", asset_hosts=(sources.HOST,)),
)


def _map() -> numpy.ndarray:
    """Every class of the registry in stripes, and a corner of nodata."""
    rows, cols = numpy.indices((HEIGHT, WIDTH))
    values = numpy.array([row.value for row in CONFIG.class_rows("map") or ()], dtype="uint8")
    data = values[(rows // 8 + cols // 8) % len(values)]
    data[:8, :8] = 0
    return data


@pytest.fixture
def item(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    path = sources.build_band_cog(tmp_path / "map.tif", _map(), scale=None, offset=None)
    sources.serve({sources.url("map"): path}, monkeypatch)
    west, south, east, north = transform_bounds(
        sources.CRS,
        "EPSG:4326",
        sources.ORIGIN_X,
        sources.ORIGIN_Y - HEIGHT * sources.RESOLUTION,
        sources.ORIGIN_X + WIDTH * sources.RESOLUTION,
        sources.ORIGIN_Y,
    )
    return worldcover_item("ESA_WorldCover_10m_2021_v200_TEST", "map.tif", (west, south, east, north), config=CONFIG)


async def _accept(item: dict[str, Any], dtype: str) -> Any:
    order = {
        "recipe_version": 2,
        "inputs": [{"name": "input", "dataset": CONFIG.dataset_id, "groups": [[item["id"]]]}],
        "aoi": sources.whole(WIDTH, HEIGHT),
        "steps": [STEP],
        "output": {"kind": "raster", "format": "cog", "dtype": dtype, "bands": ["map"]},
    }

    async def item_source(dataset: str, item_id: str) -> dict[str, Any]:
        return item

    gateway = Gateway(
        Policy(allowed_hosts=frozenset({sources.HOST})),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, headers={"ETag": '"map-1"'})),
        resolve=lambda host, port: ("93.184.216.34",),
    )
    async with gateway:
        return await accept_order(
            json.dumps(order), registry=DatasetRegistry((CONFIG,)), operators=REGISTRY, item_source=item_source, gateway=gateway
        )


async def test_the_item_names_the_type_and_the_recipe_the_classes(item: dict[str, Any]) -> None:
    accepted = await _accept(item, "uint8")
    (resolved,) = accepted.recipe.inputs[0].resolved
    assert [(band.data_type, band.nodata) for band in resolved.bands] == [("uint8", 0.0)]
    assert [row.value for row in resolved.classes or []] == [row.value for row in CONFIG.class_rows("map") or ()]


async def test_the_result_keeps_its_classes_but_the_hidden_one_and_draws_them_in_their_colours(
    item: dict[str, Any], tmp_path: Path
) -> None:
    accepted = await _accept(item, "uint8")
    result = run(accepted.recipe, workdir=tmp_path, progress=lambda done, total: None, operators=REGISTRY)
    (band,) = result.properties["bands"]
    assert band["data_type"] == "uint8"
    assert band["classification:classes"] == json.loads(FIXTURE.read_text(encoding="utf-8"))["bands"][0]["classification:classes"]
    assert TREE_COVER not in {row["value"] for row in band["classification:classes"]}

    # A tile as the result route draws it: the file's colour table, as TiTiler takes it where no colormap is asked for.
    with Reader(str(result.path)) as reader:
        colormap = reader.colormap
        assert colormap is not None
        image = reader.preview(max_size=64)
    rgba = image.render(img_format="npy", colormap=colormap)
    pixels = numpy.load(io.BytesIO(rgba))
    drawn = {tuple(int(v) for v in pixel[:3]) for pixel in pixels.reshape(pixels.shape[0], -1).T if pixel[3] > 0}
    colours = {tuple(int(row["color_hint"][i : i + 2], 16) for i in (0, 2, 4)) for row in band["classification:classes"]}
    tree = next(row for row in CONFIG.class_rows("map") or () if row.value == TREE_COVER)
    assert drawn and drawn <= colours
    assert tuple(int(tree.colour[i : i + 2], 16) for i in (1, 3, 5)) not in drawn


async def test_a_float_result_keeps_the_classes_without_a_colour_table(item: dict[str, Any], tmp_path: Path) -> None:
    """What an item without a type led the panel to (the cause of the browser test): float32. The classes stay in the
    result, the frontend draws them from there (``resultLayer.ts``); a GeoTIFF of float32 holds no colour table."""
    accepted = await _accept(item, "float32")
    result = run(accepted.recipe, workdir=tmp_path, progress=lambda done, total: None, operators=REGISTRY)
    (band,) = result.properties["bands"]
    assert band["data_type"] == "float32"
    assert TREE_COVER not in {row["value"] for row in band["classification:classes"]}
    with Reader(str(result.path)) as reader:
        assert not reader.colormap

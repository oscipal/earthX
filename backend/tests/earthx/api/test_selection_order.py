"""Crop, export, mosaic job and mosaic tile pick the same scene where scenes overlap (NM4-02).

Two flat synthetic scenes of one overpass overlap by two kilometres: "A" (value 100) and "B" (value
200). The mosaic rule is the first valid pixel, and the order of the scenes is the one function
`access.crop_rules.mosaic_order`: here A first. Before NM4-02 only the mosaic job and the mosaic tile
used it; the crop and the export followed the order of the selection, so that asking for B before A
gave B in the overlap. Each path is asked in both orders and must answer with A.

Everything runs through the real app and the real `readers` over local COGs (`sources.serve`).
"""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import httpx
import numpy
import pytest
import rasterio
from fastapi.testclient import TestClient
from pyproj import Transformer

from earthx.access.crop_rules import mosaic_order
from earthx.api.intake import accept_order
from earthx.gateway import Gateway, Policy
from earthx.processing import run
from earthx.processing.export import export
from earthx.processing.recipe import recipe_hash
from tests.earthx.access.test_mosaic_tiles import SEAM_X, SEAM_Y
from tests.earthx.access.test_mosaic_tiles import _at as value_at
from tests.earthx.api.test_tiler_mosaic import (
    ASSET,
    DATASET,
    REGISTRY,
    ZONE_32,
    ZONE_33,
    Scenes,
    _app,
    _array,
    _query,
    _serve,
    _tile_path,
)
from tests.earthx.processing import sources
from tests.earthx.processing.testops import OPERATORS

pytestmark = pytest.mark.anyio

FIRST, SECOND = 100, 200  # the values of A and B
ASKED = [["A", "B"], ["B", "A"]]
EXPORT = {"kind": "crop", "format": "cog", "resolution_factor": 1, "extent": "bbox(aoi ∩ footprints)", "mask": "file"}


@pytest.fixture
def scenes(tmp_path: Path) -> Scenes:
    """A and B, 5 km wide each, overlapping by 2 km around the seam of the tile."""
    overpass = Scenes(tmp_path)
    overpass.add("A", ZONE_32, SEAM_X - 4000.0, 5000.0, FIRST)
    overpass.add("B", ZONE_32, SEAM_X - 1000.0, 5000.0, SECOND)
    for item in overpass.items.values():
        item["assets"][ASSET]["gsd"] = 10.0  # without it the crop plans for the largest possible output
    return overpass


@pytest.fixture
def client(scenes: Scenes, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[], TestClient]]:
    stack = ExitStack()

    def build() -> TestClient:
        _serve(scenes, monkeypatch)
        return stack.enter_context(TestClient(_app(scenes)))

    with stack:
        yield build


def _aoi(scenes: Scenes, *, around: float | None = None) -> dict[str, Any]:
    """The bounding box of the scenes as a polygon in WGS84, or a square of ``around`` metres either side of the seam."""
    if around is not None:
        to_wgs = Transformer.from_crs(ZONE_32, "EPSG:4326", always_xy=True)
        (west, south), (east, north) = (
            to_wgs.transform(SEAM_X - around, SEAM_Y - around),
            to_wgs.transform(SEAM_X + around, SEAM_Y + around),
        )
        return {
            "type": "Polygon",
            "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]],
        }
    west, south, east, north = (
        min(item["bbox"][0] for item in scenes.items.values()),
        min(item["bbox"][1] for item in scenes.items.values()),
        max(item["bbox"][2] for item in scenes.items.values()),
        max(item["bbox"][3] for item in scenes.items.values()),
    )
    return {
        "type": "Polygon",
        "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]],
    }


def _in_the_overlap(source: Path | bytes) -> float | None:
    """The first band at the middle of the overlap, from a raster file (a path or bytes); ``None`` if masked."""
    if isinstance(source, bytes):
        with rasterio.MemoryFile(source) as memory, memory.open() as dataset:
            return _value_at_the_seam(dataset)
    with rasterio.open(source) as dataset:
        return _value_at_the_seam(dataset)


def _value_at_the_seam(dataset: rasterio.DatasetReader) -> float | None:
    x, y = Transformer.from_crs(ZONE_32, dataset.crs, always_xy=True).transform(SEAM_X, SEAM_Y)
    row, col = dataset.index(x, y)
    value = dataset.read(1, masked=True)[row, col]
    return None if numpy.ma.is_masked(value) else float(value)


def _member(archive: bytes, name: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(archive)) as opened:
        return opened.read(name)


def _order(selection: list[str], **override: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "recipe_version": 1,
        "inputs": [{"name": "scene", "dataset": DATASET, "groups": [selection], "assets": [ASSET]}],
        "steps": [],
        "output": {"kind": "raster", "format": "cog", "dtype": "float32"},
    }
    document.update(override)
    return document


async def _accepted(scenes: Scenes, document: dict[str, Any]):
    async def head(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"ETag": f'"etag-{request.url.path}"'})

    async def no_wait(seconds: float) -> None:
        return None

    async with Gateway(
        Policy(allowed_hosts=frozenset({sources.HOST})),
        transport=httpx.MockTransport(head),
        resolve=lambda host, port: ("93.184.216.34",),
        sleep=no_wait,
    ) as gateway:
        return await accept_order(
            json.dumps(document), registry=REGISTRY, operators=OPERATORS, item_source=scenes.source, gateway=gateway
        )


def test_the_order_the_paths_share_puts_a_before_b() -> None:
    assert mosaic_order({"A": ZONE_32, "B": ZONE_32}) == mosaic_order({"B": ZONE_32, "A": ZONE_32}) == ["A", "B"]


@pytest.mark.parametrize("selection", ASKED)
def test_the_mosaic_tile_shows_a_in_the_overlap(scenes: Scenes, client, selection: list[str]) -> None:
    tile = _array(client().get(_tile_path(), params=_query(selection)))
    assert value_at(tile, SEAM_X) == FIRST


@pytest.mark.parametrize("selection", ASKED)
async def test_the_mosaic_job_reads_a_first(scenes: Scenes, selection: list[str], tmp_path: Path, monkeypatch) -> None:
    _serve(scenes, monkeypatch)
    accepted = await _accepted(scenes, _order(selection))
    assert accepted.recipe.inputs[0].groups == [["A", "B"]]
    result = run(accepted.recipe, workdir=tmp_path, progress=lambda done, total: None, operators=OPERATORS)
    assert _in_the_overlap(result.path) == FIRST


@pytest.mark.parametrize("selection", ASKED)
def test_the_crop_keeps_a_in_the_overlap(scenes: Scenes, client, selection: list[str]) -> None:
    response = client().post(
        f"/collections/{DATASET}/download",
        json={"groups": [selection], "assets": [ASSET], "aoi": _aoi(scenes)},
    )
    assert response.status_code == 200, response.text
    assert _in_the_overlap(_member(response.content, "visual.tif")) == FIRST
    recipe = json.loads(_member(response.content, "recipe.json"))
    assert recipe["inputs"][0]["groups"] == [["A", "B"]]


@pytest.mark.parametrize("selection", ASKED)
async def test_the_export_keeps_a_in_the_overlap(
    scenes: Scenes, selection: list[str], tmp_path: Path, monkeypatch
) -> None:
    _serve(scenes, monkeypatch)
    accepted = await _accepted(scenes, _order(selection, aoi=_aoi(scenes), output=EXPORT))
    assert accepted.recipe.inputs[0].groups == [["A", "B"]]
    result = export(
        accepted.recipe, workdir=tmp_path, progress=lambda done, total: None, attachments=accepted.attachments
    )
    assert _in_the_overlap(_member(result.path.read_bytes(), "visual.tif")) == FIRST


async def test_the_export_of_either_selection_is_the_same_recipe(scenes: Scenes, monkeypatch) -> None:
    _serve(scenes, monkeypatch)
    hashes = {
        recipe_hash((await _accepted(scenes, _order(selection, aoi=_aoi(scenes), output=EXPORT))).recipe)
        for selection in ASKED
    }
    assert len(hashes) == 1


def _crop_groups(response: Any) -> list[list[str]]:
    assert response.status_code == 200, response.text
    return json.loads(_member(response.content, "recipe.json"))["inputs"][0]["groups"]


class TestTheRuleBeyondTheIds:
    """The order is `mosaic_order`, not the order of the ids: the target CRS comes first."""

    @pytest.fixture
    def mixed(self, scenes: Scenes) -> list[str]:
        """"A0" lies in zone 33 and sorts first by id; "B" and "C" lie in zone 32, the CRS most scenes share."""
        x33, y33 = Transformer.from_crs(ZONE_32, ZONE_33, always_xy=True).transform(SEAM_X, SEAM_Y)
        scenes.add("A0", ZONE_33, x33 - 5000.0, 10_000.0, 1, top=y33 + 5000.0)
        scenes.add("C", ZONE_32, SEAM_X - 4000.0, 5000.0, 3)
        scenes.items["C"]["assets"][ASSET]["gsd"] = 10.0
        scenes.items["A0"]["assets"][ASSET]["gsd"] = 10.0
        scenes.items["B"]["properties"]["s2:datatake_id"] = "D1"
        return ["A0", "C", "B"]

    async def test_the_export_reads_the_scenes_of_the_target_crs_first(
        self, scenes: Scenes, mixed: list[str], monkeypatch
    ) -> None:
        _serve(scenes, monkeypatch)
        accepted = await _accepted(scenes, _order(mixed, aoi=_aoi(scenes), output=EXPORT))
        assert accepted.recipe.inputs[0].groups == [["B", "C", "A0"]]

    def test_the_crop_reads_the_scenes_of_the_target_crs_first(
        self, scenes: Scenes, client, mixed: list[str]
    ) -> None:
        response = client().post(
            f"/collections/{DATASET}/download", json={"groups": [mixed], "assets": [ASSET], "aoi": _aoi(scenes)}
        )
        assert _crop_groups(response) == [["B", "C", "A0"]]

    @pytest.mark.parametrize("selection", [["Z", "M"], ["M", "Z"]])
    def test_scenes_that_name_no_crs_are_ordered_by_id(self, scenes: Scenes, client, selection: list[str]) -> None:
        for name, offset in (("Z", -4000.0), ("M", -1000.0)):
            scenes.add(name, ZONE_32, SEAM_X + offset, 5000.0, 7)
            scenes.items[name]["assets"][ASSET]["gsd"] = 10.0
            del scenes.items[name]["properties"]["proj:code"]
        response = client().post(
            f"/collections/{DATASET}/download",
            json={"groups": [selection], "assets": [ASSET], "aoi": _aoi(scenes)},
        )
        assert _crop_groups(response) == [["M", "Z"]]


class TestSeveralGroups:
    @pytest.fixture
    def two_passes(self, scenes: Scenes) -> list[list[str]]:
        """A second overpass, "C" and "D", on the files of A and B; each group is ordered on its own."""
        scenes.alias("C", "A", properties={"s2:datatake_id": "D2"})
        scenes.alias("D", "B", properties={"s2:datatake_id": "D2"})
        for name in "CD":
            scenes.items[name]["assets"][ASSET]["gsd"] = 10.0
        return [["B", "A"], ["D", "C"]]

    def test_the_crop_orders_each_group(self, scenes: Scenes, client, two_passes: list[list[str]]) -> None:
        response = client().post(
            f"/collections/{DATASET}/download",
            json={"groups": two_passes, "assets": [ASSET], "aoi": _aoi(scenes, around=1500.0)},
        )
        assert _crop_groups(response) == [["A", "B"], ["C", "D"]]

    async def test_the_export_orders_each_group(self, scenes: Scenes, two_passes: list[list[str]], monkeypatch) -> None:
        _serve(scenes, monkeypatch)
        document = _order(["B", "A"], aoi=_aoi(scenes), output=EXPORT)
        document["inputs"][0]["groups"] = two_passes
        accepted = await _accepted(scenes, document)
        assert accepted.recipe.inputs[0].groups == [["A", "B"], ["C", "D"]]


class TestRefusalsKeepTheirPlace:
    def _without_the_asset(self, scenes: Scenes) -> None:
        item = scenes.items["B"]
        item["assets"] = {"other": {"href": sources.url("B-other")}}

    def test_a_scene_without_the_asset_is_still_a_404_in_the_crop(self, scenes: Scenes, client) -> None:
        self._without_the_asset(scenes)
        response = client().post(
            f"/collections/{DATASET}/download",
            json={"groups": [["B", "A"]], "assets": [ASSET], "aoi": _aoi(scenes)},
        )
        assert response.status_code == 404

    async def test_a_scene_without_the_asset_still_refuses_the_export(self, scenes: Scenes, monkeypatch) -> None:
        from earthx.api.item_source import OrderRefused

        _serve(scenes, monkeypatch)
        self._without_the_asset(scenes)
        with pytest.raises(OrderRefused) as refused:
            await _accepted(scenes, _order(["B", "A"], aoi=_aoi(scenes), output=EXPORT))
        assert refused.value.status_code == 422 and refused.value.stage == "resolve"

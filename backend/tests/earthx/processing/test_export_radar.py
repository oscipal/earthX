"""The export job of a dataset placed by GCPs writes the synchronous crop's files bit for bit, in radar geometry
(DS-04d, M4-11 F1). Two synthetic slices of one pass (`mini_pass`), read through the real readers."""

from __future__ import annotations

import copy
import io
import json
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import rasterio
from shapely.geometry import mapping as shapely_mapping
from shapely.geometry import shape as shapely_shape

from earthx.access import download
from earthx.access.band_export import band_meta
from earthx.access.crop_rules import compute_crop_region
from earthx.access.radar import RADAR_GRID_LINE, item_line_times
from earthx.access.tiles import open_asset
from earthx.catalog.registry import AcquisitionYears
from earthx.processing import run
from earthx.processing.errors import AoiOutsideInputs
from earthx.processing.export import Attachments
from earthx.processing.methods import DatasetFacts
from earthx.processing.recipe import recipe_hash
from earthx.readers import Policy
from earthx.readers.cog import asset_path
from tests.earthx.api.test_download_radar import ACROSS, RADAR, area, footprint, item
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import CROP, recipe_of_data
from tests.earthx.processing.testops import OPERATORS
from tests.earthx.readers import mini_pass

YEARS = AcquisitionYears(2026, 2026)
ITEMS = ["slice-0", "slice-1"]
CONFIG = replace(RADAR, source=replace(RADAR.source, asset_hosts=(sources.HOST,)))


@pytest.fixture(scope="module")
def slices(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    directory = tmp_path_factory.mktemp("pass")
    return {name: mini_pass.build_slice(directory / f"{name}.tif", index) for index, name in enumerate(ITEMS)}


@pytest.fixture
def served(slices: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    sources.serve({sources.url(name): path for name, path in slices.items()}, monkeypatch)


def items(gap_lines: int = 0) -> dict[str, dict[str, Any]]:
    return {"slice-0": item(0), "slice-1": item(1, gap_lines=gap_lines)}


def crop_zip(stac: dict[str, dict[str, Any]], aoi: dict[str, Any]) -> zipfile.ZipFile:
    policy = Policy(allowed_hosts=frozenset({sources.HOST}))

    def path(name: str):
        return asset_path(
            sources.url(name), policy, dataset_id=CONFIG.dataset_id, item_id=name, asset="vv",
            georeferencing="gcp_tps", resolve=lambda host, port=443: ("93.184.216.34",),
        )  # fmt: skip

    region = compute_crop_region([stac[name] for name in ITEMS], shapely_shape(aoi))
    built = download.build_download_zip(
        config=CONFIG,
        years=YEARS,
        open_reader=open_asset,
        crops=[download.AssetCrop(asset="vv", paths=tuple(path(name) for name in ITEMS))],
        aoi_geometry=aoi,
        region_geometry=shapely_mapping(region),
        item_ids=ITEMS,
        recipe_json=b"{}",
        citation_bib=b"@misc{x}\n",
        band_metas={"vv": band_meta({}, "vv")},
        line_times={name: item_line_times(stac[name], mini_pass.FIRST_LINE, mini_pass.LAST_LINE) for name in ITEMS},
    )
    return zipfile.ZipFile(io.BytesIO(built))


def recipe(stac: dict[str, dict[str, Any]], aoi: dict[str, Any]) -> Any:
    entries = [
        {
            "asset": {
                "dataset_id": CONFIG.dataset_id, "item_id": name, "asset": "vv", "reader": "cog",
                "href": sources.url(name), "variable": None, "crs": None, "georeferencing": "gcp_tps",
            },
            "version": None,
            "bands": [{"data_type": "uint16", "nodata": 0, "scale": None, "offset": None}],
            "scaling": "none",
            "gsd": 10.0,
        }  # fmt: skip
        for name in ITEMS
    ]
    times = {}
    for name in ITEMS:
        first, last = item_line_times(stac[name], mini_pass.FIRST_LINE, mini_pass.LAST_LINE)
        times[name] = {"first": first.isoformat(), "last": last.isoformat()}
    data = {
        "recipe_version": 1,
        "inputs": [
            {
                "name": "input", "dataset": CONFIG.dataset_id, "groups": [list(ITEMS)], "assets": ["vv"],
                "resolved": entries, "footprints": {name: footprint(index) for index, name in enumerate(ITEMS)},
                "line_times": times,
            }
        ],
        "aoi": aoi,
        "steps": [],
        "output": {**CROP, "layout": {"form": "per_band"}},
        "recipe_id": "R" * 22,
    }  # fmt: skip
    return recipe_of_data(json.loads(json.dumps(copy.deepcopy(data))), OPERATORS)


def attachments(crop: zipfile.ZipFile) -> Attachments:
    notice = download.build_notice_text(
        CONFIG, item_ids=ITEMS, assets=["vv"], years=YEARS, radar_lines=[RADAR_GRID_LINE], group_prefix="exports/"
    )
    files = {name: crop.read(name).decode("utf-8") for name in ("citation.bib", "aoi.geojson")}
    return Attachments(
        files={**files, "ATTRIBUTION.txt": notice},
        attribution=("Contains modified synthetic data",),
        dataset=DatasetFacts(CONFIG.title, None),
        bands=(band_meta({}, "vv"),),
    )


def export(stac: dict[str, dict[str, Any]], aoi: dict[str, Any], workdir: Path) -> tuple[zipfile.ZipFile, Any]:
    crop = crop_zip(stac, aoi)
    result = run(
        recipe(stac, aoi), workdir=workdir, progress=lambda done, total: None, operators=OPERATORS,
        attachments=attachments(crop),
    )  # fmt: skip
    return crop, result


def scene_lines(text: str) -> list[str]:
    return [line for line in text.split("\n\n") if "Scene " in line or "Not joined" in line]


@pytest.mark.usefixtures("served")
def test_the_export_writes_the_crops_radar_files_bit_for_bit(tmp_path: Path) -> None:
    crop, result = export(items(), ACROSS, tmp_path)
    with zipfile.ZipFile(result.path) as exported:
        rasters = sorted(name for name in crop.namelist() if name.endswith(".tif"))
        assert len(rasters) == 2
        assert sorted(name for name in exported.namelist() if name.endswith(".tif")) == rasters
        for name in rasters:
            assert exported.read(name) == crop.read(name), name
        notice = exported.read("ATTRIBUTION.txt").decode("utf-8")
    assert RADAR_GRID_LINE in notice
    assert scene_lines(notice) == scene_lines(crop.read("ATTRIBUTION.txt").decode("utf-8"))
    with zipfile.ZipFile(result.path) as exported, rasterio.MemoryFile(exported.read(rasters[0])) as memory:
        with memory.open() as dataset:
            assert dataset.crs is None and dataset.gcps[0]


@pytest.mark.usefixtures("served")
def test_a_missing_slice_splits_the_export_as_it_splits_the_crop(tmp_path: Path) -> None:
    crop, result = export(items(gap_lines=mini_pass.HEIGHT), ACROSS, tmp_path)
    with zipfile.ZipFile(result.path) as exported:
        names = sorted(name for name in exported.namelist() if name.endswith(".tif"))
        assert names == sorted(name for name in crop.namelist() if name.endswith(".tif"))
        assert any("group-02/" in name for name in names)
        notice = exported.read("ATTRIBUTION.txt").decode("utf-8")
    assert "Not joined into one file: a slice of the pass is missing." in notice
    # The lines of the groups name the folders of the ZIP, not the one group of the recipe (Otto, A15).
    assert "Items: " not in notice
    assert group_lines(notice) == [
        "Group 1 (exports/group-01/): slice-0",
        "Group 2 (exports/group-02/): slice-1",
    ]
    assert group_lines(notice) == group_lines(crop.read("ATTRIBUTION.txt").decode("utf-8"))


@pytest.mark.usefixtures("served")
def test_a_pass_that_joins_keeps_the_one_line_of_its_items(tmp_path: Path) -> None:
    _, result = export(items(), ACROSS, tmp_path)
    with zipfile.ZipFile(result.path) as exported:
        notice = exported.read("ATTRIBUTION.txt").decode("utf-8")
    assert group_lines(notice) == ["Items: slice-0, slice-1"]


def group_lines(text: str) -> list[str]:
    return [line for line in text.split("\n\n") if line.startswith(("Items: ", "Group 1 (", "Group 2 ("))]


@pytest.mark.usefixtures("served")
def test_an_aoi_beside_the_pass_fails_the_export(tmp_path: Path) -> None:
    aoi = area(400, 400, 420, 420)
    with pytest.raises(AoiOutsideInputs):
        run(
            recipe(items(), aoi), workdir=tmp_path, progress=lambda done, total: None, operators=OPERATORS,
            attachments=attachments(crop_zip(items(), ACROSS)),
        )  # fmt: skip


def test_the_line_times_are_part_of_the_recipe_and_its_hash() -> None:
    with_times = recipe(items(), ACROSS)
    data = with_times.model_dump(mode="json")
    assert set(data["inputs"][0]["line_times"]) == set(ITEMS)
    without = copy.deepcopy(data)
    del without["inputs"][0]["line_times"]
    assert recipe_hash(with_times) != recipe_hash(recipe_of_data(without, OPERATORS))


@pytest.mark.parametrize(
    "change",
    [
        lambda times: times.pop("slice-1"),
        lambda times: times.update({"slice-0": {"first": "2026-10-26T05:34:35Z", "last": "2026-10-26T05:34:34Z"}}),
        lambda times: times.update({"slice-0": {"first": "2026-10-26T05:34:34", "last": "2026-10-26T05:34:35"}}),
    ],
    ids=["an item without an entry", "the last line before the first", "no time zone"],
)
def test_line_times_the_recipe_cannot_use_are_refused(change: Any) -> None:
    data = recipe(items(), ACROSS).model_dump(mode="json")
    change(data["inputs"][0]["line_times"])
    with pytest.raises(ValueError):
        recipe_of_data(data, OPERATORS)

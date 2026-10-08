"""The export job against the synchronous crop: the same files, bit for bit (M4-11 F1).

The crop builds its ZIP with ``access.download.build_download_zip``, the core writes
``export.zip`` block by block; both read the same synthetic COGs through the real
`readers` (``sources.serve``). Three cases, as Otto asked: one item, a mosaic of two
items (the first with a nodata gap the second fills), and two groups in one ZIP — one
group per file pair, also when the AOI reaches past one group's footprint.
"""

from __future__ import annotations

import copy
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import numpy
import pytest
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform_geom
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles
from shapely.geometry import mapping as shapely_mapping
from shapely.geometry import shape as shapely_shape

from earthx.access import download
from earthx.access.crop_rules import compute_crop_region
from earthx.access.tiles import open_asset
from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.processing import RunCancelled, run
from earthx.processing.errors import AoiOutsideInputs, UnsupportedRecipe
from earthx.processing.export import EXPORT_NAME, Attachments, AttachmentsInvalid, read_attachments
from earthx.processing.recipe import recipe_from_data
from earthx.readers import Policy
from earthx.readers.cog import asset_path
from tests.conftest import own_log_text
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import CROP
from tests.earthx.processing.testops import OPERATORS

WIDTH, HEIGHT = 700, 600
DATASET = "synthetic"


def _visual(path: Path, data: numpy.ndarray, *, origin_x: float = sources.ORIGIN_X) -> Path:
    """Three ``uint8`` bands, nodata 0, 256 px blocks: a small Sentinel-2 ``visual``."""
    count, height, width = data.shape
    plain = path.with_suffix(".plain.tif")
    profile = {
        "driver": "GTiff", "dtype": "uint8", "count": count, "height": height, "width": width,
        "crs": sources.CRS, "transform": from_origin(origin_x, sources.ORIGIN_Y, 10.0, 10.0), "nodata": 0,
    }  # fmt: skip
    with rasterio.open(plain, "w", **profile) as dst:
        dst.write(data)
    cog_profile = cog_profiles.get("deflate")
    cog_profile.update({"blockxsize": 256, "blockysize": 256})
    cog_translate(plain, path, cog_profile, overview_resampling="nearest", quiet=True)
    plain.unlink()
    return path


def _bands(base: int) -> numpy.ndarray:
    rows, cols = numpy.indices((HEIGHT, WIDTH))
    data = numpy.stack([((base + k * 40 + 3 * rows + cols) % 250 + 1) for k in range(3)]).astype("uint8")
    return data


def _footprint(origin_x: float, *, width: int = WIDTH, inset: float = 0.0) -> dict[str, Any]:
    ring = [
        [origin_x + inset, sources.ORIGIN_Y - HEIGHT * 10 + inset],
        [origin_x + width * 10 - inset, sources.ORIGIN_Y - HEIGHT * 10 + inset],
        [origin_x + width * 10 - inset, sources.ORIGIN_Y - inset],
        [origin_x + inset, sources.ORIGIN_Y - inset],
        [origin_x + inset, sources.ORIGIN_Y - HEIGHT * 10 + inset],
    ]
    return transform_geom(sources.CRS, "EPSG:4326", {"type": "Polygon", "coordinates": [ring]})


#: Item C lies 4 km east of A and B; its footprint is narrower than its raster.
EAST = sources.ORIGIN_X + 4000.0


@pytest.fixture(scope="module")
def scenes(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("export-scenes")
    gap = _bands(10)
    gap[:, :, :250] = 0  # A misses its left part; B fills it in the mosaic
    gap[1, 300:320, 400:420] = 0  # one band alone at nodata: a per-band gap, not a hole
    return {
        "ITEM_A": _visual(root / "a.tif", gap),
        "ITEM_B": _visual(root / "b.tif", _bands(90)),
        "ITEM_C": _visual(root / "c.tif", _bands(170), origin_x=EAST),
    }


FOOTPRINTS = {
    "ITEM_A": _footprint(sources.ORIGIN_X),
    "ITEM_B": _footprint(sources.ORIGIN_X),
    "ITEM_C": _footprint(EAST, width=500),
}

#: A diamond across A/B and into C: not a rectangle, so the mask is not all ones.
AOI = transform_geom(
    sources.CRS,
    "EPSG:4326",
    {
        "type": "Polygon",
        "coordinates": [
            [
                [sources.ORIGIN_X + 1500, sources.ORIGIN_Y - 3000],
                [sources.ORIGIN_X + 5200, sources.ORIGIN_Y - 5600],
                [sources.ORIGIN_X + 8500, sources.ORIGIN_Y - 3000],
                [sources.ORIGIN_X + 5200, sources.ORIGIN_Y - 400],
                [sources.ORIGIN_X + 1500, sources.ORIGIN_Y - 3000],
            ]
        ],
    },
)


@pytest.fixture
def served(scenes: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    sources.serve({sources.url(item.lower()): path for item, path in scenes.items()}, monkeypatch)


def _crop_zip(groups: list[list[str]], notice_aoi: dict[str, Any]) -> bytes:
    """The synchronous crop's ZIP, as `api.tiler.download_crop` builds it."""
    aoi = shapely_shape(AOI)
    policy = Policy(allowed_hosts=frozenset({sources.HOST}))

    def path(item: str):
        return asset_path(
            sources.url(item.lower()), policy, dataset_id=DATASET, item_id=item, asset="visual",
            resolve=lambda host, port=443: ("93.184.216.34",),
        )  # fmt: skip

    regions = [compute_crop_region([{"geometry": FOOTPRINTS[item]} for item in group], aoi) for group in groups]
    crops = [[download.AssetCrop(asset="visual", paths=tuple(path(item) for item in group))] for group in groups]
    return download.build_download_zip(
        config=SENTINEL_2_L2A,
        open_reader=open_asset,
        crops=crops[0],
        aoi_geometry=notice_aoi,
        region_geometry=shapely_mapping(regions[0]),
        item_ids=groups[0],
        additional_groups=[
            download.GroupCrop(item_ids=group, crops=crop, region_geometry=shapely_mapping(region))
            for group, crop, region in zip(groups[1:], crops[1:], regions[1:], strict=True)
        ],
        recipe_json=b"{}",
        citation_bib=b"@misc{x}\n",
    )


def _recipe(groups: list[list[str]]) -> Any:
    items = [item for group in groups for item in group]
    entries = []
    for item in items:
        entry = {
            "asset": {
                "dataset_id": DATASET, "item_id": item, "asset": "visual", "reader": "cog",
                "href": sources.url(item.lower()), "variable": None, "crs": sources.CRS,
            },
            "version": None,
            "bands": [{"data_type": "uint8", "nodata": 0, "scale": None, "offset": None}] * 3,
            "scaling": "none",
            "gsd": 10.0,
        }  # fmt: skip
        entries.append(entry)
    data = {
        "recipe_version": 1,
        "inputs": [
            {
                "name": "input", "dataset": DATASET, "groups": copy.deepcopy(groups), "assets": ["visual"],
                "resolved": entries, "footprints": {item: FOOTPRINTS[item] for item in items},
            }
        ],
        "aoi": AOI,
        "steps": [],
        "output": dict(CROP),
        "recipe_id": "R" * 22,
    }  # fmt: skip
    return recipe_from_data(json.loads(json.dumps(data)), OPERATORS)


def _attachments(crop: zipfile.ZipFile) -> Attachments:
    return Attachments(
        files={name: crop.read(name).decode("utf-8") for name in ("ATTRIBUTION.txt", "citation.bib", "aoi.geojson")},
        attribution=("Contains modified synthetic data",),
    )


def _export(groups: list[list[str]], workdir: Path, crop: zipfile.ZipFile, progress=lambda done, total: None):
    return run(_recipe(groups), workdir=workdir, progress=progress, operators=OPERATORS, attachments=_attachments(crop))


CASES = {
    "one item": [["ITEM_A"]],
    "mosaic of two items": [["ITEM_A", "ITEM_B"]],
    "two groups": [["ITEM_A", "ITEM_B"], ["ITEM_C"]],
}


@pytest.mark.usefixtures("served")
@pytest.mark.parametrize("groups", list(CASES.values()), ids=list(CASES))
def test_the_export_writes_the_crops_files_bit_for_bit(groups: list[list[str]], tmp_path: Path) -> None:
    crop = zipfile.ZipFile(io.BytesIO(_crop_zip(groups, AOI)))
    result = _export(groups, tmp_path, crop)
    with zipfile.ZipFile(result.path) as exported:
        rasters = [name for name in crop.namelist() if name.endswith(".tif")]
        assert rasters, "the crop wrote no raster"
        assert [name for name in exported.namelist() if name.endswith(".tif")] == rasters
        for name in rasters:
            assert exported.read(name) == crop.read(name), name
            assert exported.getinfo(name).compress_type == zipfile.ZIP_STORED
        for name in ("aoi.geojson", "ATTRIBUTION.txt", "citation.bib"):
            assert exported.read(name) == crop.read(name)
            assert exported.getinfo(name).compress_type == zipfile.ZIP_DEFLATED
        assert sorted(exported.namelist()) == sorted(crop.namelist())


@pytest.mark.usefixtures("served")
def test_two_groups_give_two_folders_with_a_file_pair_each(tmp_path: Path) -> None:
    groups = CASES["two groups"]
    crop = zipfile.ZipFile(io.BytesIO(_crop_zip(groups, AOI)))
    result = _export(groups, tmp_path, crop)
    assert result.members[:4] == (
        "group-01/visual.tif", "group-01/visual_mask.tif", "group-02/visual.tif", "group-02/visual_mask.tif",
    )  # fmt: skip
    assert sorted(path.name for path in tmp_path.iterdir()) == [EXPORT_NAME]


@pytest.mark.usefixtures("served")
def test_the_mosaic_takes_the_second_item_where_the_first_has_no_data(tmp_path: Path) -> None:
    groups = CASES["mosaic of two items"]
    crop = zipfile.ZipFile(io.BytesIO(_crop_zip(groups, AOI)))
    result = _export(groups, tmp_path, crop)
    with zipfile.ZipFile(result.path) as exported:
        (tmp_path / "visual.tif").write_bytes(exported.read("visual.tif"))
    alone = tmp_path / "alone"
    alone.mkdir()
    single = _export([["ITEM_A"]], alone, zipfile.ZipFile(io.BytesIO(_crop_zip([["ITEM_A"]], AOI))))
    with zipfile.ZipFile(single.path) as exported:
        (alone / "visual.tif").write_bytes(exported.read("visual.tif"))
    with rasterio.open(tmp_path / "visual.tif") as mosaic, rasterio.open(alone / "visual.tif") as first:
        assert (mosaic.read(1) == 0).sum() < (first.read(1) == 0).sum()


@pytest.mark.usefixtures("served")
def test_the_recipe_in_the_zip_is_the_jobs_own(tmp_path: Path) -> None:
    groups = CASES["one item"]
    crop = zipfile.ZipFile(io.BytesIO(_crop_zip(groups, AOI)))
    result = _export(groups, tmp_path, crop)
    with zipfile.ZipFile(result.path) as exported:
        document = json.loads(exported.read("recipe.json"))
    assert document["recipe_id"] == "R" * 22
    assert document["provenance"]["kind"] == "job"
    assert document["provenance"]["attribution"] == ["Contains modified synthetic data"]
    assert document["output"]["kind"] == "crop"
    assert set(document["inputs"][0]["footprints"]) == {"ITEM_A"}


def test_an_aoi_over_no_valid_pixel_fails_and_leaves_nothing(
    scenes: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The footprint reaches the AOI, the raster's valid pixels do not: the crop's ``AoiOutsideItems``."""
    sources.serve({sources.url("item_a"): scenes["ITEM_A"]}, monkeypatch)
    crop = zipfile.ZipFile(io.BytesIO(_crop_zip([["ITEM_A"]], AOI)))
    empty = _visual(tmp_path / "empty.tif", numpy.zeros((3, HEIGHT, WIDTH), dtype="uint8"))
    sources.serve({sources.url("item_a"): empty}, monkeypatch)
    workdir = tmp_path / "work"
    workdir.mkdir()
    with pytest.raises(AoiOutsideInputs):
        _export([["ITEM_A"]], workdir, crop)
    assert list(workdir.iterdir()) == []


@pytest.mark.usefixtures("served")
def test_a_cancel_mid_mosaic_removes_every_file(tmp_path: Path) -> None:
    groups = CASES["two groups"]
    crop = zipfile.ZipFile(io.BytesIO(_crop_zip(groups, AOI)))

    def progress(done: int, total: int) -> None:
        if done == 2:
            raise RunCancelled()

    with pytest.raises(RunCancelled):
        _export(groups, tmp_path, crop, progress)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.usefixtures("served")
def test_progress_counts_to_its_total(tmp_path: Path) -> None:
    groups = CASES["two groups"]
    crop = zipfile.ZipFile(io.BytesIO(_crop_zip(groups, AOI)))
    seen: list[tuple[int, int]] = []
    _export(groups, tmp_path, crop, lambda done, total: seen.append((done, total)))
    assert [done for done, _ in seen] == list(range(1, len(seen) + 1))
    assert seen[-1][0] == seen[-1][1]


@pytest.mark.usefixtures("served")
def test_no_aoi_address_or_hash_reaches_the_log(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    groups = CASES["two groups"]
    crop = zipfile.ZipFile(io.BytesIO(_crop_zip(groups, AOI)))
    with caplog.at_level("INFO", logger="earthx.processing"):
        _export(groups, tmp_path, crop)
    assert caplog.records
    text = "\n".join(own_log_text(record) for record in caplog.records)
    assert sources.HOST not in text
    assert f"{AOI['coordinates'][0][0][0]:.4f}"[:7] not in text
    assert "c1:" not in text


FILES = {"ATTRIBUTION.txt": "a\n", "citation.bib": "@misc{a}\n", "aoi.geojson": "{}"}


@pytest.mark.parametrize(
    ("files", "attribution"),
    [
        ({**FILES, "notes.txt": "x"}, ()),
        ({key: value for key, value in FILES.items() if key != "citation.bib"}, ()),
        ({**FILES, "ATTRIBUTION.txt": "x" * (64 * 1024 + 1)}, ()),
        ({**FILES, "citation.bib": "\ud800"}, ()),
        ({**FILES, "aoi.geojson": 7}, ()),
        (FILES, ("x" * 1025,)),
        (FILES, tuple("x" for _ in range(9))),
        (FILES, (7,)),
    ],
)
def test_attachments_are_the_fixed_files_of_bounded_text(files: dict, attribution: tuple) -> None:
    with pytest.raises(AttachmentsInvalid):
        Attachments(files=files, attribution=attribution)


@pytest.mark.parametrize("data", [None, [], {"files": FILES}, {"files": [], "attribution": []}, {"files": FILES, "attribution": "x"}])
def test_attachments_from_json_take_only_their_own_shape(data: Any) -> None:
    with pytest.raises(AttachmentsInvalid):
        Attachments.from_json(data)


def test_attachments_survive_their_json_form() -> None:
    attachments = Attachments(files=FILES, attribution=("a",))
    assert Attachments.from_json(json.loads(json.dumps(attachments.to_json()))) == attachments


def test_missing_or_unreadable_attachments_are_named_not_shown(tmp_path: Path) -> None:
    with pytest.raises(AttachmentsInvalid, match="cannot be read"):
        read_attachments(tmp_path)
    (tmp_path / "attachments.json").write_text("not json {")
    with pytest.raises(AttachmentsInvalid, match="cannot be read"):
        read_attachments(tmp_path)


def test_items_of_one_group_with_other_bands_are_no_mosaic(
    scenes: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    single = tmp_path / "single.tif"
    _visual(single, _bands(10)[:1])
    sources.serve({sources.url("item_a"): scenes["ITEM_A"], sources.url("item_b"): single}, monkeypatch)
    crop = zipfile.ZipFile(io.BytesIO(_crop_zip([["ITEM_A"]], AOI)))
    workdir = tmp_path / "work"
    workdir.mkdir()
    with pytest.raises(UnsupportedRecipe, match="differ in their bands"):
        _export([["ITEM_A", "ITEM_B"]], workdir, crop)
    assert list(workdir.iterdir()) == []

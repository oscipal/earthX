"""NM4-75: the export job with a layout writes the files the synchronous crop writes, bit for bit.

One scene with a 10 m band, a 20 m band and a 20 m classification layer, whole (no area named: the job takes the
scene's footprint). The crop and the job each build their ZIP; the rasters, the masks and ``BANDS.txt`` must agree.
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

from earthx.access import download
from earthx.access.band_export import BandMeta, band_meta
from earthx.access.crop_rules import compute_crop_region
from earthx.access.tiles import open_asset
from earthx.catalog.registry import AcquisitionYears
from earthx.processing import run
from earthx.processing.errors import UnsupportedRecipe
from earthx.processing.export import Attachments, AttachmentsInvalid
from earthx.processing.methods import DatasetFacts
from earthx.processing.plan import describe_resampling, estimate
from earthx.readers import Policy
from earthx.readers.cog import asset_path
from tests.catalog.entries import SENTINEL_2_L2A
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import CROP, recipe_of_data
from tests.earthx.processing.testops import OPERATORS

DATASET = "synthetic"
SIZE = 600  # metres: 60 px at 10 m, 30 at 20 m
# asset -> (resolution in m, dtype, band name, common name, wavelength)
ASSETS = {
    "blue": (10.0, "uint16", "B02", "blue", 0.49),
    "rededge1": (20.0, "uint16", "B05", "rededge1", 0.705),
    "scl": (20.0, "uint8", "SCL", None, None),
}
YEARS = AcquisitionYears(2025, 2025)


def _item() -> dict[str, Any]:
    return {
        "id": "ITEM_A",
        "assets": {
            asset: {
                "gsd": res,
                "eo:bands": [{k: v for k, v in (("name", name), ("common_name", common), ("center_wavelength", wl)) if v}],
                "raster:bands": [{"data_type": dtype, "nodata": 0}],
            }
            for asset, (res, dtype, name, common, wl) in ASSETS.items()
        },
    }


@pytest.fixture(scope="module")
def cogs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("layout-scenes")
    out = {}
    for asset, (res, dtype, *_rest) in ASSETS.items():
        n = int(SIZE / res)
        data = numpy.ones((n, n), dtype=dtype)
        rows, cols = numpy.indices((n, n))
        data = ((5 + 2 * rows + cols) % 200 + 1).astype(dtype) if asset != "scl" else (1 + (rows // 3 + cols // 3) % 4).astype(dtype)
        out[asset] = sources.build_band_cog(root / f"{asset}.tif", data, resolution=res, scale=None, offset=None)
    return out


@pytest.fixture
def served(cogs: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    sources.serve({sources.url(asset): path for asset, path in cogs.items()}, monkeypatch)


FOOTPRINT = sources.whole(60, 60, inset=0.0)
AOI = sources.whole(60, 60)


def _paths() -> dict[str, Any]:
    policy = Policy(allowed_hosts=frozenset({sources.HOST}))
    return {
        asset: asset_path(
            sources.url(asset), policy, dataset_id=DATASET, item_id="ITEM_A", asset=asset,
            resolve=lambda host, port=443: ("93.184.216.34",),
        )  # fmt: skip
        for asset in ASSETS
    }


def _metas() -> dict[str, BandMeta]:
    return {asset: band_meta(_item(), asset, unit="1", categorical=asset == "scl") for asset in ASSETS}


def _crop(assets: list[str], form: str, common: float | None) -> zipfile.ZipFile:
    from shapely.geometry import mapping, shape

    region = compute_crop_region([{"geometry": FOOTPRINT}], shape(AOI))
    paths = _paths()
    data = download.build_download_zip(
        config=SENTINEL_2_L2A, years=YEARS, open_reader=open_asset,
        crops=[download.AssetCrop(asset=a, paths=(paths[a],)) for a in assets],
        aoi_geometry=AOI, region_geometry=mapping(region), item_ids=["ITEM_A"],
        form=form, common_resolution=common, band_metas=_metas(),
        recipe_json=b"{}", citation_bib=b"@misc{x}\n",
    )  # fmt: skip
    return zipfile.ZipFile(io.BytesIO(data))


def _recipe(assets: list[str], layout: dict[str, Any], *, aoi: Any = AOI) -> Any:
    entries = [
        {
            "asset": {
                "dataset_id": DATASET, "item_id": "ITEM_A", "asset": asset, "reader": "cog",
                "href": sources.url(asset), "variable": None, "crs": sources.CRS,
            },
            "version": None,
            "bands": [{"data_type": ASSETS[asset][1], "nodata": 0, "scale": None, "offset": None}],
            "scaling": "none",
            "gsd": ASSETS[asset][0],
        }
        for asset in assets
    ]  # fmt: skip
    data = {
        "recipe_version": 1,
        "inputs": [
            {
                "name": "input", "dataset": DATASET, "groups": [["ITEM_A"]], "assets": assets,
                "resolved": entries, "footprints": {"ITEM_A": FOOTPRINT},
            }
        ],
        "aoi": aoi,
        "steps": [],
        "output": {**CROP, "layout": layout},
        "recipe_id": "R" * 22,
    }  # fmt: skip
    return recipe_of_data(json.loads(json.dumps(data)), OPERATORS)


def _job(assets: list[str], layout: dict[str, Any], crop: zipfile.ZipFile, workdir: Path) -> zipfile.ZipFile:
    metas = _metas()
    attachments = Attachments(
        files={name: crop.read(name).decode() for name in ("ATTRIBUTION.txt", "citation.bib", "aoi.geojson")},
        attribution=("x",),
        dataset=DatasetFacts(SENTINEL_2_L2A.title, None),
        bands=tuple(metas[a] for a in assets),
    )
    result = run(_recipe(assets, layout), workdir=workdir, progress=lambda done, total: None, operators=OPERATORS, attachments=attachments)
    return zipfile.ZipFile(result.path)


CASES = {
    "one file per band": ("per_band", None),
    "one file per resolution": ("per_resolution", None),
    "one multi-band file at 20 m": ("multi_band", 20.0),
    "one multi-band file at 10 m": ("multi_band", 10.0),
}


@pytest.mark.usefixtures("served")
@pytest.mark.parametrize(("form", "common"), list(CASES.values()), ids=list(CASES))
def test_the_job_writes_the_crops_files_bit_for_bit(form: str, common: float | None, tmp_path: Path) -> None:
    assets = list(ASSETS)
    layout = {"form": form, **({"resolution_m": common} if common else {})}
    crop = _crop(assets, form, common)
    with _job(assets, layout, crop, tmp_path) as job:
        rasters = [n for n in crop.namelist() if n.endswith(".tif")]
        assert rasters and sorted(n for n in job.namelist() if n.endswith(".tif")) == sorted(rasters)
        for name in rasters:
            assert job.read(name) == crop.read(name), name
        assert job.read("exports/BANDS.txt") == crop.read("exports/BANDS.txt")
        for name in ("exports/BANDS.txt", "ATTRIBUTION.txt"):
            assert job.read(name) == crop.read(name)


@pytest.mark.usefixtures("served")
def test_a_multi_band_job_carries_descriptions_and_converts_by_the_kind_of_band(tmp_path: Path) -> None:
    assets = list(ASSETS)
    crop = _crop(assets, "multi_band", 20.0)
    with _job(assets, {"form": "multi_band", "resolution_m": 20.0}, crop, tmp_path) as job:
        names = [n for n in job.namelist() if n.endswith(".tif") and "_mask" not in n]
        assert names == ["exports/bands_20m.tif"]
        with rasterio.MemoryFile(job.read(names[0])) as mem, mem.open() as ds:
            assert ds.descriptions == ("B02", "B05", "SCL")
            assert ds.count == 3
        table = job.read("exports/BANDS.txt").decode()
        assert "| 10 | 20 | average |" in table  # the 10 m band is averaged, the 20 m ones are not converted
        assert table.count("| none |") == 2


def test_an_order_for_a_layout_names_its_resolution_exactly_for_one_multi_band_file() -> None:
    for layout in ({"form": "multi_band"}, {"form": "per_band", "resolution_m": 20.0}, {"form": "zip"}):
        with pytest.raises(Exception, match="resolution_m|layout|form"):
            _recipe(list(ASSETS), layout)


def test_a_recipe_without_a_layout_hashes_as_before() -> None:
    plain = recipe_of_data(json.loads(json.dumps({**json.loads(_recipe(["blue"], {"form": "per_band"}).model_dump_json()), "output": dict(CROP)})), OPERATORS)
    assert "layout" not in plain.model_dump(mode="json")["output"]


@pytest.mark.usefixtures("served")
def test_the_job_without_the_bands_of_its_assets_is_refused(tmp_path: Path) -> None:
    crop = _crop(["blue"], "per_band", None)
    attachments = Attachments(
        files={name: crop.read(name).decode() for name in ("ATTRIBUTION.txt", "citation.bib", "aoi.geojson")},
        attribution=("x",),
        dataset=DatasetFacts("x", None),
    )
    with pytest.raises(AttachmentsInvalid):
        run(_recipe(["blue"], {"form": "per_band"}), workdir=tmp_path, progress=lambda d, t: None, operators=OPERATORS, attachments=attachments)


def test_the_estimate_counts_one_stacked_file_and_names_the_converted_bands() -> None:
    per_band = estimate(_recipe(list(ASSETS), {"form": "per_band"}), OPERATORS)
    stacked = estimate(_recipe(list(ASSETS), {"form": "multi_band", "resolution_m": 20.0}), OPERATORS)
    assert stacked.output_pixels < per_band.output_pixels  # three files, one at 10 m, against one at 20 m
    facts = describe_resampling(_recipe(list(ASSETS), {"form": "multi_band", "resolution_m": 20.0}), OPERATORS)
    assert facts is not None and facts.grid.resolution == 20.0
    assert [band.band for band in facts.bands] == ["blue"]
    # Counter-checks: nothing is converted in the other forms, and a crop without a layout says nothing.
    assert describe_resampling(_recipe(list(ASSETS), {"form": "per_resolution"}), OPERATORS) is None
    assert describe_resampling(_recipe(list(ASSETS), {"form": "per_band"}), OPERATORS) is None
    legacy = copy.deepcopy(_recipe(["blue"], {"form": "per_band"}))
    assert describe_resampling(recipe_of_data({**legacy.model_dump(mode="json"), "output": dict(CROP)}, OPERATORS), OPERATORS) is None


@pytest.mark.usefixtures("served")
def test_a_multi_band_layout_over_an_asset_without_a_pixel_size_is_unsupported(tmp_path: Path) -> None:
    crop = _crop(["blue"], "per_band", None)
    metas = _metas()
    nameless = BandMeta(**{**metas["blue"].to_json(), "resolution_m": None})
    attachments = Attachments(
        files={name: crop.read(name).decode() for name in ("ATTRIBUTION.txt", "citation.bib", "aoi.geojson")},
        attribution=("x",),
        dataset=DatasetFacts("x", None),
        bands=(nameless,),
    )
    with pytest.raises(UnsupportedRecipe):
        run(_recipe(["blue"], {"form": "multi_band", "resolution_m": 20.0}), workdir=tmp_path, progress=lambda d, t: None, operators=OPERATORS, attachments=attachments)

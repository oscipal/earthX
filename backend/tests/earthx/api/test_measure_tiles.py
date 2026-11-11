"""The measurement of the tile path (M5-30b part 1, adr/0032 §8.5, F11).

No network: the items are made up, the files are synthetic COGs on disk read by the mosaic tile's own reader, and the
resolver answers with a public address without asking anyone. What has to hold besides the numbers: nothing it
prints names the rectangle, an address or an item id.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import morecantile
import numpy
import pytest
import rasterio
import yaml
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from shapely.geometry import Point, box

from earthx.access.resolve import ResolvedAsset
from earthx.api import measure_tiles
from earthx.api.dependencies import policy_from_registry
from earthx.api.measure_tiles import (
    CannotMeasure,
    Gathered,
    ZoomRow,
    check_dataset,
    count_downloads,
    gather,
    measure_zoom,
    parse_args,
    read_twice,
    render_json,
    render_table,
    scenes_touching_tile,
    tile_at_centre,
)
from earthx.catalog.datasets import registry
from earthx.catalog.registry import LicenseTier
from earthx.gateway.gdal import tile_gdal_options
from earthx.readers.cog import AssetPath

REPO = Path(__file__).resolve().parents[4]
TMS = morecantile.tms.get("WebMercatorQuad")
BBOX = (7.41, 46.93, 7.47, 46.97)
SECRET_HOST_PART = "secret-place-1234-5678"


def _public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


# --- arguments


def test_the_arguments_take_a_rectangle_and_give_defaults() -> None:
    args = parse_args(["swissalti3d", "--bbox", "7.4,46.9,7.5,47.0"])
    assert args.bbox == (7.4, 46.9, 7.5, 47.0)
    assert args.zooms == tuple(range(15))
    assert (args.max_files, args.max_items, args.format, args.asset) == (64, 500, "table", None)
    assert args.datetime == (None, None)


@pytest.mark.parametrize(
    "bbox",
    ["7.5,46.9,7.4,47.0", "7.4,47.0,7.5,46.9", "7.4,46.9,7.5", "a,b,c,d", "7.4,46.9,7.5,nan", "-200,0,10,10", "0,-89,1,1"],
)
def test_a_rectangle_that_is_no_rectangle_is_refused(bbox: str) -> None:
    with pytest.raises(SystemExit):
        parse_args(["swissalti3d", "--bbox", bbox])


@pytest.mark.parametrize("zooms", ["14-3", "-1", "0-25", "x", "3-"])
def test_a_zoom_range_outside_the_grid_or_backwards_is_refused(zooms: str) -> None:
    with pytest.raises(SystemExit):
        parse_args(["swissalti3d", "--bbox", "7.4,46.9,7.5,47.0", "--zooms", zooms])


def test_one_zoom_level_and_one_day_are_enough() -> None:
    args = parse_args(["s", "--bbox", "7.4,46.9,7.5,47.0", "--zooms", "10", "--datetime", "2026-10-01"])
    assert args.zooms == (10,)
    start, end = args.datetime
    assert (start.isoformat(), end.isoformat()) == ("2026-10-01T00:00:00+00:00", "2026-10-01T23:59:59+00:00")


@pytest.mark.parametrize("value", ["0", "-3", "many"])
def test_the_caps_are_whole_numbers_above_zero(value: str) -> None:
    with pytest.raises(SystemExit):
        parse_args(["s", "--bbox", "7.4,46.9,7.5,47.0", "--max-files", value])


# --- what may be measured


def test_an_unknown_dataset_is_refused_by_name() -> None:
    with pytest.raises(CannotMeasure, match="no dataset 'nothing'"):
        check_dataset(registry(), "nothing")


def test_a_catalogue_entry_and_an_entry_without_viewer_are_refused_as_the_tile_route_refuses_them() -> None:
    catalogue = SimpleNamespace(license=SimpleNamespace(tier=LicenseTier.CATALOG), viewer=object())
    hidden = SimpleNamespace(license=SimpleNamespace(tier=LicenseTier.DISPLAY), viewer=None)
    with pytest.raises(CannotMeasure, match="catalogue entry only"):
        check_dataset(SimpleNamespace(get=lambda _: catalogue), "x")
    with pytest.raises(CannotMeasure, match="no released zoom range"):
        check_dataset(SimpleNamespace(get=lambda _: hidden), "x")


# --- counting GDAL's requests


def test_each_download_line_is_one_request_and_its_ranges_are_its_bytes() -> None:
    lines = [
        "CPLE_None in VSICURL: Downloading 0-16383 (https://host/a/tile_2485-1109.tif)...",
        "VSICURL: Downloading 16384-49151 (https://host/a/tile_2485-1109.tif)...",
        "VSICURL: Downloading 0-99, 200-299 (https://host/b.tif)...",
        "GDAL: GDALOpen(/vsicurl/https://host/a/tile_2485-1109.tif) succeeds",
    ]
    assert count_downloads(lines) == (3, 16384 + 32768 + 200)


def test_digits_in_an_address_are_not_counted_as_a_range() -> None:
    assert count_downloads(["VSICURL: Downloading 0-9 (https://host/2000-3000/9-99.tif)..."]) == (1, 10)


# --- the tile and its scenes


def test_the_tile_of_a_level_lies_over_the_middle_of_the_rectangle() -> None:
    for zoom in (0, 8, 14):
        tile = tile_at_centre(BBOX, zoom)
        assert tile.z == zoom
        assert box(*TMS.bounds(tile)).covers(Point(7.44, 46.95))


def _outlines() -> dict[str, Any]:
    return {f"t{n}": box(7.40 + 0.013 * n, 46.94, 7.413 + 0.013 * n, 46.953) for n in range(6)}


def test_the_scenes_of_a_tile_keep_the_order_of_the_mosaic() -> None:
    outlines = _outlines()
    order = ["t5", "t0", "t3", "t1", "t4", "t2"]
    assert scenes_touching_tile(order, outlines, tile_at_centre(BBOX, 8)) == order
    small = tile_at_centre((7.40, 46.94, 7.412, 46.952), 16)
    assert scenes_touching_tile(order, outlines, small) == ["t0"]


def _gathered(outlines: dict[str, Any]) -> Gathered:
    refs = {
        item_id: ResolvedAsset("d", item_id, "a", "cog", f"https://host.example/{item_id}.tif", None, None, "geotransform")
        for item_id in outlines
    }
    return Gathered("d", "a", len(outlines), 1, tuple(sorted(outlines)), refs, outlines, {})


def test_a_tile_without_scenes_and_a_tile_over_the_cap_are_not_read() -> None:
    def never(*_: Any) -> dict[str, Any]:
        raise AssertionError("not read")

    gathered = _gathered(_outlines())
    assert measure_zoom(gathered, 10, BBOX, 5, {}, read=never) == ZoomRow(10, 6, "over cap")
    far = (8.5, 47.5, 8.6, 47.6)
    assert measure_zoom(gathered, 10, far, 64, {}, read=never) == ZoomRow(10, 0, "no scenes")


def test_a_tile_is_read_with_its_scenes_in_order_and_a_failure_keeps_its_kind() -> None:
    seen: list[Any] = []

    def fake(scenes: Any, dataset: str, bounds: Any, tile: Any, config: Any) -> dict[str, Any]:
        seen.append(([s.item_id for s in scenes], dataset, tile, config))
        return {"status": "ok", "cold_s": 1.5, "warm_s": 0.2, "cold_requests": 12, "unknown": 1}

    row = measure_zoom(_gathered(_outlines()), 9, BBOX, 64, {"A": "1"}, read=fake)
    assert seen[0][0] == ["t0", "t1", "t2", "t3", "t4", "t5"]
    assert seen[0][1:] == ("d", (tuple(tile_at_centre(BBOX, 9))), {"A": "1"})
    assert (row.status, row.files, row.read, row.cold_s, row.cold_requests) == ("ok", 6, 6, 1.5, 12)
    failed = measure_zoom(_gathered(_outlines()), 9, BBOX, 64, {}, read=lambda *_: {"status": "RasterioIOError"})
    assert failed.status == "RasterioIOError" and failed.cold_s is None


# --- the read itself, with the mosaic tile's reader


def _cog(path: Path, west: float, value: float, item_id: str) -> AssetPath:
    pixel = 0.0001
    profile = {
        "driver": "GTiff", "dtype": "float32", "count": 1, "height": 256, "width": 256, "crs": "EPSG:4326",
        "transform": from_origin(west, 46.96, pixel, pixel), "nodata": -9999.0, "tiled": True,
        "blockxsize": 128, "blockysize": 128,
    }
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with rasterio.open(path, "w", **profile) as target:
            target.write(numpy.full((256, 256), value, dtype="float32"), 1)
        with rasterio.open(path, "r+") as target:
            target.build_overviews([2, 4], Resampling.average)
    return AssetPath(str(path), dataset_id="synthetic", item_id=item_id, asset="dtm")


def test_a_tile_is_read_cold_and_warm_and_says_how_much_of_it_is_filled(tmp_path: Path) -> None:
    scenes = [_cog(tmp_path / "a.tif", 7.43, 500.0, "a"), _cog(tmp_path / "b.tif", 7.4556, 900.0, "b")]
    tile = tile_at_centre((7.43, 46.9344, 7.4812, 46.96), 13)
    ticks = iter([0.0, 1.25, 2.0, 2.5])
    result = read_twice(scenes, "synthetic", (7.43, 46.93, 7.49, 46.96), tuple(tile), {}, clock=lambda: next(ticks))
    assert result["status"] == "ok"
    assert (result["cold_s"], result["warm_s"]) == (1.25, 0.5)
    # Local files: no download line, so no request and no byte.
    assert (result["cold_requests"], result["cold_mb"], result["warm_requests"]) == (0, 0.0, 0)
    assert 0 < result["filled"] < 1
    assert result["tiff_kb"] > 0


def test_a_scene_that_cannot_be_read_ends_the_row_with_the_kind_and_without_its_path(tmp_path: Path) -> None:
    missing = AssetPath(str(tmp_path / SECRET_HOST_PART / "x.tif"), dataset_id="d", item_id="secret-item", asset="a")
    tile = tile_at_centre(BBOX, 12)
    result = read_twice([missing], "d", BBOX, tuple(tile), {})
    assert result["status"] not in ("ok", "")
    assert SECRET_HOST_PART not in json.dumps(result) and "secret-item" not in json.dumps(result)


# --- the overpass, its addresses and its order


def _item(item_id: str, west: float, state: str | None, host: str = "data.geo.admin.ch") -> dict[str, Any]:
    properties: dict[str, Any] = {"datetime": "2021-01-01T00:00:00Z", "proj:code": "EPSG:2056"}
    if state is not None:
        properties["earthx:state"] = state
    return {
        "type": "Feature",
        "id": item_id,
        "bbox": [west, 46.94, west + 0.013, 46.953],
        "geometry": box(west, 46.94, west + 0.013, 46.953).__geo_interface__,
        "properties": properties,
        "assets": {
            "dtm": {"href": f"https://{host}/{SECRET_HOST_PART}/{item_id}.tif", "type": "image/tiff; application=geotiff"}
        },
    }


def test_the_largest_overpass_is_measured_and_what_cannot_be_read_is_only_counted() -> None:
    reg = registry()
    config = reg.get("swissalti3d")
    items = [
        _item("tile-c", 7.426, "2021"),
        _item("tile-a", 7.400, "2021"),
        _item("tile-b", 7.413, "2021"),
        _item("tile-elsewhere", 7.439, "2021", host="example.org"),
        _item("tile-old", 7.400, "2019"),
        _item("tile-nokey", 7.400, None),
    ]
    gathered = gather(config, items, None, policy_from_registry(reg), _public)
    assert gathered.asset == "dtm"
    assert gathered.order == ("tile-a", "tile-b", "tile-c")
    assert (gathered.items_found, gathered.overpasses) == (6, 2)
    assert gathered.skipped == {"no overpass key": 1, "AssetRejected": 1}


def test_an_overpass_without_the_asset_is_refused_without_naming_an_item() -> None:
    reg = registry()
    with pytest.raises(CannotMeasure) as refused:
        gather(reg.get("swissalti3d"), [_item("tile-a", 7.4, "2021")], "dtm_2m", policy_from_registry(reg), _public)
    assert "tile-a" not in str(refused.value)


# --- what is printed


def test_the_report_names_neither_the_rectangle_nor_an_address_nor_an_item() -> None:
    reg = registry()
    items = [_item("tile-a", 7.400, "2021"), _item("tile-b", 7.413, "2021")]
    gathered = gather(reg.get("swissalti3d"), items, None, policy_from_registry(reg), _public)
    rows = [ZoomRow(13, 2, "ok", 2, 1.2, 0.3, 4, 0.8, 0, 0.0, 0.5, 120.0), ZoomRow(8, 70, "over cap")]
    for text in (render_table(gathered, rows, 64), render_json(gathered, rows, 64)):
        for secret in ("tile-a", "tile-b", SECRET_HOST_PART, "data.geo.admin.ch", "7.4", "46.9"):
            assert secret not in text
    assert "| 13 | 2 | ok | 1.2 | 0.3 | 4 | 0.8 | 0 | 0.0 | 0.5 | 120.0 |" in render_table(gathered, rows, 64)
    assert json.loads(render_json(gathered, rows, 64))["rows"][1]["status"] == "over cap"


def test_a_failure_of_the_run_is_reported_by_its_kind_only(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    def broken(*_: Any, **__: Any) -> str:
        raise RuntimeError(f"https://{SECRET_HOST_PART}/x.tif refused")

    monkeypatch.setattr(measure_tiles, "run", broken)
    assert measure_tiles.main(["swissalti3d", "--bbox", "7.4,46.9,7.5,47.0"]) == 1
    error = capsys.readouterr().err
    assert "RuntimeError" in error and SECRET_HOST_PART not in error


def test_an_unknown_dataset_ends_the_run_with_its_reason(capsys: Any) -> None:
    assert measure_tiles.main(["nothing", "--bbox", "7.4,46.9,7.5,47.0"]) == 1
    assert "no dataset 'nothing'" in capsys.readouterr().err


# --- the compose service


def test_the_measurement_runs_only_by_hand_under_its_profile() -> None:
    services = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))["services"]
    service = services["measure-tiles"]
    assert service["profiles"] == ["measure"]
    assert service["entrypoint"] == ["python", "-m", "earthx.api.measure_tiles"]
    assert service["depends_on"]["catalog-load"]["condition"] == "service_completed_successfully"
    for name in ("PGUSER", "PGPASSWORD", "PGDATABASE"):
        assert str(service["environment"][name]).startswith("${")


def test_the_gdal_configuration_is_the_tiles_own() -> None:
    config = tile_gdal_options(policy_from_registry(registry()))
    assert config["GDAL_HTTP_MULTIRANGE"] == "SERIAL"

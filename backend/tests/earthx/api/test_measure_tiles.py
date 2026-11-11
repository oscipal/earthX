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

from earthx.access.mosaic_tiles import MAX_MOSAIC_THREADS, MOSAIC_THREADS
from earthx.api import measure_tiles
from earthx.api.dependencies import policy_from_registry
from earthx.api.measure_tiles import (
    CannotMeasure,
    ZoomRow,
    check_dataset,
    choose,
    count_downloads,
    gather,
    measure_zoom,
    parse_args,
    read_twice,
    render_json,
    render_table,
    run,
    scenes_touching_tile,
    tile_at_centre,
    tile_bounds,
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
    assert args.threads == MOSAIC_THREADS
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


def test_the_threads_are_one_to_sixteen() -> None:
    args = ["s", "--bbox", "7.4,46.9,7.5,47.0", "--threads"]
    assert parse_args([*args, "8"]).threads == 8
    assert parse_args([*args, str(MAX_MOSAIC_THREADS)]).threads == 16
    for value in ("0", "17", "-2", "many", "2.5"):
        with pytest.raises(SystemExit):
            parse_args([*args, value])


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


def _line(count: int, state: str | None = "2021", start: int = 0) -> list[dict[str, Any]]:
    """``count`` neighbouring tiles in a row, each about 1 km wide, named after their number."""
    return [_item(f"t{state}-{n}", 7.40 + 0.013 * n, state) for n in range(start, start + count)]


class _Source:
    """A fake search: the items whose footprint meets the rectangle asked, cut at ``cut``; it records each ask."""

    def __init__(self, items: list[dict[str, Any]], cut: int = 10_000) -> None:
        self.items, self.cut, self.asked = items, cut, []

    def __call__(self, bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
        self.asked.append(bbox)
        west, south, east, north = bbox
        meeting = [
            item
            for item in self.items
            if item["bbox"][0] <= east and item["bbox"][2] >= west and item["bbox"][1] <= north
            and item["bbox"][3] >= south
        ]  # fmt: skip
        return meeting[: self.cut]


class _Reads:
    """A fake read: records what it was asked and answers with a row."""

    def __init__(self) -> None:
        self.asked: list[Any] = []

    def __call__(self, scenes: Any, dataset: str, bounds: Any, tile: Any, config: Any, **options: Any) -> dict[str, Any]:
        self.asked.append(([s.item_id for s in scenes], dataset, bounds, tile, config, options))
        return {"status": "ok", "cold_s": 1.5, "warm_s": 0.2, "cold_requests": 12, "unknown": 1}


def _zoom(source: _Source, zoom: int, reads: _Reads, *, max_files: int = 64, max_items: int = 500, **more: Any) -> ZoomRow:
    reg = registry()
    config = reg.get("swissalti3d")
    chosen = choose(config, _line(6), None)
    return measure_zoom(
        config, chosen, zoom, BBOX, fetch=source, policy=policy_from_registry(reg), resolve=_public,
        max_files=max_files, max_items=max_items, gdal_config={"A": "1"}, read=reads, **more,
    )  # fmt: skip


def test_each_zoom_level_fetches_the_items_in_the_bounds_of_its_own_tile() -> None:
    source, reads = _Source(_line(6)), _Reads()
    for zoom in (6, 9, 12):
        _zoom(source, zoom, reads)
    expected = [tile_bounds(tile_at_centre(BBOX, zoom)) for zoom in (6, 9, 12)]
    assert source.asked == expected
    west, south, east, north = expected[0]
    assert (east - west) > (expected[1][2] - expected[1][0]) > (expected[2][2] - expected[2][0])
    assert west < 7.44 < east and south < 46.95 < north


def test_the_bounds_of_a_tile_stay_inside_the_valid_latitudes_and_longitudes(monkeypatch: pytest.MonkeyPatch) -> None:
    assert tile_bounds(tile_at_centre(BBOX, 0)) == (-180.0, -85.0511287798066, 180.0, 85.0511287798066)
    monkeypatch.setattr(measure_tiles, "_TMS", SimpleNamespace(bounds=lambda _: (-181.0, -91.0, 181.0, 91.0)))
    assert tile_bounds(None) == (-180.0, -90.0, 180.0, 90.0)  # type: ignore[arg-type]


def test_a_tile_reads_the_files_of_its_bounds_that_the_rectangle_did_not_find() -> None:
    # The rectangle holds six tiles; the tile of z8 reaches ten more along the row.
    source, reads = _Source(_line(16)), _Reads()
    row = _zoom(source, 8, reads)
    assert row.files == row.read == 16 and row.status == "ok"
    assert sorted(reads.asked[0][0]) == sorted(f"t2021-{n}" for n in range(16))


def test_only_the_items_of_the_chosen_overpass_are_kept_and_read() -> None:
    source, reads = _Source([*_line(6), *_line(9, "2019"), *_line(3, None, 20)]), _Reads()
    row = _zoom(source, 9, reads)
    assert reads.asked[0][0] == [f"t2021-{n}" for n in range(6)]
    assert (row.status, row.files, row.read, row.cold_s, row.cold_requests) == ("ok", 6, 6, 1.5, 12)


def test_a_tile_is_read_with_its_scenes_in_order_its_config_and_threads() -> None:
    reads = _Reads()
    row = _zoom(_Source(_line(6)), 9, reads, threads=8)
    scenes, dataset, bounds, tile, config, options = reads.asked[0]
    assert (dataset, tile, config, options) == ("swissalti3d", tuple(tile_at_centre(BBOX, 9)), {"A": "1"}, {"threads": 8})
    assert bounds == pytest.approx((7.40, 46.94, 7.40 + 0.013 * 6, 46.953))
    assert row.status == "ok"


def test_a_failure_of_the_read_keeps_its_kind() -> None:
    failed = _zoom(_Source(_line(6)), 9, lambda *_, **__: {"status": "RasterioIOError"})  # type: ignore[arg-type]
    assert failed.status == "RasterioIOError" and failed.cold_s is None


def test_a_tile_over_the_cap_is_not_read_and_says_how_many_files() -> None:
    reads = _Reads()
    assert _zoom(_Source(_line(6)), 10, reads, max_files=5) == ZoomRow(10, 6, "over cap")
    assert reads.asked == []


def test_a_tile_without_scenes_is_not_read() -> None:
    reads = _Reads()
    far = _Source([_item("far", 8.6, "2021")])
    assert _zoom(far, 10, reads) == ZoomRow(10, 0, "no scenes")
    assert _zoom(_Source(_line(6, "2019")), 10, reads) == ZoomRow(10, 0, "no scenes")
    assert reads.asked == []


def test_a_full_fetch_is_not_read_and_does_not_report_a_count_that_may_be_too_small() -> None:
    reads = _Reads()
    full = _Source(_line(16), cut=7)
    row = _zoom(full, 8, reads, max_items=7)
    assert (row.status, row.read) == ("over items cap", 0)
    assert row.files == 7  # at least; the row's status says the list was cut
    assert reads.asked == []
    # Nothing of the overpass in a cut list is also not "no scenes".
    assert _zoom(_Source(_line(7, "2019"), cut=7), 8, reads, max_items=7).status == "over items cap"
    # One item short of the cap, the list is whole and is read.
    assert _zoom(_Source(_line(6)), 8, reads, max_items=7).status == "ok"


def test_a_full_fetch_over_the_file_cap_is_over_cap() -> None:
    row = _zoom(_Source(_line(16), cut=7), 8, _Reads(), max_items=7, max_files=5)
    assert (row.status, row.files) == ("over cap", 7)


def test_a_run_chooses_by_the_rectangle_and_fetches_by_the_tile(capsys: Any) -> None:
    source, reads = _Source([*_line(6), *_line(2, "2019", 3), *_line(10, start=6)]), _Reads()
    args = parse_args(["swissalti3d", "--bbox", ",".join(map(str, BBOX)), "--zooms", "7-8", "--threads", "8"])
    text = run(args, registry(), fetch=source, resolve=_public, read=reads)
    assert source.asked[0] == BBOX
    assert source.asked[1:] == [tile_bounds(tile_at_centre(BBOX, zoom)) for zoom in (7, 8)]
    assert [ask[5] for ask in reads.asked] == [{"threads": 8}] * 2
    header = text.splitlines()[0]
    assert "8 threads" in header
    assert "| 7 | 16 | ok |" in text and "| 8 | 16 | ok |" in text
    for secret in ("t2021", "t2019", SECRET_HOST_PART, "7.4", "46.9"):
        assert secret not in text


def test_a_run_without_items_in_the_rectangle_says_so() -> None:
    args = parse_args(["swissalti3d", "--bbox", ",".join(map(str, BBOX))])
    with pytest.raises(CannotMeasure, match="no item in the rectangle"):
        run(args, registry(), fetch=_Source([]), resolve=_public)


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
    for text in (render_table(gathered, rows, 64, 8), render_json(gathered, rows, 64, 8)):
        for secret in ("tile-a", "tile-b", SECRET_HOST_PART, "data.geo.admin.ch", "7.4", "46.9"):
            assert secret not in text
    assert "| 13 | 2 | ok | 1.2 | 0.3 | 4 | 0.8 | 0 | 0.0 | 0.5 | 120.0 |" in render_table(gathered, rows, 64)
    assert json.loads(render_json(gathered, rows, 64))["rows"][1]["status"] == "over cap"
    assert json.loads(render_json(gathered, rows, 64, 8))["threads"] == 8
    assert "at most 64 files read per tile, 8 threads." in render_table(gathered, rows, 64, 8).splitlines()[0]


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


# --- the logging module is as it was after a read (#336)


@pytest.mark.parametrize("fails", [False, True], ids=["read", "failed read"])
def test_a_read_leaves_the_gdal_logger_as_it_found_it(tmp_path: Path, fails: bool) -> None:
    import logging

    gdal_logger = logging.getLogger("rasterio")
    before = (gdal_logger.level, gdal_logger.propagate, list(gdal_logger.handlers))
    scene = (
        AssetPath(str(tmp_path / "missing.tif"), dataset_id="d", item_id="x", asset="a")
        if fails
        else _cog(tmp_path / "a.tif", 7.43, 500.0, "a")
    )
    tile = tile_at_centre((7.43, 46.9344, 7.4812, 46.96), 13)
    result = read_twice([scene], "d", (7.43, 46.93, 7.49, 46.96), tuple(tile), {})
    assert (result["status"] == "ok") is not fails
    assert (gdal_logger.level, gdal_logger.propagate, list(gdal_logger.handlers)) == before


def test_gdal_lines_reach_only_the_counter_during_a_read_and_the_process_again_afterwards() -> None:
    import logging

    gdal_logger = logging.getLogger("rasterio")
    seen: list[str] = []

    class Catch(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            seen.append(record.getMessage())

    catch = Catch(logging.DEBUG)
    root = logging.getLogger()
    root.addHandler(catch)
    try:
        with measure_tiles._counting_gdal_lines() as downloads:
            gdal_logger.debug("VSICURL: Downloading 0-9 (https://%s/x.tif)...", SECRET_HOST_PART)
            assert downloads.take() == (1, 10)
        assert seen == []
        gdal_logger.warning("after the read")
        assert seen == ["after the read"]
    finally:
        root.removeHandler(catch)

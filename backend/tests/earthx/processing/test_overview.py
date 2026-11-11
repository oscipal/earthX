"""The core of the overview pyramid on synthetic files in tmp dirs (M5-30b part 8a, adr/0032 §5.2, §8.2)."""

from __future__ import annotations

import logging
from pathlib import Path

import morecantile
import numpy as np
import pytest
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds

from earthx.catalog.registry import OverviewResampling
from earthx.gateway import HostPacer
from earthx.processing import overview
from earthx.processing.overview import (
    TILE_SIZE,
    base_hash,
    base_tile,
    base_zoom,
    children_of,
    encode_tile,
    levels,
    parent_tile,
    tile_image,
)
from earthx.readers.cog import AssetPath

pytestmark = pytest.mark.filterwarnings("ignore:The dataset has no Overviews")

TMS = morecantile.tms.get("WebMercatorQuad")
TILE = morecantile.Tile(8, 5, 4)
HOST = "data.example.org"
AVERAGE, MODE, NEAREST = OverviewResampling.AVERAGE, OverviewResampling.MODE, OverviewResampling.NEAREST


class Pacing:
    """A pacer that only records."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int | None]] = []

    def wait(self, host: str) -> None:
        self.calls.append(("wait", host, None))

    def account(self, host: str, requests: int) -> None:
        self.calls.append(("account", host, requests))


def cog(
    path: Path,
    array: np.ndarray,
    *,
    part: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0),
    nodata: float | None = 0,
) -> AssetPath:
    """A GeoTIFF in EPSG:3857 whose raster covers ``part`` (fractions west, south, east, north) of ``TILE``."""
    left, bottom, right, top = TMS.xy_bounds(TILE)
    west, south = left + part[0] * (right - left), bottom + part[1] * (top - bottom)
    east, north = left + part[2] * (right - left), bottom + part[3] * (top - bottom)
    height, width = array.shape
    profile = {
        "driver": "GTiff", "width": width, "height": height, "count": 1, "dtype": array.dtype.name,
        "crs": "EPSG:3857", "transform": from_bounds(west, south, east, north, width, height), "nodata": nodata,
    }  # fmt: skip
    with rasterio.open(path, "w", **profile) as target:
        target.write(array, 1)
    return AssetPath(str(path), dataset_id="synthetic", item_id=path.stem, asset="dem")


def read(scenes: list[AssetPath], resampling: OverviewResampling = AVERAGE, pacer: object | None = None):
    return base_tile(scenes, TILE, resampling=resampling, pacer=pacer or Pacing(), gdal_config={})


# --- the base tile


def test_a_base_tile_holds_the_values_of_the_source_in_its_type_and_on_the_grid_of_its_tile(tmp_path: Path) -> None:
    values = np.arange(TILE_SIZE * TILE_SIZE, dtype="int16").reshape(TILE_SIZE, TILE_SIZE) % 3000 + 1
    image = read([cog(tmp_path / "a.tif", values, nodata=-32768)])
    assert image is not None
    assert image.array.shape == (1, TILE_SIZE, TILE_SIZE)
    assert image.array.dtype == np.int16
    assert image.nodata == -32768
    assert image.crs == TMS.rasterio_crs
    assert tuple(image.bounds) == pytest.approx(tuple(TMS.xy_bounds(TILE)))
    np.testing.assert_array_equal(image.array[0].filled(0), values)


def test_two_adjacent_files_make_one_tile(tmp_path: Path) -> None:
    west = cog(tmp_path / "w.tif", np.full((512, 256), 10, "uint8"), part=(0.0, 0.0, 0.5, 1.0))
    east = cog(tmp_path / "e.tif", np.full((512, 256), 20, "uint8"), part=(0.5, 0.0, 1.0, 1.0))
    image = read([west, east])
    assert image is not None
    band = image.array[0]
    assert (band[:, :256] == 10).all() and (band[:, 256:] == 20).all()
    assert not np.ma.getmaskarray(band).any()


def test_where_files_overlap_the_first_valid_pixel_wins_and_holes_are_filled_from_the_next(tmp_path: Path) -> None:
    first = np.full((512, 512), 10, "uint8")
    first[:, :128] = 0  # nodata in the first file
    second = np.full((512, 512), 20, "uint8")
    one, two = cog(tmp_path / "1.tif", first), cog(tmp_path / "2.tif", second)
    image = read([one, two])
    assert image is not None
    band = image.array[0]
    assert (band[:, :128] == 20).all() and (band[:, 128:] == 10).all()
    swapped = read([two, one])
    assert swapped is not None
    assert (swapped.array[0] == 20).all()


def test_reading_stops_when_every_pixel_is_filled(tmp_path: Path) -> None:
    full = cog(tmp_path / "full.tif", np.full((512, 512), 7, "uint8"))
    never = AssetPath(str(tmp_path / "missing.tif"), dataset_id="d", item_id="m", asset="a")
    image = read([full, never])
    assert image is not None and (image.array[0] == 7).all()


@pytest.mark.parametrize(("resampling", "expected"), [(AVERAGE, 3), (MODE, 1), (NEAREST, 9)])
def test_the_resampling_decides_what_a_block_of_four_source_pixels_becomes(
    tmp_path: Path, resampling: OverviewResampling, expected: int
) -> None:
    source = np.tile(np.array([[1, 1], [1, 9]], "uint8"), (512, 512))  # 1024 px for a 512 px tile
    image = read([cog(tmp_path / "a.tif", source)], resampling)
    assert image is not None
    assert (image.array[0] == expected).all()


def test_a_float_file_keeps_its_type_and_nan_is_nodata(tmp_path: Path) -> None:
    values = np.full((512, 512), 4.5, "float32")
    values[:100] = np.nan
    image = read([cog(tmp_path / "f.tif", values, nodata=float("nan"))])
    assert image is not None
    assert image.array.dtype == np.float32
    assert np.isnan(image.nodata)
    assert np.ma.getmaskarray(image.array[0])[:100].all()
    assert (image.array[0][100:] == 4.5).all()


def test_a_tile_without_a_valid_pixel_is_none(tmp_path: Path) -> None:
    empty = cog(tmp_path / "empty.tif", np.zeros((512, 512), "uint8"))
    far = cog(tmp_path / "far.tif", np.full((64, 64), 5, "uint8"))
    assert read([empty]) is None
    assert read([]) is None
    other = morecantile.Tile(TILE.x + 3, TILE.y, TILE.z)
    assert base_tile([far], other, resampling=AVERAGE, pacer=Pacing(), gdal_config={}) is None


def test_a_file_that_cannot_be_read_fails_the_tile_instead_of_being_left_out(tmp_path: Path) -> None:
    missing = AssetPath(str(tmp_path / "missing.tif"), dataset_id="d", item_id="m", asset="a")
    good = cog(tmp_path / "good.tif", np.full((512, 512), 7, "uint8"))
    with pytest.raises(rasterio.errors.RasterioIOError):
        read([missing, good])


def test_files_of_different_types_are_refused(tmp_path: Path) -> None:
    half = np.full((512, 512), 7, "uint8")
    half[:, 256:] = 0
    one = cog(tmp_path / "1.tif", half)
    two = cog(tmp_path / "2.tif", np.full((512, 512), 7, "float32"), nodata=None)
    with pytest.raises(ValueError, match="data type"):
        read([one, two])


def test_a_plain_string_is_no_file_to_read(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        read([str(tmp_path / "a.tif")])  # type: ignore[list-item]


def test_the_resampling_is_one_of_the_registry(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        read([cog(tmp_path / "a.tif", np.ones((512, 512), "uint8"))], "bilinear")  # type: ignore[arg-type]


# --- reading with spacing


class CountingReader(overview.CogReader):  # type: ignore[misc]
    """A reader that logs GDAL's download lines the way a remote file would."""

    lines = 3
    fail = False

    def tile(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        for index in range(self.lines):
            logging.getLogger("rasterio").debug(
                "VSICURL: Downloading %d-%d (https://secret.example.org/x.tif)", index, 9
            )
        if self.fail:
            raise RuntimeError("source failed")
        return super().tile(*args, **kwargs)


@pytest.fixture
def remote(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every file reads as if it lay on ``HOST``, with three counted requests."""
    monkeypatch.setattr(overview, "asset_host", lambda path: HOST)
    monkeypatch.setattr(overview, "CogReader", CountingReader)
    monkeypatch.setattr(CountingReader, "fail", False)


def test_each_remote_file_is_read_between_wait_and_account_with_its_counted_requests(
    tmp_path: Path, remote: None
) -> None:
    pacer = Pacing()
    one = cog(tmp_path / "1.tif", np.full((512, 512), 7, "uint8"), part=(0.0, 0.0, 0.5, 1.0))
    two = cog(tmp_path / "2.tif", np.full((512, 512), 8, "uint8"), part=(0.5, 0.0, 1.0, 1.0))
    assert read([one, two], pacer=pacer) is not None
    assert pacer.calls == [("wait", HOST, None), ("account", HOST, 3)] * 2


def test_the_requests_of_a_file_that_failed_are_accounted_too(tmp_path: Path, remote: None, monkeypatch) -> None:
    monkeypatch.setattr(CountingReader, "fail", True)
    pacer = Pacing()
    with pytest.raises(RuntimeError):
        read([cog(tmp_path / "1.tif", np.ones((512, 512), "uint8"))], pacer=pacer)
    assert pacer.calls == [("wait", HOST, None), ("account", HOST, 3)]


def test_a_file_on_disk_is_not_paced(tmp_path: Path) -> None:
    pacer = Pacing()
    assert read([cog(tmp_path / "1.tif", np.ones((512, 512), "uint8"))], pacer=pacer) is not None
    assert pacer.calls == []


def test_gdals_lines_are_counted_and_not_logged(tmp_path: Path, remote: None) -> None:
    seen: list[str] = []

    class Catch(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            seen.append(record.getMessage())

    scene = cog(tmp_path / "1.tif", np.ones((512, 512), "uint8"))
    catch = Catch(logging.DEBUG)
    root = logging.getLogger()
    level = root.level
    root.addHandler(catch)
    root.setLevel(logging.DEBUG)
    try:
        read([scene])
        assert seen == []
        logging.getLogger("rasterio").debug("VSICURL: Downloading 0-9 (https://secret.example.org/x.tif)")
        assert len(seen) == 1  # the counter-sample: outside a read the line does reach the log
    finally:
        root.removeHandler(catch)
        root.setLevel(level)


def test_the_gateways_host_pacer_spaces_the_files_of_a_build(tmp_path: Path, remote: None) -> None:
    now = [1000.0]

    def sleep(seconds: float) -> None:
        now[0] += seconds

    pacer = HostPacer(0.25, clock=lambda: now[0], sleep=sleep)
    scenes = [
        cog(tmp_path / f"{name}.tif", np.full((512, 128), value, "uint8"), part=(index / 4, 0.0, (index + 1) / 4, 1.0))
        for index, (name, value) in enumerate([("a", 1), ("b", 2), ("c", 3), ("d", 4)])
    ]
    assert read(scenes, pacer=pacer) is not None
    # four files of three requests each: the second to fourth start 0.75 s apart
    assert now[0] - 1000.0 == pytest.approx(3 * 0.75)


# --- the level above


def block(value: int | float, dtype: str = "uint8") -> np.ma.MaskedArray:
    return np.ma.array(np.full((TILE_SIZE, TILE_SIZE), value, dtype), mask=False)


def test_a_parent_averages_the_valid_pixels_of_each_block_and_places_the_children_by_quadrant() -> None:
    children = [block(10, "float32"), block(20, "float32"), block(30, "float32"), block(40, "float32")]
    children[0][0, :2] = 20.0
    children[0][1, :2] = np.ma.masked  # a block of two valid pixels
    children[1][0:2, 0:2] = np.ma.masked  # a block with none
    parent = parent_tile(children, AVERAGE)
    assert parent is not None and parent.dtype == np.float32
    assert parent[0, 0] == 20.0 and parent[0, 1] == 10.0  # (20+20)/2 is 20, a plain block is 10
    assert (parent[:256, :256][1:, 1:] == 10).all()
    assert parent[0, 256] is np.ma.masked and parent[1, 256] == 20.0
    assert (parent[:256, 256:][1:, 1:] == 20).all()
    assert (parent[256:, :256] == 30).all() and (parent[256:, 256:] == 40).all()


def test_an_integer_average_is_rounded_to_the_nearest_value() -> None:
    child = block(10)
    child[0, 0], child[0, 1], child[1, 0], child[1, 1] = 1, 2, 2, 2  # mean 1.75
    parent = parent_tile([child, None, None, None], AVERAGE)
    assert parent is not None and parent[0, 0] == 2 and parent.dtype == np.uint8


def test_a_parent_of_classes_takes_the_most_frequent_value_and_the_smallest_of_equals() -> None:
    child = block(10)
    child[0, :2], child[1, :2] = [40, 40], [40, 10]  # 40 three times
    child[0, 2:4], child[1, 2:4] = [50, 50], [20, 20]  # 50 and 20 twice each: 20
    child[0, 4:6], child[1, 4:6] = [60, 70], [80, 90]  # all alone: 60
    parent = parent_tile([child, None, None, None], MODE)
    assert parent is not None
    assert list(parent[0, :3]) == [40, 20, 60]


def test_mode_and_average_ignore_masked_pixels_and_nearest_takes_the_first_valid_one() -> None:
    child = block(10)
    child[0, 0], child[0, 1], child[1, 0], child[1, 1] = 5, 6, 7, 8
    child[0, 0] = np.ma.masked
    assert parent_tile([child, None, None, None], NEAREST)[0, 0] == 6
    assert parent_tile([child, None, None, None], MODE)[0, 0] == 6
    assert parent_tile([child, None, None, None], AVERAGE)[0, 0] == 7


def test_non_finite_floats_are_holes_not_values() -> None:
    child = block(2.0, "float32")
    child[0, 0] = np.nan
    child[2, 2] = np.inf
    child[3, 3] = np.inf
    child[2, 3] = np.inf
    child[3, 2] = np.inf
    parent = parent_tile([child, None, None, None], AVERAGE)
    assert parent is not None
    assert parent[0, 0] == 2.0 and parent[1, 1] is np.ma.masked


def test_a_missing_child_is_nodata_and_no_child_with_a_value_is_none() -> None:
    parent = parent_tile([None, block(3), None, None], MODE)
    assert parent is not None
    assert np.ma.getmaskarray(parent)[:, :256].all() and (parent[:256, 256:] == 3).all()
    assert parent_tile([None] * 4, AVERAGE) is None
    empty = np.ma.array(np.zeros((TILE_SIZE, TILE_SIZE), "uint8"), mask=True)
    assert parent_tile([empty, None, empty, None], MODE) is None


@pytest.mark.parametrize("resampling", list(OverviewResampling))
def test_a_parent_of_four_equal_tiles_is_that_tile_at_half_the_detail(resampling: OverviewResampling) -> None:
    values = np.random.default_rng(1).integers(1, 200, (TILE_SIZE, TILE_SIZE)).astype("uint8")
    same = np.ma.array(np.repeat(np.repeat(values[::2, ::2], 2, 0), 2, 1), mask=False)
    parent = parent_tile([same] * 4, resampling)
    assert parent is not None
    np.testing.assert_array_equal(parent[:256, :256].filled(0), values[::2, ::2])


def test_a_parent_refuses_bad_children() -> None:
    with pytest.raises(ValueError, match="four"):
        parent_tile([block(1)] * 3, AVERAGE)
    with pytest.raises(ValueError, match="data type"):
        parent_tile([block(1), block(1, "float32"), None, None], AVERAGE)
    with pytest.raises(ValueError):
        parent_tile([np.ma.array(np.ones((64, 64), "uint8")), None, None, None], AVERAGE)
    with pytest.raises(TypeError):
        parent_tile([block(1)] * 4, "average")  # type: ignore[arg-type]


def test_the_children_of_a_tile_are_the_four_below_it_in_the_order_of_the_parent() -> None:
    assert [(tile.x, tile.y, tile.z) for tile in children_of(morecantile.Tile(3, 5, 4))] == [
        (6, 10, 5), (7, 10, 5), (6, 11, 5), (7, 11, 5),
    ]  # fmt: skip


# --- the stored tile


def tiff_tags(data: bytes) -> set[int]:
    """The tag numbers of the first directory of a classic TIFF (little endian): 322 is the tile width, 273 a strip."""
    assert data[:4] == b"II*\x00"
    start = int.from_bytes(data[4:8], "little")
    count = int.from_bytes(data[start : start + 2], "little")
    return {int.from_bytes(data[start + 2 + 12 * index :][:2], "little") for index in range(count)}


def decode(data: bytes) -> tuple[np.ndarray, dict]:
    with MemoryFile(data) as memory, memory.open() as source:
        profile = {
            "bounds": tuple(source.bounds), "crs": source.crs, "width": source.width, "height": source.height,
            "dtype": source.dtypes[0], "nodata": source.nodata, "compress": source.compression.value,
            "block": source.block_shapes[0], "count": source.count,
            "predictor": source.tags(ns="IMAGE_STRUCTURE").get("PREDICTOR"),
        }  # fmt: skip
        return source.read(1), profile


@pytest.mark.parametrize(
    ("dtype", "nodata", "predictor"), [("float32", -9999.0, "3"), ("int16", -32768, "2"), ("uint8", 0, "2")]
)
def test_a_tile_round_trips_through_its_geotiff(dtype: str, nodata: float, predictor: str) -> None:
    values = np.ma.array((np.arange(TILE_SIZE * TILE_SIZE).reshape(TILE_SIZE, TILE_SIZE) % 100 + 1).astype(dtype))
    values[10:20, 5:9] = np.ma.masked
    data = encode_tile(tile_image(values, TILE, nodata=nodata))
    read_back, profile = decode(data)
    assert profile["bounds"] == pytest.approx(tuple(TMS.xy_bounds(TILE)))
    assert profile["crs"].to_epsg() == 3857
    assert (profile["width"], profile["height"], profile["count"]) == (512, 512, 1)
    assert profile["dtype"] == dtype and profile["nodata"] == nodata
    assert profile["compress"] == "DEFLATE" and profile["block"] == (512, 512)
    assert 322 in tiff_tags(data) and 273 not in tiff_tags(data)  # tiles, not strips
    assert profile["predictor"] == predictor
    expected = values.filled(nodata)
    np.testing.assert_array_equal(read_back, expected)
    assert len(data) < expected.nbytes


def test_a_float_tile_without_nodata_gets_nan_and_an_integer_tile_without_holes_none() -> None:
    floats = np.ma.array(np.ones((TILE_SIZE, TILE_SIZE), "float64"))
    floats[0, 0] = np.ma.masked
    read_back, profile = decode(encode_tile(tile_image(floats, TILE, nodata=None)))
    assert np.isnan(profile["nodata"]) and np.isnan(read_back[0, 0]) and read_back[0, 1] == 1.0
    ints = np.ma.array(np.ones((TILE_SIZE, TILE_SIZE), "uint16"))
    assert decode(encode_tile(tile_image(ints, TILE, nodata=None)))[1]["nodata"] is None
    ints[0, 0] = np.ma.masked
    with pytest.raises(ValueError, match="nodata"):
        encode_tile(tile_image(ints, TILE, nodata=None))


def test_a_base_tile_encodes_to_the_bytes_of_its_own_values(tmp_path: Path) -> None:
    values = np.full((512, 512), 12, "int16")
    values[:, :100] = -32768
    image = read([cog(tmp_path / "a.tif", values, nodata=-32768)])
    assert image is not None
    read_back, profile = decode(encode_tile(image))
    np.testing.assert_array_equal(read_back, values)
    assert profile["nodata"] == -32768 and profile["bounds"] == pytest.approx(tuple(TMS.xy_bounds(TILE)))


def test_only_a_tile_of_512_px_in_web_mercator_is_encoded() -> None:
    small = tile_image(np.ma.array(np.ones((256, 256), "uint8")), TILE, nodata=0)
    with pytest.raises(ValueError, match="512"):
        encode_tile(small)
    image = tile_image(np.ma.array(np.ones((TILE_SIZE, TILE_SIZE), "uint8")), TILE, nodata=0)
    image.crs = rasterio.crs.CRS.from_epsg(4326)
    with pytest.raises(ValueError, match="3857"):
        encode_tile(image)


# --- the hash of a base tile and the levels


def item(item_id: str, updated: str | None = "2026-01-01T00:00:00Z") -> dict:
    return {"id": item_id, "properties": {} if updated is None else {"updated": updated}}


def test_the_hash_of_a_base_tile_is_stable_whatever_the_order_of_its_items() -> None:
    one = base_hash([item("a"), item("b", "2026-02-02T00:00:00Z")])
    assert one == base_hash([item("b", "2026-02-02T00:00:00Z"), item("a")])
    assert one == base_hash(iter([item("a"), item("b", "2026-02-02T00:00:00Z")]))
    assert len(one) == 64


def test_the_hash_changes_with_an_id_an_updated_or_another_item() -> None:
    base = base_hash([item("a"), item("b")])
    assert base != base_hash([item("a"), item("c")])
    assert base != base_hash([item("a"), item("b", "2026-03-03T00:00:00Z")])
    assert base != base_hash([item("a")])
    assert base_hash([item("ab", "c")]) != base_hash([item("a", "bc")])


def test_other_properties_of_an_item_do_not_change_the_hash() -> None:
    plain = item("a")
    noisy = {
        **item("a"),
        "assets": {"x": {"href": "https://example.org/a.tif"}},
        "properties": {"updated": "2026-01-01T00:00:00Z", "gsd": 30},
    }
    assert base_hash([plain]) == base_hash([noisy])


@pytest.mark.parametrize(
    "bad", [{"properties": {"updated": "x"}}, item("a", None), {"id": "", "properties": {"updated": "x"}}, {"id": "a"}]
)
def test_an_item_without_a_version_is_no_part_of_a_hash(bad: dict) -> None:
    with pytest.raises(ValueError):
        base_hash([item("ok"), bad])


@pytest.mark.parametrize(("min_zoom", "base"), [(7, 6), (5, 4), (1, 0)])
def test_the_pyramid_reaches_from_z0_to_one_below_min_zoom(min_zoom: int, base: int) -> None:
    assert base_zoom(min_zoom) == base
    assert levels(min_zoom) == tuple(range(base + 1))


@pytest.mark.parametrize("min_zoom", [0, -1, 26, 6.5, True, None])
def test_a_min_zoom_without_a_level_below_it_has_no_pyramid(min_zoom: object) -> None:
    with pytest.raises(ValueError):
        levels(min_zoom)  # type: ignore[arg-type]

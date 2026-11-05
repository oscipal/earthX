"""DS-03c: the classes of the merged scenes of an overpass inside an AOI, counted on synthetic classification COGs.

Every count is checked against a second one that shares nothing with the code under test but the files: the scenes are laid
over one another with plain numpy on the grid of the first one, the first valid value wins, and the pixel centres are tested
against the AOI as a UTM polygon with ``shapely.contains_xy``. No network, no checked-in raster.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy
import pytest
import rasterio
import shapely
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from shapely.geometry import Polygon

from earthx.access import aoi_clouds
from earthx.access.aoi_clouds import (
    MIN_AOI_PIXELS,
    aoi_clouds_cache_key,
    aoi_pass_cache_key,
    measure_aoi_clouds,
    measure_aoi_pass,
)
from earthx.readers.cog import AssetPath

CRS = "EPSG:32632"
ORIGIN_X, ORIGIN_Y = 500_000.0, 5_500_000.0
PIXEL = 20.0
SIZE = 512
CLOUDS = frozenset({8, 9, 10})
VEGETATION, CLOUD, WATER = 4, 8, 6

TO_LONLAT = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)


def _write(path: Path, data: numpy.ndarray, *, left: float = 0.0, crs: str = CRS, origin: tuple[float, float] | None = None) -> AssetPath:
    """A scene whose upper left corner lies ``left`` metres east of the common origin (or at ``origin`` in ``crs``)."""
    x, y = origin if origin is not None else (ORIGIN_X + left, ORIGIN_Y)
    profile = {
        "driver": "GTiff",
        "dtype": "uint8",
        "count": 1,
        "height": data.shape[0],
        "width": data.shape[1],
        "crs": crs,
        "transform": from_origin(x, y, PIXEL, PIXEL),
        "nodata": 0,
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
    }
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with rasterio.open(path, "w", **profile) as destination:
            destination.write(data, 1)
        with rasterio.open(path, "r+") as destination:
            destination.build_overviews([2, 4, 8, 16], Resampling.mode)
    return AssetPath(str(path), dataset_id="synthetic", item_id=path.stem, asset="scl")


def _filled(value: int, size: int = SIZE) -> numpy.ndarray:
    return numpy.full((size, size), value, dtype="uint8")


def _region(x: float, y: float, side: float) -> dict:
    """A square of ``side`` metres, its upper left corner ``x`` east and ``y`` south of the common origin, as GeoJSON."""
    corners = [(x, y), (x + side, y), (x + side, y + side), (x, y + side), (x, y)]
    ring = [list(TO_LONLAT.transform(ORIGIN_X + cx, ORIGIN_Y - cy)) for cx, cy in corners]
    return {"type": "Polygon", "coordinates": [ring]}


def _by_numpy(paths: list[AssetPath], aoi_utm: Polygon, level: int) -> tuple[int, int, dict[int, int]]:
    """The slow way: the first scene's grid at ``level``, each scene read back whole and laid over it, first valid wins."""
    first = rasterio.open(paths[0], overview_level=level - 1) if level else rasterio.open(paths[0])
    with first:
        transform, shape = first.transform, first.shape
    rows, cols = numpy.meshgrid(numpy.arange(shape[0]), numpy.arange(shape[1]), indexing="ij")
    x = transform.c + (cols + 0.5) * transform.a
    y = transform.f + (rows + 0.5) * transform.e
    inside = shapely.contains_xy(aoi_utm, x, y)
    merged = numpy.zeros(shape, dtype="uint8")
    for path in paths:
        with rasterio.open(path) as scene:
            # nearest neighbour at the cell centres, as the code under test warps
            col = numpy.floor((x - scene.transform.c) / scene.transform.a).astype(int)
            row = numpy.floor((y - scene.transform.f) / scene.transform.e).astype(int)
            on = (col >= 0) & (col < scene.width) & (row >= 0) & (row < scene.height)
            values = scene.read(1)[numpy.clip(row, 0, scene.height - 1), numpy.clip(col, 0, scene.width - 1)]
        fresh = (merged == 0) & on & (values != 0)
        merged[fresh] = values[fresh]
    valid = inside & (merged != 0)
    classes = {int(v): int((valid & (merged == v)).sum()) for v in numpy.unique(merged[valid]).tolist()}
    return int(valid.sum()), int(inside.sum()), classes


@pytest.fixture
def pair(tmp_path: Path) -> list[AssetPath]:
    """Two scenes side by side that overlap by half: the first is cloud, the second vegetation."""
    return [
        _write(tmp_path / "a.tif", _filled(CLOUD)),
        _write(tmp_path / "b.tif", _filled(VEGETATION), left=SIZE * PIXEL / 2),
    ]


class TestTheMerge:
    def test_a_place_in_an_overlap_counts_once_for_the_first_scene(self, pair: list[AssetPath]) -> None:
        """The AOI lies half on a alone, half in the overlap of a and b: b adds nothing there."""
        aoi = _region(2_000, 1_000, 6_000)
        counts = measure_aoi_pass(pair, aoi, CLOUDS)
        assert counts.class_pixels == {CLOUD: counts.data_pixels}
        assert counts.data_pixels == counts.aoi_pixels

    def test_the_other_order_gives_the_other_scene_in_the_overlap(self, pair: list[AssetPath]) -> None:
        """Gegenprobe: the order of the mosaic decides who owns an overlap, and nothing else changes."""
        aoi = _region(2_000, 1_000, 6_000)
        forward = measure_aoi_pass(pair, aoi, CLOUDS)
        backward = measure_aoi_pass(pair[::-1], aoi, CLOUDS)
        assert forward.data_pixels == backward.data_pixels
        assert forward.class_pixels == {CLOUD: forward.data_pixels}
        # b first: b owns its whole extent (from 5 120 m east), a only the part west of it
        assert set(backward.class_pixels) == {CLOUD, VEGETATION}
        assert backward.class_pixels[VEGETATION] > 0 and backward.class_pixels[CLOUD] > 0

    def test_an_overlap_is_not_counted_twice(self, pair: list[AssetPath]) -> None:
        """The counts of the separate scenes add up to more than the pass has; the pass counts each place once."""
        aoi = _region(2_000, 1_000, 8_000)
        merged = measure_aoi_pass(pair, aoi, CLOUDS)
        separate = sum(measure_aoi_clouds(path, aoi, CLOUDS).data_pixels for path in pair)
        assert separate > merged.data_pixels
        assert merged.data_pixels <= merged.aoi_pixels

    def test_it_equals_a_count_with_numpy(self, pair: list[AssetPath]) -> None:
        aoi = _region(2_000, 1_000, 8_000)
        counts = measure_aoi_pass(pair, aoi, CLOUDS)
        level = [2, 4, 8, 16].index(round(counts.resolution / PIXEL)) + 1
        polygon = shapely.geometry.shape(
            {"type": "Polygon", "coordinates": [[list(Transformer.from_crs("EPSG:4326", CRS, always_xy=True).transform(*p)) for p in aoi["coordinates"][0]]]}
        )
        data, inside, classes = _by_numpy(pair, polygon, level)
        assert (counts.data_pixels, counts.aoi_pixels, dict(counts.class_pixels)) == (data, inside, classes)

    def test_two_scenes_apart_add_up(self, tmp_path: Path) -> None:
        """No overlap: the pass is the sum of its scenes, class by class."""
        one = _write(tmp_path / "one.tif", _filled(WATER))
        two = _write(tmp_path / "two.tif", _filled(VEGETATION), left=SIZE * PIXEL)
        aoi = _region(6_000, 500, 8_000)  # across the seam at 10 240 m
        counts = measure_aoi_pass([one, two], aoi, CLOUDS)
        assert set(counts.class_pixels) == {WATER, VEGETATION}
        separate = [measure_aoi_clouds(path, aoi, CLOUDS) for path in (one, two)]
        assert counts.data_pixels == counts.aoi_pixels
        # in the pixels of the pass's own level, the scenes' shares of the area are the ones the seam makes
        assert counts.class_pixels[WATER] / counts.data_pixels == pytest.approx(4_240 / 8_000, abs=0.02)
        assert sum(m.data_pixels * m.resolution**2 for m in separate) == pytest.approx(
            counts.data_pixels * counts.resolution**2, rel=0.05
        )

    def test_where_the_first_scene_has_no_data_the_next_one_gives_the_pixel(self, tmp_path: Path) -> None:
        holed = _filled(CLOUD)
        holed[:, :256] = 0
        a = _write(tmp_path / "a.tif", holed)
        b = _write(tmp_path / "b.tif", _filled(WATER))
        counts = measure_aoi_pass([a, b], _region(1_000, 1_000, 8_000), CLOUDS)
        assert set(counts.class_pixels) == {WATER, CLOUD}

    def test_the_part_of_the_aoi_no_scene_covers_is_without_data(self, pair: list[AssetPath]) -> None:
        aoi = _region(-6_000, 1_000, 8_000)  # 6 km west of the scenes
        counts = measure_aoi_pass(pair, aoi, CLOUDS)
        assert 0 < counts.data_pixels < counts.aoi_pixels

    def test_an_aoi_off_the_scenes_has_no_data_at_all(self, pair: list[AssetPath]) -> None:
        counts = measure_aoi_pass(pair, _region(-50_000, 1_000, 8_000), CLOUDS)
        assert counts.data_pixels == 0 and counts.aoi_pixels > 0 and counts.class_pixels == {}

    def test_scenes_in_two_zones_are_laid_on_the_grid_of_the_first(self, tmp_path: Path) -> None:
        """Zone 33 starts east of 12°E; the same ground read in the other CRS lands on the same cells."""
        to_33 = Transformer.from_crs(CRS, "EPSG:32633", always_xy=True)
        x33, y33 = to_33.transform(ORIGIN_X + 5_000, ORIGIN_Y)
        a = _write(tmp_path / "a.tif", _filled(CLOUD))
        b = _write(tmp_path / "b.tif", _filled(WATER), crs="EPSG:32633", origin=(round(x33), round(y33)))
        counts = measure_aoi_pass([b, a], _region(3_000, 1_000, 6_000), CLOUDS)
        assert set(counts.class_pixels) == {CLOUD, WATER}  # b is laid first and owns what it covers; a fills the rest
        assert counts.data_pixels > 0.9 * counts.aoi_pixels

    def test_a_read_in_chunks_is_the_same_as_in_one(self, pair: list[AssetPath], monkeypatch: pytest.MonkeyPatch) -> None:
        aoi = _region(1_000, 1_000, 9_000)
        whole = measure_aoi_pass(pair, aoi, CLOUDS)
        monkeypatch.setattr(aoi_clouds, "PASS_CHUNK", 16)
        assert measure_aoi_pass(pair, aoi, CLOUDS) == whole

    def test_cloud_pixels_are_the_classes_asked(self, pair: list[AssetPath]) -> None:
        counts = measure_aoi_pass(pair, _region(2_000, 1_000, 6_000), CLOUDS)
        assert counts.cloud_pixels == counts.class_pixels.get(CLOUD, 0)
        assert measure_aoi_pass(pair, _region(2_000, 1_000, 6_000), frozenset({VEGETATION})).cloud_pixels == 0

    def test_the_level_follows_the_pixels_of_the_aoi_on_the_scenes(self, pair: list[AssetPath]) -> None:
        small = measure_aoi_pass(pair, _region(2_000, 1_000, 1_500), CLOUDS)
        large = measure_aoi_pass(pair, _region(1_000, 1_000, 9_000), CLOUDS)
        assert small.resolution <= large.resolution
        assert small.aoi_pixels >= MIN_AOI_PIXELS or small.resolution == PIXEL


class TestRefusals:
    def test_a_plain_string_is_not_a_path(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "a.tif", _filled(CLOUD))
        with pytest.raises(TypeError, match="gateway cleared"):
            measure_aoi_pass([str(path)], _region(1_000, 1_000, 2_000), CLOUDS)  # type: ignore[list-item]

    def test_no_scene_is_a_type_error(self) -> None:
        with pytest.raises(TypeError):
            measure_aoi_pass([], _region(1_000, 1_000, 2_000), CLOUDS)

    @pytest.mark.parametrize("aoi", [{"type": "Point", "coordinates": [10, 47]}, {}, None, "x"])
    def test_an_aoi_that_is_not_an_area(self, tmp_path: Path, aoi: object) -> None:
        path = _write(tmp_path / "a.tif", _filled(CLOUD))
        with pytest.raises(ValueError, match="Polygon or MultiPolygon"):
            measure_aoi_pass([path], aoi, CLOUDS)  # type: ignore[arg-type]

    def test_a_self_crossing_ring_names_no_coordinate(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "a.tif", _filled(CLOUD))
        bow = {"type": "Polygon", "coordinates": [[[10.0, 47.0], [10.1, 47.1], [10.1, 47.0], [10.0, 47.1], [10.0, 47.0]]]}
        with pytest.raises(ValueError) as caught:
            measure_aoi_pass([path], bow, CLOUDS)
        assert "10." not in str(caught.value) and "47." not in str(caught.value)


class TestTheKeys:
    def test_the_key_of_a_pass_is_the_set_of_its_scenes(self) -> None:
        aoi = _region(0, 0, 1_000)
        one = aoi_pass_cache_key("d", ["b", "a"], "scl", CLOUDS, aoi)
        assert one == aoi_pass_cache_key("d", ["a", "b"], "scl", CLOUDS, aoi)
        assert one != aoi_pass_cache_key("d", ["a", "c"], "scl", CLOUDS, aoi)
        assert one != aoi_pass_cache_key("d", ["a"], "scl", CLOUDS, aoi)
        assert one != aoi_pass_cache_key("d", ["a", "b"], "scl", CLOUDS, _region(0, 0, 2_000))

    def test_a_pass_and_a_scene_never_share_a_key(self) -> None:
        aoi = _region(0, 0, 1_000)
        assert aoi_pass_cache_key("d", ["a"], "scl", CLOUDS, aoi) != aoi_clouds_cache_key("d", "a", "scl", CLOUDS, aoi)

    def test_the_key_names_no_coordinate(self) -> None:
        key = aoi_pass_cache_key("d", ["a"], "scl", CLOUDS, _region(0, 0, 1_000))
        assert len(key) == 64 and key.isalnum()

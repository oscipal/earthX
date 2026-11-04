"""DS-03 plan §6.19: the cloud share in an AOI, counted on synthetic classification COGs.

Every count is checked against a second one that shares nothing with the code under test but the file: the
pixel centres of the level are placed with the level's own transform and tested against the AOI as a UTM polygon
with ``shapely.contains_xy``, on the array read back from the file. No network, no checked-in raster.
"""

from __future__ import annotations

import math
import warnings
from pathlib import Path

import numpy
import pytest
import rasterio
import shapely
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from shapely.geometry import MultiPolygon, Polygon

import earthx
from earthx.access.aoi_clouds import (
    MIN_AOI_PIXELS,
    AoiClouds,
    aoi_clouds_cache_key,
    measure_aoi_clouds,
    overview_factor,
)
from earthx.api.aoi_cloud_filter import SceneMeasure
from earthx.readers.cog import AssetPath

CRS = "EPSG:32632"
ORIGIN_X, ORIGIN_Y = 500_000.0, 5_500_000.0
PIXEL = 20.0
SIZE = 1024
FACTORS = [2, 4, 8, 16]
CLOUDS = frozenset({8, 9, 10})
#: The classes of an SCL without 0 (no data) and 2 (cast shadows, left out for brevity).
CLASSES = numpy.array([1, 3, 4, 5, 6, 7, 8, 9, 10, 11], dtype="uint8")

TO_LONLAT = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)


def _write(
    path: Path, data: numpy.ndarray, *, nodata: int | None = 0, crs: str | None = CRS, overviews=FACTORS
) -> Path:
    profile = {
        "driver": "GTiff",
        "dtype": "uint8",
        "count": 1,
        "height": data.shape[0],
        "width": data.shape[1],
        "crs": crs,
        "transform": from_origin(ORIGIN_X, ORIGIN_Y, PIXEL, PIXEL),
        "nodata": nodata,
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
    }
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with rasterio.open(path, "w", **profile) as destination:
            destination.write(data, 1)
        if overviews:
            with rasterio.open(path, "r+") as destination:
                destination.build_overviews(overviews, Resampling.mode)
    return path


def _scene() -> numpy.ndarray:
    """Blocks of 16 pixels with a class each, a no-data corner and a no-data strip along the right edge."""
    rng = numpy.random.default_rng(seed=20261029)
    blocks = rng.choice(CLASSES, size=(SIZE // 16, SIZE // 16))
    data = numpy.kron(blocks, numpy.ones((16, 16), dtype="uint8")).astype("uint8")
    data[:200, :300] = 0
    data[:, 1000:] = 0
    return data


@pytest.fixture(scope="module")
def scene(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _write(tmp_path_factory.mktemp("aoi-clouds") / "scl.tif", _scene())


def _cleared(path: Path) -> AssetPath:
    """The local file as the path a gateway check hands out; the check itself is the readers' to test."""
    return AssetPath(str(path), dataset_id="synthetic", item_id="scene", asset="scl")


def _at(x: float, y: float) -> tuple[float, float]:
    """The UTM position ``x`` metres east and ``y`` metres south of the scene's upper left corner."""
    return ORIGIN_X + x, ORIGIN_Y - y


def _polygon(*corners: tuple[float, float]) -> Polygon:
    return Polygon(corners)


def _square(x: float, y: float, side: float) -> Polygon:
    """A square of ``side`` metres with its lower left corner ``x`` and ``y`` metres from the scene's upper left."""
    left, top = _at(x, y)
    return _polygon((left, top), (left + side, top), (left + side, top - side), (left, top - side))


def _geojson(polygon: Polygon | MultiPolygon) -> dict:
    """The polygon, given in UTM, as GeoJSON in EPSG:4326."""

    def ring(coordinates) -> list[list[float]]:
        return [list(TO_LONLAT.transform(x, y)) for x, y in coordinates]

    if isinstance(polygon, MultiPolygon):
        return {"type": "MultiPolygon", "coordinates": [[ring(part.exterior.coords)] for part in polygon.geoms]}
    return {"type": "Polygon", "coordinates": [ring(polygon.exterior.coords)]}


def _expected(path: Path, region, classes=CLOUDS, overview_level: int | None = None) -> AoiClouds:
    """The count the slow, plain way: every pixel centre around the region, the ones past the raster included."""
    options = {} if overview_level is None else {"overview_level": overview_level}
    with rasterio.open(path, **options) as level:
        array, nodata, transform = level.read(1), level.nodata, level.transform
    minx, miny, maxx, maxy = region.bounds
    first_col = math.floor((minx - transform.c) / transform.a) - 2
    last_col = math.ceil((maxx - transform.c) / transform.a) + 2
    first_row = math.floor((maxy - transform.f) / transform.e) - 2
    last_row = math.ceil((miny - transform.f) / transform.e) + 2
    rows, cols = numpy.meshgrid(numpy.arange(first_row, last_row), numpy.arange(first_col, last_col), indexing="ij")
    inside = shapely.contains_xy(
        region, transform.c + (cols + 0.5) * transform.a, transform.f + (rows + 0.5) * transform.e
    )
    on_raster = (rows >= 0) & (rows < array.shape[0]) & (cols >= 0) & (cols < array.shape[1])
    values = array[numpy.clip(rows, 0, array.shape[0] - 1), numpy.clip(cols, 0, array.shape[1] - 1)]
    valid = inside & on_raster & ((values != nodata) if nodata is not None else True)
    return AoiClouds(
        cloud_pixels=int((valid & numpy.isin(values, sorted(classes))).sum()),
        data_pixels=int(valid.sum()),
        aoi_pixels=int(inside.sum()),
        resolution=abs(transform.a),
    )


class TestOverviewFactor:
    @pytest.mark.parametrize(
        ("pixels", "expected"),
        [
            (0, 1),
            (9_999, 1),
            (39_999, 1),
            (40_000, 2),
            (159_999, 2),
            (160_000, 4),
            (639_999, 4),
            (640_000, 8),
            (2_559_999, 8),
            (2_560_000, 16),
            (10**12, 16),
        ],
    )
    def test_the_coarsest_level_that_keeps_ten_thousand_pixels(self, pixels: float, expected: int) -> None:
        assert overview_factor(pixels, FACTORS) == expected

    def test_it_is_one_of_the_levels_the_file_has(self) -> None:
        assert overview_factor(10**9, [2, 4]) == 4
        assert overview_factor(10**9, []) == 1
        assert overview_factor(10**9, [4, 2]) == 4

    def test_the_limit_can_be_given(self) -> None:
        assert overview_factor(1_000, FACTORS, min_pixels=250) == 2
        assert MIN_AOI_PIXELS == 10_000

    def test_a_factor_of_one_or_less_is_no_overview(self) -> None:
        assert overview_factor(10**9, [1, 0, -2]) == 1

    def test_a_limit_below_one_is_refused(self) -> None:
        with pytest.raises(ValueError, match="at least 1"):
            overview_factor(100, FACTORS, min_pixels=0)


class TestTheCount:
    def test_on_the_full_resolution_against_a_count_with_numpy(self, scene: Path) -> None:
        region = _polygon(_at(3_300.5, 4_100.5), _at(4_900.5, 4_300.5), _at(5_300.5, 5_700.5), _at(3_900.5, 6_000.5))
        measured = measure_aoi_clouds(_cleared(scene), _geojson(region), CLOUDS)
        expected = _expected(scene, region)
        assert measured == expected
        assert measured.resolution == 20.0
        assert 0 < measured.cloud_pixels < measured.data_pixels

    def test_on_an_overview_against_a_count_on_the_level_read_back(self, scene: Path) -> None:
        region = _square(6_000.5, 6_000.5, 10_000)
        measured = measure_aoi_clouds(_cleared(scene), _geojson(region), CLOUDS)
        expected = _expected(scene, region, overview_level=FACTORS.index(4))
        assert measured == expected
        assert measured.resolution == 80.0
        assert 0 < measured.cloud_pixels < measured.data_pixels

    def test_the_level_follows_the_area_at_the_limit(self, scene: Path) -> None:
        # 199 × 199 native pixels are 39 601, 201 × 201 are 40 401: either side of the 40 000 that leave 10 000 at 2.
        under = measure_aoi_clouds(_cleared(scene), _geojson(_square(5_000.5, 5_000.5, 199 * PIXEL)), CLOUDS)
        over = measure_aoi_clouds(_cleared(scene), _geojson(_square(5_000.5, 5_000.5, 201 * PIXEL)), CLOUDS)
        assert (under.resolution, over.resolution) == (20.0, 40.0)

    def test_a_file_without_overviews_is_read_as_it_is(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "plain.tif", _scene(), overviews=[])
        region = _square(2_000.5, 8_000.5, 12_000)
        assert measure_aoi_clouds(_cleared(path), _geojson(region), CLOUDS) == _expected(path, region)

    def test_a_rectangle_given_as_a_polygon(self, scene: Path) -> None:
        west, south = TO_LONLAT.transform(ORIGIN_X + 8_000.5, ORIGIN_Y - 9_000.5)
        east, north = TO_LONLAT.transform(ORIGIN_X + 9_500.5, ORIGIN_Y - 7_500.5)
        aoi = {
            "type": "Polygon",
            "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]],
        }
        corners = [TO_LONLAT.transform(*c, direction="INVERSE") for c in aoi["coordinates"][0]]
        measured = measure_aoi_clouds(_cleared(scene), aoi, CLOUDS)
        assert measured == _expected(scene, Polygon(corners))
        assert measured.data_pixels > 0

    def test_a_multipolygon(self, scene: Path) -> None:
        first, second = _square(3_500.5, 4_500.5, 1_500), _square(9_000.5, 11_000.5, 2_000)
        measured = measure_aoi_clouds(_cleared(scene), _geojson(MultiPolygon([first, second])), CLOUDS)
        assert measured == _expected(scene, MultiPolygon([first, second]))
        single = measure_aoi_clouds(_cleared(scene), _geojson(first), CLOUDS)
        assert measured.aoi_pixels > single.aoi_pixels

    def test_an_aoi_with_a_hole_leaves_the_hole_out(self, scene: Path) -> None:
        outer, hole = _square(4_000.5, 4_000.5, 2_000), _square(4_500.5, 4_500.5, 1_000)
        region = Polygon(outer.exterior.coords, [hole.exterior.coords])
        aoi = _geojson(outer)
        aoi["coordinates"].append([list(TO_LONLAT.transform(x, y)) for x, y in hole.exterior.coords])
        assert measure_aoi_clouds(_cleared(scene), aoi, CLOUDS) == _expected(scene, region)

    def test_only_the_cloud_classes_given_count(self, scene: Path) -> None:
        aoi = _geojson(_square(5_000.5, 5_000.5, 2_000))
        all_three = measure_aoi_clouds(_cleared(scene), aoi, CLOUDS)
        only_nine = measure_aoi_clouds(_cleared(scene), aoi, frozenset({9}))
        none = measure_aoi_clouds(_cleared(scene), aoi, frozenset())
        assert none.cloud_pixels == 0 and none.cloud_percent == 0.0
        assert only_nine.cloud_pixels < all_three.cloud_pixels
        assert none.data_pixels == only_nine.data_pixels == all_three.data_pixels

    def test_an_aoi_of_20_000_positions(self, scene: Path) -> None:
        angles = numpy.linspace(0, 2 * numpy.pi, 20_000, endpoint=False)
        centre_x, centre_y = ORIGIN_X + 10_000.3, ORIGIN_Y - 10_000.7
        ring = [(centre_x + 1_800 * numpy.cos(a), centre_y + 1_300 * numpy.sin(a)) for a in angles]
        region = Polygon(ring)
        aoi = _geojson(region)
        assert len(aoi["coordinates"][0]) == 20_001
        assert measure_aoi_clouds(_cleared(scene), aoi, CLOUDS) == _expected(scene, region)


class TestTheEdges:
    """The part of an AOI past the raster has no data; it joins ``aoi_pixels`` by its area, not pixel by pixel."""

    @staticmethod
    def _matches(measured: AoiClouds, expected: AoiClouds, region) -> None:
        assert (measured.cloud_pixels, measured.data_pixels, measured.resolution) == (
            expected.cloud_pixels,
            expected.data_pixels,
            expected.resolution,
        )
        # Counted by area rather than by pixel centres, the pixels past the edge differ by at most a row of them.
        assert abs(measured.aoi_pixels - expected.aoi_pixels) <= region.length / expected.resolution

    def test_an_aoi_partly_outside_the_raster_counts_the_rest_as_no_data(self, scene: Path) -> None:
        east = SIZE * PIXEL
        region = _square(east - 500.5, 9_000.5, 1_000)
        measured = measure_aoi_clouds(_cleared(scene), _geojson(region), CLOUDS)
        self._matches(measured, _expected(scene, region), region)
        assert measured.aoi_pixels > measured.data_pixels
        assert measured.data_percent < 100

    def test_an_aoi_past_the_top_edge(self, scene: Path) -> None:
        region = _square(12_000.5, -500.5, 1_000)
        measured = measure_aoi_clouds(_cleared(scene), _geojson(region), CLOUDS)
        self._matches(measured, _expected(scene, region), region)
        assert 0 < measured.data_pixels < measured.aoi_pixels

    def test_the_part_on_the_raster_picks_the_level(self, scene: Path) -> None:
        # 10 x 10 km reaching past the east and the south edge: under 160 000 pixels of 20 m lie on the raster, so
        # 40 m (at least 10 000 of them); the whole square, 250 000 pixels, would have been read at 80 m.
        region = _square(SIZE * PIXEL - 5_000.5, 12_000.5, 10_000)
        measured = measure_aoi_clouds(_cleared(scene), _geojson(region), CLOUDS)
        self._matches(measured, _expected(scene, region, overview_level=FACTORS.index(2)), region)
        assert measured.resolution == 40.0

    def test_an_aoi_far_larger_than_the_raster_masks_no_more_than_the_raster(self, scene: Path) -> None:
        # About 2 000 km across against a scene of 20 km: the part past the raster is never laid out as pixels,
        # and the level follows the scene's own 1 Mi pixels (160 m keeps 16 384 of them).
        region = _square(-1_000_000.5, -1_000_000.5, 2_000_000)
        measured = measure_aoi_clouds(_cleared(scene), _geojson(region), CLOUDS)
        with rasterio.open(scene, overview_level=FACTORS.index(8)) as level:
            values = level.read(1)
        assert measured.resolution == 8 * PIXEL
        assert measured.data_pixels == int((values != 0).sum())
        assert measured.cloud_pixels == int(numpy.isin(values, sorted(CLOUDS)).sum())
        assert measured.data_percent < 1

    def test_only_the_blocks_the_aoi_touches_are_read(self, scene: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Two squares of 300 m in opposite corners: 450 pixels, so 20 m, where the box around them is the whole
        # scene of 16 blocks. Only the two blocks under the squares are masked and read.
        from earthx.access import aoi_clouds

        masked: list[tuple[int, int]] = []
        real = aoi_clouds.geometry_mask

        def counting(shapes, *, out_shape, **options):
            masked.append(out_shape)
            return real(shapes, out_shape=out_shape, **options)

        monkeypatch.setattr(aoi_clouds, "geometry_mask", counting)
        far = SIZE * PIXEL - 1_300.5
        region = MultiPolygon([_square(1_000.5, 1_000.5, 300), _square(far, far, 300)])
        measured = measure_aoi_clouds(_cleared(scene), _geojson(region), CLOUDS)
        assert measured == _expected(scene, region)
        assert len(masked) == 2

    def test_an_aoi_entirely_outside_has_pixels_and_no_data(self, scene: Path) -> None:
        measured = measure_aoi_clouds(_cleared(scene), _geojson(_square(-5_000.5, 3_000.5, 1_000)), CLOUDS)
        assert measured.aoi_pixels > 0 and measured.data_pixels == 0 and measured.cloud_pixels == 0
        assert measured.cloud_percent is None and measured.data_percent == 0.0

    def test_an_aoi_entirely_in_no_data_has_no_value(self, scene: Path) -> None:
        # The upper left corner of the scene (200 rows by 300 columns of class 0).
        measured = measure_aoi_clouds(_cleared(scene), _geojson(_square(1_000.5, 1_000.5, 1_000)), CLOUDS)
        assert measured.aoi_pixels > 0 and measured.data_pixels == 0
        assert measured.cloud_percent is None and measured.data_percent == 0.0

    def test_class_one_stays_in_the_denominator(self, tmp_path: Path) -> None:
        data = numpy.full((256, 256), 9, dtype="uint8")
        data[:, :128] = 1
        path = _write(tmp_path / "half.tif", data)
        # 100 × 100 pixels with the edge between the classes in the middle; an edge of pixels, so no centre is on it.
        measured = measure_aoi_clouds(_cleared(path), _geojson(_square(78 * PIXEL, 78 * PIXEL, 100 * PIXEL)), CLOUDS)
        assert (measured.cloud_pixels, measured.data_pixels, measured.aoi_pixels) == (5_000, 10_000, 10_000)
        assert measured.cloud_percent == 50.0 and measured.data_percent == 100.0

    def test_a_file_without_nodata_counts_every_pixel_in_the_raster(self, tmp_path: Path) -> None:
        data = numpy.zeros((256, 256), dtype="uint8")
        data[:, 128:] = 8
        path = _write(tmp_path / "plain.tif", data, nodata=None)
        measured = measure_aoi_clouds(_cleared(path), _geojson(_square(78 * PIXEL, 78 * PIXEL, 100 * PIXEL)), CLOUDS)
        assert (measured.cloud_pixels, measured.data_pixels) == (5_000, 10_000)

    def test_a_float_nodata_of_nan(self, tmp_path: Path) -> None:
        path = tmp_path / "float.tif"
        data = numpy.full((256, 256), 9.0, dtype="float32")
        data[:, :128] = numpy.nan
        with rasterio.open(
            path, "w", driver="GTiff", dtype="float32", count=1, height=256, width=256, crs=CRS,
            transform=from_origin(ORIGIN_X, ORIGIN_Y, PIXEL, PIXEL), nodata=float("nan"),
        ) as destination:  # fmt: skip
            destination.write(data, 1)
        measured = measure_aoi_clouds(_cleared(path), _geojson(_square(78 * PIXEL, 78 * PIXEL, 100 * PIXEL)), CLOUDS)
        assert (measured.cloud_pixels, measured.data_pixels, measured.aoi_pixels) == (5_000, 5_000, 10_000)
        assert measured.cloud_percent == 100.0 and measured.data_percent == 50.0


class TestRefusals:
    @pytest.mark.parametrize(
        "aoi",
        [
            {"type": "Point", "coordinates": [10.0, 50.0]},
            {"type": "LineString", "coordinates": [[10.0, 50.0], [10.1, 50.1]]},
            {"type": "MultiPoint", "coordinates": [[10.0, 50.0]]},
            {"type": "GeometryCollection", "geometries": []},
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [10.0, 50.0]}},
            {"coordinates": [[[10.0, 50.0]]]},
            {},
            [[10.0, 50.0]],
            None,
            "Polygon",
        ],
    )
    def test_what_is_not_an_area_names_no_coordinate(self, scene: Path, aoi) -> None:
        with pytest.raises(ValueError, match="Polygon or MultiPolygon") as caught:
            measure_aoi_clouds(_cleared(scene), aoi, CLOUDS)
        assert not any(char.isdigit() for char in str(caught.value))

    @pytest.mark.parametrize(
        "coordinates",
        [
            [],
            [[]],
            [[["10.0", "50.0"], ["10.1", "50.1"], ["10.2", "50.05"], ["10.0", "50.0"]]],
            [[[10.0, 50.0], [10.1, 50.1]]],
            [[[float("nan"), 50.0], [9.5, 49.6], [9.6, 49.5], [float("nan"), 50.0]]],
            [[[float("inf"), 50.0], [9.5, 49.6], [9.6, 49.5], [float("inf"), 50.0]]],
            [10.0, 50.0],
        ],
    )
    def test_a_polygon_that_cannot_be_placed_names_no_coordinate(self, scene: Path, coordinates) -> None:
        with pytest.raises(ValueError) as caught:
            measure_aoi_clouds(_cleared(scene), {"type": "Polygon", "coordinates": coordinates}, CLOUDS)
        assert not any(char.isdigit() for char in str(caught.value))

    @pytest.mark.parametrize(
        "region",
        [
            # A ring that crosses itself, lopsided so that it keeps an area, and two parts that overlap.
            _polygon(_at(3_000.5, 3_000.5), _at(5_000.5, 5_000.5), _at(5_000.5, 3_000.5), _at(3_000.5, 6_000.5)),
            MultiPolygon([_square(3_000.5, 3_000.5, 2_000), _square(4_000.5, 4_000.5, 2_000)]),
        ],
        ids=["bowtie", "overlapping-parts"],
    )
    def test_an_invalid_polygon_names_no_coordinate(self, scene: Path, region) -> None:
        with pytest.raises(ValueError, match="valid polygon") as caught:
            measure_aoi_clouds(_cleared(scene), _geojson(region), CLOUDS)
        assert not any(char.isdigit() for char in str(caught.value))

    def test_a_plain_path_is_refused(self, scene: Path) -> None:
        with pytest.raises(TypeError, match="gateway cleared"):
            measure_aoi_clouds(str(scene), _geojson(_square(1_000.5, 1_000.5, 1_000)), CLOUDS)

    def test_a_raster_without_a_crs(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "bare.tif", _scene(), crs=None, overviews=[])
        with pytest.raises(ValueError, match="no CRS"):
            measure_aoi_clouds(_cleared(path), _geojson(_square(1_000.5, 1_000.5, 1_000)), CLOUDS)

    def test_a_file_that_is_not_there_is_the_readers_error(self, tmp_path: Path) -> None:
        with pytest.raises(rasterio.errors.RasterioIOError):
            measure_aoi_clouds(_cleared(tmp_path / "gone.tif"), _geojson(_square(1_000.5, 1_000.5, 1_000)), CLOUDS)


class TestTheNumbers:
    def test_the_percentages_have_one_decimal(self) -> None:
        counted = AoiClouds(cloud_pixels=1, data_pixels=3, aoi_pixels=7, resolution=20.0)
        assert counted.cloud_percent == 33.3
        assert counted.data_percent == 42.9

    def test_no_valid_pixel_is_no_value_and_no_pixel_is_no_data(self) -> None:
        assert AoiClouds(0, 0, 100, 20.0).cloud_percent is None
        assert AoiClouds(0, 0, 100, 20.0).data_percent == 0.0
        assert AoiClouds(0, 0, 0, 20.0).data_percent == 0.0

    def test_the_measure_is_what_goes_on_the_item(self) -> None:
        assert AoiClouds(25, 50, 200, 80.0).as_measure() == {
            "data_percent": 25.0,
            "cloud_pixels": 25,
            "data_pixels": 50,
            "resolution": 80.0,
        }

    def test_it_is_a_value(self) -> None:
        counted = AoiClouds(1, 2, 3, 20.0)
        assert counted == AoiClouds(1, 2, 3, 20.0)
        with pytest.raises(AttributeError):
            counted.cloud_pixels = 5  # type: ignore[misc]



def _nodata_expected(path: Path, region, overview_level: int | None = None) -> tuple[float, float]:
    """The share of the AOI without a valid pixel, from the independent count of ``_expected``, and the most that the
    share may differ where the part past the raster's edge is counted by its area and not pixel by pixel."""
    counted = _expected(path, region, overview_level=overview_level)
    share = 100 * (counted.aoi_pixels - counted.data_pixels) / counted.aoi_pixels
    row_of_pixels = 100 * (region.length / counted.resolution) / counted.aoi_pixels
    return share, row_of_pixels


def _nodata_of(path: Path, region) -> float:
    return SceneMeasure.of(measure_aoi_clouds(_cleared(path), _geojson(region), CLOUDS)).nodata_percent


class TestTheNoDataShareInTheAoi:
    """DS-03, Otto 31.10.2026: no data in the AOI is 100 less ``data_percent`` of the one reading the cloud share
    comes from. Each value is checked against the independent count of ``_expected`` (class 0 is the file's nodata)."""

    def test_an_aoi_over_the_no_data_corner_against_an_independent_count(self, scene: Path) -> None:
        region = _square(4_000.5, 2_500.5, 3_000)  # rows 125..275 and columns 200..350: the corner is class 0
        share, _ = _nodata_expected(scene, region)
        assert 0 < share < 100
        assert _nodata_of(scene, region) == pytest.approx(share, abs=0.1)

    def test_an_aoi_on_an_overview_against_the_count_on_the_level_read_back(self, scene: Path) -> None:
        region = _square(2_000.5, 1_000.5, 12_000)  # reaches the corner and the strip at the right edge
        share, _ = _nodata_expected(scene, region, overview_level=FACTORS.index(4))
        assert 0 < share < 100
        assert _nodata_of(scene, region) == pytest.approx(share, abs=0.1)

    def test_an_aoi_past_the_south_edge_counts_what_lies_past_it_as_no_data(self, scene: Path) -> None:
        region = _square(8_000.5, SIZE * PIXEL - 500.5, 1_000)  # the south half lies past the raster
        share, row = _nodata_expected(scene, region)
        assert 45 < share < 55
        assert _nodata_of(scene, region) == pytest.approx(share, abs=row + 0.1)

    def test_a_scene_without_a_valid_pixel_in_the_aoi_is_measurable_with_100(self, scene: Path) -> None:
        in_the_corner = _square(1_000.5, 1_000.5, 1_000)
        counted = measure_aoi_clouds(_cleared(scene), _geojson(in_the_corner), CLOUDS)
        assert counted.data_pixels == 0
        measure = SceneMeasure.of(counted)
        assert measure.nodata_percent == 100.0 and measure.cloud_percent is None, "the cloud share has no value"
        outside = SceneMeasure.of(measure_aoi_clouds(_cleared(scene), _geojson(_square(-5_000.5, 3_000.5, 1_000)), CLOUDS))
        assert outside.nodata_percent == 100.0 and outside.cloud_percent is None

    def test_a_scene_valid_everywhere_in_the_aoi_has_0(self, tmp_path: Path) -> None:
        data = numpy.full((256, 256), 9, dtype="uint8")
        data[:, :128] = 1  # class 1 is a valid pixel
        path = _write(tmp_path / "half.tif", data)
        region = _square(78 * PIXEL, 78 * PIXEL, 100 * PIXEL)
        assert _expected(path, region).data_pixels == _expected(path, region).aoi_pixels == 10_000
        assert _nodata_of(path, region) == 0.0

    def test_a_file_without_nodata_has_none_inside_the_raster_only(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "plain.tif", numpy.zeros((256, 256), dtype="uint8"), nodata=None)
        assert _nodata_of(path, _square(78 * PIXEL, 78 * PIXEL, 100 * PIXEL)) == 0.0
        half_out = _square(-50 * PIXEL, 78 * PIXEL, 100 * PIXEL)
        share, row = _nodata_expected(path, half_out)
        assert 45 < share < 55
        assert _nodata_of(path, half_out) == pytest.approx(share, abs=row + 0.1)

    def test_it_is_derived_from_the_numbers_the_cache_keeps(self, scene: Path) -> None:
        """The cache holds ``as_measure()``; the value from it equals the value of the reading itself, so the cache needs
        neither another key nor another number."""
        regions = [
            _square(4_000.5, 2_500.5, 3_000),
            _square(8_000.5, SIZE * PIXEL - 500.5, 1_000),
            _square(1_000.5, 1_000.5, 1_000),
            _square(2_000.5, 1_000.5, 12_000),
        ]
        for region in regions:
            counted = measure_aoi_clouds(_cleared(scene), _geojson(region), CLOUDS)
            cached = SceneMeasure.stored(counted.as_measure())
            assert cached is not None
            assert cached.nodata_percent == SceneMeasure.of(counted).nodata_percent
            assert cached.nodata_percent == round(100 - counted.data_percent, 1)

    @pytest.mark.parametrize(
        ("data_pixels", "aoi_pixels", "expected"),
        [(0, 100, 100.0), (100, 100, 0.0), (1, 3, 66.7), (2, 3, 33.3), (1, 7, 85.7), (1, 10_000, 100.0), (9_999, 10_000, 0.0)],
    )
    def test_the_arithmetic(self, data_pixels: int, aoi_pixels: int, expected: float) -> None:
        measure = SceneMeasure.of(AoiClouds(0, data_pixels, aoi_pixels, 20.0))
        assert measure.nodata_percent == expected

AOI = {"type": "Polygon", "coordinates": [[[10.0, 50.0], [10.1, 50.1], [10.2, 50.05], [10.0, 50.0]]]}


def _key(**changes) -> str:
    arguments = {
        "dataset_id": "sentinel-2-c1-l2a",
        "item_id": "S2X_01ABC_20260101_0_L2A",
        "asset": "scl",
        "cloud_classes": CLOUDS,
        "aoi": AOI,
    }
    return aoi_clouds_cache_key(**{**arguments, **changes})


class TestTheCacheKey:
    def test_it_is_a_sha256(self) -> None:
        key = _key()
        assert len(key) == 64 and set(key) <= set("0123456789abcdef")
        assert _key() == key

    def test_the_same_aoi_in_another_spelling_is_one_key(self) -> None:
        whole = {"type": "Polygon", "coordinates": [[[47, 8], [48, 9], [49, 8], [47, 8]]]}
        floats = {"coordinates": [[[47.0, 8.0], [48.0, 9.0], [49.0, 8.0], [47.0, 8.0]]], "type": "Polygon"}
        tuples = {"type": "Polygon", "coordinates": (((47, 8), (48, 9), (49, 8), (47, 8)),)}
        assert _key(aoi=whole) == _key(aoi=floats) == _key(aoi=tuples)

    def test_a_negative_zero_is_a_zero(self) -> None:
        zero = {"type": "Polygon", "coordinates": [[[0.0, 8.0], [1.0, 9.0], [1.0, 8.0], [0.0, 8.0]]]}
        negative = {"type": "Polygon", "coordinates": [[[-0.0, 8.0], [1.0, 9.0], [1.0, 8.0], [-0.0, 8.0]]]}
        assert _key(aoi=zero) == _key(aoi=negative)

    def test_the_classes_are_a_set(self) -> None:
        assert _key(cloud_classes=frozenset({10, 9, 8})) == _key()

    @pytest.mark.parametrize(
        "changes",
        [
            {"dataset_id": "other-dataset"},
            {"item_id": "S2X_01ABC_20260102_0_L2A"},
            {"asset": "scl2"},
            {"cloud_classes": frozenset({8, 9})},
            {"cloud_classes": frozenset()},
            {
                "aoi": {
                    **AOI,
                    "coordinates": [[[10.000001, 50.0], [10.1, 50.1], [10.2, 50.05], [10.000001, 50.0]]],
                }
            },
            {"aoi": {"type": "MultiPolygon", "coordinates": [AOI["coordinates"]]}},
        ],
    )
    def test_anything_else_is_another_key(self, changes) -> None:
        assert _key(**changes) != _key()

    def test_the_fields_do_not_run_into_each_other(self) -> None:
        assert _key(dataset_id="a", item_id="bc") != _key(dataset_id="ab", item_id="c")

    def test_the_version_of_earthx_is_part_of_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        before = _key()
        monkeypatch.setattr(earthx, "__version__", "99.0.0")
        assert _key() != before

    @pytest.mark.parametrize(
        "aoi",
        [
            {"type": "Point", "coordinates": [10.0, 50.0]},
            {"type": "Polygon"},
            {"type": "Polygon", "coordinates": [[["10.0", 50.0]]]},
            {"type": "Polygon", "coordinates": [[[float("nan"), 50.0]]]},
            {"type": "Polygon", "coordinates": [[[[[[1.0]]]]]]},
            {"type": "Polygon", "coordinates": [10.0, 50.0]},
            {"type": "Polygon", "coordinates": []},
            {"type": "MultiPolygon", "coordinates": [[[10.0, 50.0]]]},
            {"type": "Polygon", "coordinates": [[[10**400, 50.0], [10.1, 50.1], [10.2, 50.05], [10**400, 50.0]]]},
            None,
        ],
    )
    def test_what_is_no_area_is_refused_without_its_values(self, aoi) -> None:
        with pytest.raises(ValueError) as caught:
            _key(aoi=aoi)
        assert not any(char.isdigit() for char in str(caught.value))

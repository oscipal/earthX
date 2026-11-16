"""The terrain kernel and its parameters (M5-10): planes with a known answer, a second implementation of the gdaldem
formulas written as loops, the size of a pixel in metres per CRS, edges, and refusals."""

from __future__ import annotations

import dataclasses
import math
from pathlib import Path

import numpy
import pytest
from affine import Affine
from pydantic import ValidationError
from rasterio.crs import CRS
from rio_tiler.models import ImageData

from earthx.catalog.datasets import registry
from earthx.processing.errors import RecipeInvalid, UnsupportedRecipe
from earthx.processing.operators import (
    REGISTRY,
    TERRAIN,
    BandMeta,
    Operator,
    RasterMeta,
    TerrainParams,
    applicable,
    terrain,
)
from earthx.processing.operators.terrain import pixel_metres

UTM = CRS.from_epsg(32632)
SLOPE = {"product": "slope", "bands": ["dem"], "name": "slope", "slope_unit": "degrees"}
ASPECT = {"product": "aspect", "bands": ["dem"], "name": "aspect"}
HILLSHADE = {
    "product": "hillshade",
    "bands": ["dem"],
    "name": "shade",
    "azimuth": 315,
    "altitude": 45,
    "z_factor": 1,
    "multidirectional": False,
}


def _params(base: dict, **changes) -> TerrainParams:
    return TerrainParams.model_validate({**base, **changes}, strict=True)


def _image(heights: numpy.ndarray, *, crs=UTM, left=500000.0, top=5200000.0, size=(10.0, 10.0), mask=None) -> ImageData:
    rows, cols = heights.shape
    bounds = (left, top - rows * size[1], left + cols * size[0], top)
    data = numpy.ma.MaskedArray(heights[None].astype("float32"), mask=None if mask is None else mask[None])
    return ImageData(data, bounds=bounds, crs=crs, band_names=["dem"])


def _computed(image: ImageData, params: TerrainParams) -> numpy.ma.MaskedArray:
    result = TERRAIN.run(image, params)
    assert result.band_names == ["dem", params.name]
    return result.array[1]


def _plane(rows: int, cols: int, east: float, north: float, size: float = 10.0) -> numpy.ndarray:
    """Heights rising ``east`` metres per metre towards east and ``north`` towards north."""
    row, col = numpy.indices((rows, cols), dtype="float64")
    return 100 + east * col * size - north * row * size


# --- planes with a known answer ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["horn", "zevenbergen_thorne"])
def test_the_slope_of_a_plane_is_its_angle(method: str) -> None:
    image = _image(_plane(12, 14, 0.3, 0.4))
    degrees = _computed(image, _params(SLOPE, method=method))
    percent = _computed(image, _params(SLOPE, method=method, slope_unit="percent"))
    assert degrees.shape == (10, 12) and degrees.dtype == numpy.float32 and not degrees.mask.any()
    numpy.testing.assert_allclose(degrees, math.degrees(math.atan(0.5)), rtol=1e-6)
    numpy.testing.assert_allclose(percent, 50.0, rtol=1e-6)


@pytest.mark.parametrize(
    ("east", "north", "facing"),
    [(0.0, 0.2, 180.0), (0.0, -0.2, 0.0), (0.2, 0.0, 270.0), (-0.2, 0.0, 90.0), (0.1, 0.1, 225.0)],
)
def test_the_aspect_of_a_plane_is_the_direction_it_faces(east: float, north: float, facing: float) -> None:
    aspect = _computed(_image(_plane(6, 6, east, north)), _params(ASPECT))
    numpy.testing.assert_allclose(aspect, facing, atol=1e-4)


def test_a_slope_facing_the_light_is_bright_and_one_away_from_it_dark() -> None:
    towards = _computed(_image(_plane(6, 6, 0.3, -0.3)), _params(HILLSHADE))  # faces north-west, the light is at 315°
    away = _computed(_image(_plane(6, 6, -0.3, 0.3)), _params(HILLSHADE))
    flat = _computed(_image(numpy.full((6, 6), 400.0)), _params(HILLSHADE))
    slope = math.atan(0.3 * math.sqrt(2))
    expected = 1 + 254 * math.cos(math.radians(45) - slope)  # the light hits the plane at 45° − slope from its normal
    numpy.testing.assert_allclose(towards, expected, rtol=1e-6)
    numpy.testing.assert_allclose(flat, 1 + 254 * math.sin(math.radians(45)), rtol=1e-6)
    assert float(away.max()) < float(flat.min()) < float(towards.min())


def test_a_plane_lit_from_behind_is_one_not_zero() -> None:
    shade = _computed(_image(_plane(5, 5, -2.0, 2.0)), _params(HILLSHADE, altitude=10))
    numpy.testing.assert_array_equal(shade, 1.0)


# --- a second implementation of the gdaldem formulas ------------------------------------------------------------------


def _gdaldem(heights: numpy.ndarray, size: float, params: TerrainParams) -> numpy.ndarray:
    """gdaldem_lib.cpp (GDAL 3.12) pixel by pixel, for square pixels; NaN where the window is not complete."""
    rows, cols = heights.shape
    out = numpy.full((rows - 2, cols - 2), numpy.nan)
    for r in range(1, rows - 1):
        for c in range(1, cols - 1):
            w = heights[r - 1 : r + 2, c - 1 : c + 2].ravel()
            if numpy.isnan(w).any():
                continue
            if params.method == "horn":
                x = ((w[0] + w[3] + w[3] + w[6]) - (w[2] + w[5] + w[5] + w[8])) / size
                y = ((w[6] + w[7] + w[7] + w[8]) - (w[0] + w[1] + w[1] + w[2])) / -size
                spread = 8
            else:
                x = (w[3] - w[5]) / size
                y = (w[7] - w[1]) / -size
                spread = 2
            if params.product == "slope":
                steep = math.sqrt(x * x + y * y) / spread
                value = 100 * steep if params.slope_unit == "percent" else math.degrees(math.atan(steep))
            elif params.product == "aspect":
                dx, dy = -x, -y  # gdaldem's aspect reads the sums without the pixel size: square pixels only
                if dx == 0 and dy == 0:
                    continue
                angle = math.degrees(math.atan2(dy, -dx))
                value = 450 - angle if angle > 90 else 90 - angle
                value = 0.0 if value == 360 else value
            elif not params.multidirectional:
                z = params.z_factor / spread
                alt, az = math.radians(params.altitude), math.radians(params.azimuth)
                cang = (
                    math.sin(alt) - (y * math.cos(az) * math.cos(alt) * z - x * math.sin(az) * math.cos(alt) * z)
                ) / math.sqrt(1 + z * z * (x * x + y * y))
                value = 1.0 if cang <= 0 else 1 + 254 * cang
            else:
                z = params.z_factor / spread
                alt = math.radians(params.altitude)
                s, ca = math.sin(alt), math.cos(alt) * z
                c225 = math.cos(math.radians(225))
                xx_yy = x * x + y * y
                if xx_yy == 0:
                    value = 1 + 254 * s
                else:
                    lights = [s + (x - y) * c225 * ca, s - x * ca, s + (x + y) * c225 * ca, s - y * ca]
                    w225 = 0.5 * xx_yy - x * y
                    weights = [w225, x * x, xx_yy - w225, y * y]
                    total = sum(wt * max(light, 0) for wt, light in zip(weights, lights, strict=True)) / xx_yy
                    value = 1 + 127 * total / math.sqrt(1 + z * z * xx_yy)
            out[r - 1, c - 1] = value
    return out


VARIANTS = [
    _params(SLOPE),
    _params(SLOPE, slope_unit="percent", method="zevenbergen_thorne"),
    _params(ASPECT),
    _params(ASPECT, method="zevenbergen_thorne"),
    _params(HILLSHADE),
    _params(HILLSHADE, method="zevenbergen_thorne", azimuth=30, altitude=60, z_factor=2.5),
    _params({k: v for k, v in HILLSHADE.items() if k != "azimuth"}, multidirectional=True),
]


@pytest.mark.parametrize("params", VARIANTS, ids=lambda p: f"{p.product}-{p.method}-{p.multidirectional}")
def test_the_kernel_agrees_with_gdaldem_on_a_rough_model_with_gaps(params: TerrainParams) -> None:
    generator = numpy.random.default_rng(10)
    heights = (generator.normal(800, 40, (40, 37)).cumsum(axis=0) / 10).astype("float32").astype("float64")
    gaps = generator.random(heights.shape) < 0.03
    result = _computed(_image(heights, mask=gaps), params)
    expected = _gdaldem(numpy.where(gaps, numpy.nan, heights), 10.0, params)
    numpy.testing.assert_array_equal(numpy.ma.getmaskarray(result), numpy.isnan(expected))
    numpy.testing.assert_allclose(
        result.compressed(), expected[~numpy.isnan(expected)].astype("float32"), rtol=2e-6, atol=1e-4
    )


# --- the size of a pixel in metres -------------------------------------------------------------------------------------


def _metres_per_degree(latitude: float) -> tuple[float, float]:
    """WGS84 east-west and north-south metres of one degree at ``latitude`` (the ellipsoid's radii of curvature)."""
    a, f = 6378137.0, 1 / 298.257223563
    e2 = f * (2 - f)
    phi = math.radians(latitude)
    w = math.sqrt(1 - e2 * math.sin(phi) ** 2)
    return math.radians(1) * a / w * math.cos(phi), math.radians(1) * a * (1 - e2) / w**3


@pytest.mark.parametrize("latitude", [0.5, 47.0, 60.0])
def test_a_plane_on_a_geographic_grid_has_the_slope_it_has_in_metres(latitude: float) -> None:
    step = 1 / 3600
    east_m, north_m = _metres_per_degree(latitude)
    rows, cols = 7, 7
    top = latitude + rows * step / 2
    centres = top - (numpy.arange(rows) + 0.5) * step
    east = numpy.array([_metres_per_degree(lat)[0] for lat in centres])[:, None] * step
    north = numpy.array([_metres_per_degree(lat)[1] for lat in centres]) * step
    # 0.2 m per metre towards east and 0.1 towards north, each row measured at its own latitude.
    southwards = numpy.concatenate([[0.0], numpy.cumsum((north[1:] + north[:-1]) / 2)])[:, None]
    heights = 500 + 0.2 * numpy.arange(cols)[None, :] * east - 0.1 * southwards
    image = _image(heights, crs=CRS.from_epsg(4326), left=8.0, top=top, size=(step, step))
    slope = _computed(image, _params(SLOPE, slope_unit="percent"))
    numpy.testing.assert_allclose(slope, 100 * math.hypot(0.2, 0.1), rtol=1e-3)
    east_size, north_size = pixel_metres(image)
    assert east_size[2, 0] == pytest.approx(east_m * step, rel=1e-6)
    assert north_size[2, 0] == pytest.approx(north_m * step, rel=1e-6)


def test_a_web_mercator_pixel_is_its_size_on_the_ground() -> None:
    latitude = 47.0
    radius = 6378137.0
    y = radius * math.log(math.tan(math.pi / 4 + math.radians(latitude) / 2))
    image = _image(numpy.zeros((3, 3)), crs=CRS.from_epsg(3857), left=900000.0, top=y + 15.0, size=(10.0, 10.0))
    east, north = pixel_metres(image)
    east_m, north_m = _metres_per_degree(latitude)
    # A degree of longitude is radius · π/180 metres of Web Mercator; of latitude, that over cos φ.
    assert east[0, 0] == pytest.approx(10.0 * east_m / (radius * math.radians(1)), rel=1e-6)
    assert north[0, 0] == pytest.approx(
        10.0 * north_m * math.cos(math.radians(latitude)) / (radius * math.radians(1)), rel=1e-5
    )


def test_a_projected_grid_in_feet_is_measured_in_metres() -> None:
    feet = CRS.from_epsg(2229)  # NAD83 / California zone 5 (ftUS)
    east, north = pixel_metres(_image(numpy.zeros((4, 4)), crs=feet, left=6400000.0, top=1800000.0, size=(10.0, 10.0)))
    assert east[0, 0] == pytest.approx(3.048006, rel=1e-6) and north[0, 0] == pytest.approx(3.048006, rel=1e-6)


def test_a_raster_without_a_crs_is_refused() -> None:
    image = _image(_plane(4, 4, 0.1, 0.1), crs=None)
    with pytest.raises(UnsupportedRecipe, match="coordinate reference system"):
        TERRAIN.run(image, _params(SLOPE))


# --- edges, gaps, flat ground ------------------------------------------------------------------------------------------


def test_a_gap_empties_the_pixels_whose_window_reaches_it() -> None:
    gaps = numpy.zeros((7, 7), dtype=bool)
    gaps[3, 3] = True
    slope = _computed(_image(_plane(7, 7, 0.1, 0.1), mask=gaps), _params(SLOPE))
    expected = numpy.zeros((5, 5), dtype=bool)
    expected[1:4, 1:4] = True
    numpy.testing.assert_array_equal(numpy.ma.getmaskarray(slope), expected)
    assert numpy.isnan(numpy.ma.getdata(slope)[2, 2])


def test_a_non_finite_height_counts_as_a_gap() -> None:
    heights = _plane(5, 5, 0.1, 0.1)
    heights[0, 0] = numpy.inf
    slope = _computed(_image(heights), _params(SLOPE))
    assert numpy.ma.getmaskarray(slope)[0, 0] and numpy.ma.getmaskarray(slope).sum() == 1


def test_flat_ground_has_no_aspect_but_a_slope_of_zero() -> None:
    image = _image(numpy.full((5, 5), 250.0))
    assert numpy.ma.getmaskarray(_computed(image, _params(ASPECT))).all()
    numpy.testing.assert_array_equal(_computed(image, _params(SLOPE)), 0.0)


def test_the_halo_goes_and_the_stock_stays() -> None:
    heights = _plane(6, 8, 0.1, 0.2)
    result = TERRAIN.run(_image(heights), _params(SLOPE))
    assert result.array.shape == (2, 4, 6)
    numpy.testing.assert_array_equal(result.array[0], heights[1:-1, 1:-1].astype("float32"))
    assert result.bounds == pytest.approx((500010.0, 5199950.0, 500070.0, 5199990.0))


def test_a_block_no_larger_than_the_window_is_refused() -> None:
    with pytest.raises(RecipeInvalid, match="larger than its window"):
        TERRAIN.run(_image(numpy.zeros((2, 5))), _params(SLOPE))


# --- parameters --------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        ({**SLOPE, "slope_unit": None}, "slope needs slope_unit"),
        ({**SLOPE, "azimuth": 10}, "slope takes no azimuth"),
        ({**ASPECT, "slope_unit": "degrees"}, "aspect takes no slope_unit"),
        ({**HILLSHADE, "slope_unit": "degrees"}, "hillshade takes no slope_unit"),
        ({k: v for k, v in HILLSHADE.items() if k != "azimuth"}, "hillshade needs azimuth"),
        ({**HILLSHADE, "multidirectional": True}, "hillshade takes no azimuth"),
        ({k: v for k, v in HILLSHADE.items() if k != "z_factor"}, "hillshade needs z_factor"),
        ({**HILLSHADE, "z_factor": 0}, "greater than 0"),
        ({**HILLSHADE, "azimuth": 360}, "less than 360"),
        ({**HILLSHADE, "altitude": 91}, "less than or equal to 90"),
        ({**HILLSHADE, "altitude": float("nan")}, "finite"),
        ({**SLOPE, "bands": []}, "at least 1"),
        ({**SLOPE, "bands": ["dem", "dtm"]}, "at most 1"),
        ({**SLOPE, "name": "1slope"}, "a letter"),
        ({**SLOPE, "name": "where"}, "function"),
        ({**SLOPE, "product": "curvature"}, "slope"),
        ({**SLOPE, "method": "sobel"}, "horn"),
        ({**SLOPE, "kernel": 5}, "Extra inputs"),
        ({**SLOPE, "slope_unit": "radians"}, "degrees"),
    ],
)
def test_parameters_that_do_not_fit_the_product_are_refused(data: dict, reason: str) -> None:
    with pytest.raises(ValidationError, match=reason):
        TerrainParams.model_validate(data, strict=True)


def test_the_method_defaults_to_horn() -> None:
    assert _params(SLOPE).method == "horn"


def _meta(unit: str | None = "m", name: str = "dem") -> RasterMeta:
    band = BandMeta(name=name, data_type="float32", nodata=-9999.0, unit=unit)
    return RasterMeta("EPSG:32632", TERRAIN_TRANSFORM, 10, 10, (band,))


TERRAIN_TRANSFORM = _image(numpy.zeros((10, 10))).transform


@pytest.mark.parametrize(
    ("params", "unit"),
    [
        (_params(SLOPE), "deg"),
        (_params(SLOPE, slope_unit="percent"), "%"),
        (_params(ASPECT), "deg"),
        (_params(HILLSHADE), None),
    ],
)
def test_the_new_band_has_a_unit_only_where_it_is_physical(params: TerrainParams, unit: str | None) -> None:
    meta = TERRAIN.transform(_meta(), params)
    assert [(b.name, b.unit, b.data_type) for b in meta.bands] == [
        ("dem", "m", "float32"),
        (params.name, unit, "float32"),
    ]
    assert (meta.width, meta.height, meta.transform) == (10, 10, TERRAIN_TRANSFORM)


@pytest.mark.parametrize(
    ("meta", "params", "reason"),
    [
        (_meta(unit="DN"), _params(SLOPE), "heights in metres; dem is in DN"),
        (_meta(unit=None), _params(SLOPE), "dem is in no unit"),
        (_meta(name="dtm"), _params(SLOPE), "reads dem, which the input does not have"),
        (_meta(), _params(SLOPE, name="DEM"), "used twice"),
    ],
)
def test_a_band_that_is_not_heights_in_metres_is_refused_before_any_read(
    meta: RasterMeta, params: TerrainParams, reason: str
) -> None:
    with pytest.raises(RecipeInvalid, match=reason):
        TERRAIN.transform(meta, params)


def test_the_kernel_refuses_a_band_it_is_not_given() -> None:
    with pytest.raises(RecipeInvalid, match="does not have"):
        TERRAIN.run(_image(numpy.zeros((4, 4))), _params(SLOPE, bands=["dtm"]))


# --- where it applies --------------------------------------------------------------------------------------------------


def test_only_models_of_heights_offer_the_terrain_operator() -> None:
    offered = {config.dataset_id for config in registry(prototype=False) if not applicable(TERRAIN, config)}
    assert offered == {"bev-als-dgm", "cop-dem-glo-30", "swissalti3d"}
    reasons = applicable(TERRAIN, registry().get("sentinel-2-c1-l2a"), _params(SLOPE))
    assert reasons == ["sentinel-2-c1-l2a does not allow terrain"]


def test_the_operator_is_registered_as_a_focal_step_of_both_tiers() -> None:
    operator = REGISTRY.operator("terrain", 1)
    assert (operator.kind, operator.halo, sorted(t.value for t in operator.tiers)) == ("focal", 1, ["T1", "T2"])
    assert operator.passes_values(_params(SLOPE)) is False
    assert operator.listed is True  # offered with the panel's form since the second part of M5-10
    assert REGISTRY.params_schema("terrain", 1)["properties"]["product"]["enum"] == ["slope", "aspect", "hillshade"]


@pytest.mark.parametrize(("kind", "halo"), [("focal", 0), ("pixel", 1), ("grid", 1), ("focal", -1)])
def test_a_halo_belongs_to_a_focal_operator_and_to_no_other(kind: str, halo: int) -> None:
    tiers = TERRAIN.tiers if kind != "grid" else frozenset({next(t for t in TERRAIN.tiers if t.value == "T2")})
    with pytest.raises(ValueError, match="halo"):
        dataclasses.replace(TERRAIN, kind=kind, halo=halo, tiers=tiers)


def test_the_result_names_what_was_computed() -> None:
    params = _params(HILLSHADE)
    assert TERRAIN.lineage(params) == "terrain: shade = hillshade of dem (horn)"
    assert "light from azimuth 315°, altitude 45°, z-factor 1" in TERRAIN.method(params)
    assert TERRAIN.properties(_params(ASPECT)) == {
        "earthx:terrain": {"product": "aspect", "bands": ["dem"], "name": "aspect", "method": "horn"}
    }
    assert isinstance(TERRAIN, Operator)


# --- the same bits in every block and on every machine ----------------------------------------------------------------


@pytest.mark.parametrize("product", [SLOPE, ASPECT, HILLSHADE], ids=lambda p: p["product"])
def test_a_geographic_grid_gives_the_same_bits_in_blocks_of_any_size(product: dict) -> None:
    # The grid of the Copernicus DEM: 1″ pixels, the origin half a pixel off whole degrees, bounds as a block has them.
    grid = Affine(1 / 3600, 0, 7.0001388888888, 0, -1 / 3600, 47.0001388888888)
    heights = (numpy.random.default_rng(0).random((202, 202)) * 50 + 1000).astype("float32")
    params = _params(product)

    def block(row: int, col: int, rows: int, cols: int) -> numpy.ndarray:
        left, top = grid @ (col, row)
        right, bottom = grid @ (col + cols, row + rows)
        data = numpy.ma.MaskedArray(heights[None, row : row + rows, col : col + cols])
        image = ImageData(data, bounds=(left, bottom, right, top), crs=CRS.from_epsg(4326), band_names=["dem"])
        return TERRAIN.run(image, params).array[1].filled(numpy.nan)

    whole = block(0, 0, 202, 202)
    for size in (37, 64):
        tiled = numpy.full((200, 200), numpy.nan, dtype="float32")
        for row in range(0, 200, size):
            for col in range(0, 200, size):
                rows, cols = min(size, 200 - row), min(size, 200 - col)
                tiled[row : row + rows, col : col + cols] = block(row, col, rows + 2, cols + 2)
        assert tiled.tobytes() == whole.tobytes()


def test_the_angles_are_those_of_numpy_to_the_last_digits() -> None:
    # Measured on 15.11.2026: arctan 3.3e-16, arctan2 4.4e-16, sine and cosine 1.1e-15 (radians; at ±720° most of that is
    # numpy's own reduction of the angle). A float32 result has a step of 6e-8 at 1.
    generator = numpy.random.default_rng(3)
    x = numpy.concatenate([numpy.linspace(0, 50, 20001), [0.0, 1.0, 1e-300, 1e300]])
    numpy.testing.assert_allclose(terrain._atan(x), numpy.arctan(x), rtol=0, atol=5e-16)
    y, z = generator.normal(size=20000), generator.normal(size=20000)
    numpy.testing.assert_allclose(terrain._atan2(y, z), numpy.arctan2(y, z), rtol=0, atol=5e-16)
    assert terrain._atan2(numpy.array([0.0]), numpy.array([0.0]))[0] == 0
    degrees = numpy.linspace(-720, 720, 14401)
    sine, cosine = terrain._sin_cos(degrees)
    numpy.testing.assert_allclose(sine, numpy.sin(numpy.radians(degrees)), rtol=0, atol=1.2e-15)
    numpy.testing.assert_allclose(cosine, numpy.cos(numpy.radians(degrees)), rtol=0, atol=1.2e-15)


# --- against gdaldem on a synthetic alpine model (scripts/m5-10/gdaldem_reference.py) ---------------------------------

REFERENCE = Path(__file__).resolve().parents[2] / "fixtures" / "terrain" / "gdaldem_reference.npz"

#: name in the reference → parameters, and the largest difference allowed (measured on 15.11.2026 against GDAL 3.8.4):
#: Horn: gdaldem sums the window in float32 (bit-identical when the sums are float32, checked), the operator in float64,
#: so slope differs by up to 0.0034° and aspect by up to 0.016°; Zevenbergen-Thorne takes differences of two heights
#: only, which float32 holds exactly: slope 0, aspect 3.1e-5°. Hillshade is 8 bits in gdaldem: up to 0.5, and 0.501
#: for four lights.
AGAINST_GDALDEM = {
    "slope_horn_degrees": ({"product": "slope", "slope_unit": "degrees"}, 0.004),
    "slope_zt_percent": ({"product": "slope", "slope_unit": "percent", "method": "zevenbergen_thorne"}, 1e-4),
    "aspect_horn": ({"product": "aspect"}, 0.02),
    "aspect_zt": ({"product": "aspect", "method": "zevenbergen_thorne"}, 1e-4),
    "hillshade_horn": (
        {"product": "hillshade", "azimuth": 315, "altitude": 45, "z_factor": 1, "multidirectional": False},
        0.5,
    ),
    "hillshade_zt": (
        {
            "product": "hillshade",
            "method": "zevenbergen_thorne",
            "azimuth": 30,
            "altitude": 60,
            "z_factor": 2.5,
            "multidirectional": False,
        },
        0.5,
    ),
    "hillshade_multidirectional": (
        {"product": "hillshade", "altitude": 45, "z_factor": 1, "multidirectional": True},
        0.51,
    ),
}


def _reference_image() -> tuple[ImageData, dict]:
    reference = dict(numpy.load(REFERENCE))
    heights = reference["heights"]
    size = float(reference["pixel"])
    gaps = numpy.pad(heights == -9999, 1, constant_values=True)
    padded = numpy.pad(heights, 1, constant_values=-9999)
    rows, cols = padded.shape
    bounds = (2600000 - size, 1200000 + size - rows * size, 2600000 - size + cols * size, 1200000 + size)
    data = numpy.ma.MaskedArray(padded[None], mask=gaps[None])
    return ImageData(data, bounds=bounds, crs=CRS.from_epsg(2056), band_names=["dem"]), reference


@pytest.mark.parametrize("name", sorted(AGAINST_GDALDEM))
def test_the_operator_agrees_with_gdaldem_within_the_measured_difference(name: str) -> None:
    image, reference = _reference_image()
    changes, tolerance = AGAINST_GDALDEM[name]
    result = TERRAIN.run(image, TerrainParams.model_validate({"bands": ["dem"], "name": "t", **changes})).array[1]
    ours, theirs = result.filled(numpy.nan).astype("float64"), reference[name].astype("float64")
    numpy.testing.assert_array_equal(numpy.isnan(ours), numpy.isnan(theirs))  # the same pixels empty
    difference = numpy.abs(ours - theirs)[~numpy.isnan(theirs)]
    if name.startswith("aspect"):
        difference = numpy.minimum(difference, 360 - difference)
    assert difference.max() <= tolerance


@pytest.mark.parametrize("name", sorted(AGAINST_GDALDEM))
def test_the_own_angles_give_the_values_numpy_would(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    # Measured on 15.11.2026: every float32 value the same on the reference model; at most one step of float32 allowed.
    image, _ = _reference_image()
    params = TerrainParams.model_validate({"bands": ["dem"], "name": "t", **AGAINST_GDALDEM[name][0]})
    ours = TERRAIN.run(image, params).array[1]
    monkeypatch.setattr(terrain, "_atan", numpy.arctan)
    monkeypatch.setattr(terrain, "_atan2", numpy.arctan2)
    monkeypatch.setattr(
        terrain, "_sin_cos", lambda degrees: (numpy.sin(numpy.radians(degrees)), numpy.cos(numpy.radians(degrees)))
    )
    with_numpy = TERRAIN.run(image, params).array[1]
    numpy.testing.assert_array_equal(numpy.ma.getmaskarray(ours), numpy.ma.getmaskarray(with_numpy))
    numpy.testing.assert_array_max_ulp(ours.compressed(), with_numpy.compressed(), maxulp=1)

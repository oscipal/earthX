"""NM4-75: the three forms of a band export, on real (small, synthetic) GeoTIFFs, offline.

One scene on a UTM grid with bands of 10, 20 and 60 m and a classification layer, cropped by
:func:`~earthx.access.download.build_download_zip` in each form. The counter-checks (Gegenprobe) sit beside
the checks: a file of another form, a conversion that must not happen, a value that must not change.
"""

from __future__ import annotations

import contextlib
import json
import zipfile
from collections.abc import Iterator
from io import BytesIO
from typing import Any

import numpy as np
import pytest
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from rasterio.warp import transform_geom

from earthx.access import download as dl
from earthx.access.band_export import ExportPlanError, band_meta
from earthx.access.qgis_style import ExportStyle
from earthx.catalog.registry import AcquisitionYears
from tests.catalog.entries import SENTINEL_2_L2A

from .test_download_edge_cases import UTM32, _asset_path, _bbox_to_wgs84, _memcog, _polygon, open_reader

YEARS = AcquisitionYears(2025, 2025)
ORIGIN = (600000, 5700000)

# asset -> (name, common name, wavelength in um, pixel size in m, dtype, scale, offset)
BANDS: dict[str, tuple[str, str | None, float | None, int, str, float | None, float | None]] = {
    "blue": ("B02", "blue", 0.49, 10, "uint16", 0.0001, -0.1),
    "red": ("B04", "red", 0.665, 10, "uint16", 0.0001, -0.1),
    "rededge1": ("B05", "rededge1", 0.705, 20, "uint16", 0.0001, -0.1),
    "coastal": ("B01", "coastal", 0.443, 60, "uint16", 0.0001, -0.1),
    "scl": ("SCL", None, None, 20, "uint8", None, None),
}
SIZE_M = 1200  # the scene is 1200 m wide: 120 px at 10 m, 60 at 20 m, 20 at 60 m


def _item() -> dict[str, Any]:
    return {
        "id": "ITEM1",
        "assets": {
            asset: {
                "gsd": res,
                "eo:bands": [
                    {k: v for k, v in (("name", name), ("common_name", common), ("center_wavelength", wavelength)) if v}
                ],
                "raster:bands": [
                    {"data_type": dtype, "nodata": 0, **({"scale": scale} if scale else {}), **({"offset": offset} if offset else {})}
                ],
            }
            for asset, (name, common, wavelength, res, dtype, scale, offset) in BANDS.items()
        },
    }


def _array(asset: str) -> np.ndarray:
    _name, _common, _wl, res, dtype, _scale, _offset = BANDS[asset]
    n = SIZE_M // res
    rows, cols = np.mgrid[0:n, 0:n]
    if asset == "red":  # a checkerboard: averaging it gives values the source does not have
        data = np.where((rows + cols) % 2 == 0, 100, 200)
    elif asset == "scl":  # classes in 3 x 3 blocks of 20 m, so a 60 m pixel is one class
        data = 1 + ((rows // 3) + (cols // 3)) % 4
    else:
        data = 1000 + 3 * rows + cols
    return data[np.newaxis].astype(dtype)


def _sources() -> tuple[dict[str, MemoryFile], dict[str, Any]]:
    mems = {
        asset: _memcog(_array(asset), crs=UTM32, transform=from_origin(*ORIGIN, BANDS[asset][3], BANDS[asset][3]))
        for asset in BANDS
    }
    item = _item()
    metas = {
        asset: band_meta(item, asset, unit="1", categorical=asset == "scl", classes=SENTINEL_2_L2A.class_rows(asset))
        for asset in BANDS
    }
    return mems, metas


def _zip(
    assets: list[str], *, form: str = "per_band", common: float | None = None, groups: int = 1, aoi: dict | None = None,
    **kwargs: Any,
) -> zipfile.ZipFile:  # fmt: skip
    mems, metas = _sources()
    if aoi is None:
        west, south, east, north = _bbox_to_wgs84(UTM32, (ORIGIN[0], ORIGIN[1] - SIZE_M, ORIGIN[0] + SIZE_M, ORIGIN[1]))
        aoi = _polygon((west, south, east, north))

    def crops(item_id: str) -> list[dl.AssetCrop]:
        return [dl.AssetCrop(asset=a, paths=(_asset_path(mems[a], item_id=item_id, asset=a),)) for a in assets]

    data = dl.build_download_zip(
        config=SENTINEL_2_L2A,
        years=YEARS,
        open_reader=open_reader,
        crops=crops("ITEM1"),
        aoi_geometry=aoi,
        item_ids=["ITEM1"],
        additional_groups=[
            dl.GroupCrop(item_ids=["ITEM2"], crops=crops("ITEM2"), region_geometry=aoi) for _ in range(groups - 1)
        ],
        form=form,
        common_resolution=common,
        band_metas=metas,
        **kwargs,
    )
    return zipfile.ZipFile(BytesIO(data))


@contextlib.contextmanager
def _open(archive: zipfile.ZipFile, name: str) -> Iterator[MemoryFile]:
    with MemoryFile(archive.read(name)) as mem:
        yield mem


def _table(archive: zipfile.ZipFile) -> dict[str, list[list[str]]]:
    """BANDS.txt as {file: rows of cells}."""
    files: dict[str, list[list[str]]] = {}
    current: list[list[str]] | None = None
    for line in archive.read("exports/BANDS.txt").decode().splitlines():
        if line.startswith("File: "):
            current = files.setdefault(line[6:], [])
        elif line.startswith("Classes of band "):
            current = None
        elif current is not None and line and not line.startswith("Band |"):
            current.append([cell.strip() for cell in line.split("|")])
    return files


ALL = list(BANDS)


class TestOneFilePerBand:
    def test_every_band_is_a_file_in_its_own_resolution_and_nothing_is_converted(self) -> None:
        with _zip(ALL) as archive:
            names = set(archive.namelist())
            assert {
                "exports/B02_blue_10m.tif", "exports/B04_red_10m.tif", "exports/B05_rededge1_20m.tif",
                "exports/B01_coastal_60m.tif", "exports/SCL_20m.tif", "exports/BANDS.txt",
            } <= names  # fmt: skip
            sizes = {}
            for asset, (name, common, *_rest) in BANDS.items():
                stem = "_".join(part for part in (name, common if common and common != name else None) if part)
                with _open(archive, f"exports/{stem}_{BANDS[asset][3]}m.tif") as mem, mem.open() as ds:
                    sizes[asset] = ds.width
            # 10 m : 20 m : 60 m pixels -> 6 : 3 : 1 pixels across the same ground.
            assert sizes["blue"] == sizes["red"]
            assert sizes["blue"] == pytest.approx(2 * sizes["rededge1"], abs=2)
            assert sizes["blue"] == pytest.approx(6 * sizes["coastal"], abs=6)
            assert sizes["scl"] == sizes["rededge1"]

    def test_values_of_a_band_are_the_source_values(self) -> None:
        with _zip(["scl"]) as archive, _open(archive, "exports/SCL_20m.tif") as mem, mem.open() as ds:
            assert set(np.unique(ds.read(1))) <= {0, 1, 2, 3, 4}  # 0: nodata beyond the footprint edge, never a new class
            assert ds.dtypes[0] == "uint8"


class TestOneFilePerResolution:
    def test_one_stacked_file_per_resolution_with_the_grid_of_the_per_band_files(self) -> None:
        with _zip(ALL, form="per_resolution") as stacked, _zip(ALL) as single:
            names = set(stacked.namelist())
            assert {"exports/bands_10m.tif", "exports/bands_20m.tif", "exports/bands_60m.tif"} <= names
            assert "exports/B02_blue_10m.tif" not in names  # Gegenprobe: not the other form
            with _open(stacked, "exports/bands_10m.tif") as mem, mem.open() as ds, _open(
                single, "exports/B04_red_10m.tif"
            ) as other_mem, other_mem.open() as other:
                assert ds.count == 2
                assert ds.descriptions == ("B02", "B04")
                assert (ds.width, ds.height, ds.transform) == (other.width, other.height, other.transform)
                # Not converted: the stacked band is the very array of the per-band file.
                np.testing.assert_array_equal(ds.read(2), other.read(1))
            with _open(stacked, "exports/bands_20m.tif") as mem, mem.open() as ds, _open(
                single, "exports/SCL_20m.tif"
            ) as other_mem, other_mem.open() as other:
                assert ds.descriptions == ("B05", "SCL")
                assert (ds.width, ds.height, ds.transform) == (other.width, other.height, other.transform)
                np.testing.assert_array_equal(ds.read(2), other.read(1).astype(ds.dtypes[1]))
                assert ds.dtypes[0] == ds.dtypes[1] == "uint16"  # uint16 and uint8 -> the wider one

    def test_scale_and_offset_travel_with_each_band(self) -> None:
        with _zip(ALL, form="per_resolution") as archive, _open(archive, "exports/bands_20m.tif") as mem, mem.open() as ds:
            assert ds.scales == (0.0001, 1.0)
            assert ds.offsets == (-0.1, 0.0)
            assert ds.nodata == 0


class TestOneMultiBandFile:
    def test_all_bands_on_the_common_resolution_with_descriptions(self) -> None:
        with _zip(ALL, form="multi_band", common=20) as archive, _zip(ALL) as single:
            files = [n for n in archive.namelist() if n.startswith("exports/") and n.endswith(".tif") and "_mask" not in n]
            assert files == ["exports/bands_20m.tif"]
            with _open(archive, files[0]) as mem, mem.open() as ds, _open(
                single, "exports/SCL_20m.tif"
            ) as other_mem, other_mem.open() as native:
                assert ds.count == len(BANDS)
                assert ds.descriptions == ("B02", "B04", "B05", "B01", "SCL")  # in the order asked for
                assert (ds.width, ds.height) == (native.width, native.height)
                red = ds.read(2)
                # 10 m -> 20 m measurements are averaged: values the source (100, 200) does not have.
                inside = red[5:-5, 5:-5]
                assert (~np.isin(inside, [100, 200])).mean() > 0.9
                assert 100 < inside.mean() < 200

    def test_a_finer_resolution_repeats_values_and_a_coarser_one_takes_the_class_that_occurs_most(self) -> None:
        with _zip(["coastal", "scl"], form="multi_band", common=10) as fine, _open(fine, "exports/bands_10m.tif") as mem, mem.open() as ds:
            source = set(np.unique(_array("coastal")))
            assert set(np.unique(ds.read(1))) - {0} <= source  # nearest: no value the source does not have
        with _zip(["rededge1", "scl"], form="multi_band", common=60) as coarse, _open(coarse, "exports/bands_60m.tif") as mem, mem.open() as ds:
            scl = ds.read(2)
            assert set(np.unique(scl)) <= {0, 1, 2, 3, 4}  # mode: a class, never a mean of classes
            assert ds.count == 2

    def test_bands_txt_names_the_conversion_of_each_band(self) -> None:
        with _zip(ALL, form="multi_band", common=20) as archive:
            rows = _table(archive)["exports/bands_20m.tif"]
            by_name = {row[1]: row for row in rows}
            assert by_name["B02"][4:7] == ["10", "20", "average"]
            assert by_name["B05"][4:7] == ["20", "20", "none"]
            assert by_name["B01"][4:7] == ["60", "20", "nearest"]
            assert by_name["SCL"][4:7] == ["20", "20", "none"]
        with _zip(["scl"], form="multi_band", common=60) as archive:
            assert _table(archive)["exports/bands_60m.tif"][0][4:7] == ["20", "60", "mode"]


class TestBandsTxtMatchesTheFiles:
    @pytest.mark.parametrize(("form", "common"), [("per_band", None), ("per_resolution", None), ("multi_band", 20.0)])
    def test_every_file_and_band_of_the_zip_is_listed_as_it_is_written(self, form: str, common: float | None) -> None:
        with _zip(ALL, form=form, common=common) as archive:
            listed = _table(archive)
            written = {n for n in archive.namelist() if n.startswith("exports/") and n.endswith(".tif") and "_mask" not in n}
            assert set(listed) == written
            for path, rows in listed.items():
                with _open(archive, path) as mem, mem.open() as ds:
                    assert [row[0] for row in rows] == [str(i) for i in range(1, ds.count + 1)]
                    assert [row[1] for row in rows] == [d or "" for d in ds.descriptions] or ds.count == 1
                    assert {row[7] for row in rows} == {ds.dtypes[0]}
                    assert [float(row[8]) for row in rows] == list(ds.scales)
                    assert [float(row[9]) for row in rows] == list(ds.offsets)
                    assert {row[10] for row in rows} == {"0"} and ds.nodata == 0
                    if form != "per_band":  # the bands of one file lie on one grid, so they share one pixel size
                        assert len({row[5] for row in rows}) == 1
                    if form == "multi_band":
                        assert {row[5] for row in rows} == {"20"}

    def test_head_names_the_layout_the_common_resolution_and_the_notes(self) -> None:
        with _zip(ALL, form="multi_band", common=20, bands_notes=["Note: scenes were reprojected."]) as archive:
            head = archive.read("exports/BANDS.txt").decode().split("\n\n")[0].splitlines()
            assert head == [
                "EarthX band list",
                f"Dataset: {SENTINEL_2_L2A.title}",
                "Layout: one multi-band file",
                "Common resolution: 20 m",
                "Note: scenes were reprojected.",
            ]
        with _zip(ALL) as archive:
            assert "Common resolution" not in archive.read("exports/BANDS.txt").decode()  # Gegenprobe


class TestGroupsAndRefusals:
    def test_two_groups_get_their_own_folder_under_exports(self) -> None:
        with _zip(["blue", "scl"], form="per_resolution", groups=2) as archive:
            names = set(archive.namelist())
            assert {"exports/group-01/bands_10m.tif", "exports/group-02/bands_20m.tif"} <= names
            assert set(_table(archive)) >= {"exports/group-01/bands_10m.tif", "exports/group-02/bands_20m.tif"}

    @pytest.mark.parametrize(
        ("form", "common", "message"),
        [
            ("multi_band", None, "common resolution"),
            ("per_band", 20.0, "common resolution"),
            ("per_resolution", 20.0, "common resolution"),
            ("zip", None, "form is one of"),
            ("multi_band", -5.0, "positive"),
        ],
    )
    def test_a_form_and_resolution_that_do_not_fit_are_refused_before_any_read(
        self, form: str, common: float | None, message: str
    ) -> None:
        with pytest.raises(ExportPlanError, match=message):
            _zip(["blue"], form=form, common=common)

    def test_a_source_asset_of_several_bands_cannot_be_stacked(self) -> None:
        mems, metas = _sources()
        three = _memcog(np.ones((3, 120, 120), dtype="uint16"), crs=UTM32, transform=from_origin(*ORIGIN, 10, 10))
        aoi = _polygon(_bbox_to_wgs84(UTM32, (ORIGIN[0], ORIGIN[1] - SIZE_M, ORIGIN[0] + SIZE_M, ORIGIN[1])))
        with pytest.raises(ExportPlanError, match="exactly one band"):
            dl.build_download_zip(
                config=SENTINEL_2_L2A, years=YEARS, open_reader=open_reader,
                crops=[dl.AssetCrop(asset="visual", paths=(_asset_path(three, asset="visual"),))],
                aoi_geometry=aoi, item_ids=["ITEM1"], form="per_resolution", band_metas=metas,
            )  # fmt: skip

    def test_an_aoi_that_misses_every_band_is_refused_not_an_empty_zip(self) -> None:
        mems, metas = _sources()
        far = _polygon((30.0, 10.0, 30.1, 10.1))
        with pytest.raises((dl.AoiOutsideItems, rasterio.errors.RasterioError, Exception)) as raised:
            dl.build_download_zip(
                config=SENTINEL_2_L2A, years=YEARS, open_reader=open_reader,
                crops=[dl.AssetCrop(asset="blue", paths=(_asset_path(mems["blue"], asset="blue"),)),
                       dl.AssetCrop(asset="red", paths=(_asset_path(mems["red"], asset="red"),))],
                aoi_geometry=far, item_ids=["ITEM1"], form="per_resolution", band_metas=metas,
            )  # fmt: skip
        assert "zip" not in str(type(raised.value)).lower()


class TestTheGridIsTheSources:
    """Otto, 03.11.2026: every export lies in the CRS of the source, at its pixel size, on its pixel lattice."""

    @pytest.mark.parametrize("form", ["per_band", "per_resolution"])
    def test_crs_pixel_size_and_pixels_are_the_sources_and_nothing_is_resampled(self, form: str) -> None:
        names = {"per_band": "exports/B04_red_10m.tif", "per_resolution": "exports/bands_10m.tif"}
        with _zip(["red"], form=form) as archive, _open(archive, names[form]) as mem, mem.open() as ds:
            assert ds.crs.to_epsg() == 32632
            assert (ds.transform.a, -ds.transform.e) == (10.0, 10.0)
            # The grid lies on the lattice of the source: its origin is a whole number of pixels from the source's.
            assert (ds.transform.c - ORIGIN[0]) % 10 == 0 and (ORIGIN[1] - ds.transform.f) % 10 == 0
            out = ds.read(1)
            source = _array("red")[0]
            col0, row0 = int((ds.transform.c - ORIGIN[0]) / 10), int((ORIGIN[1] - ds.transform.f) / 10)
            inside = out[max(0, -row0) : source.shape[0] - row0, max(0, -col0) : source.shape[1] - col0]
            expected = source[max(0, row0) : max(0, row0) + inside.shape[0], max(0, col0) : max(0, col0) + inside.shape[1]]
            np.testing.assert_array_equal(inside[: expected.shape[0], : expected.shape[1]], expected)

    def test_a_20_m_band_keeps_its_own_pixel_size_in_utm(self) -> None:
        with _zip(["rededge1", "coastal"]) as archive:
            for name, size in (("exports/B05_rededge1_20m.tif", 20.0), ("exports/B01_coastal_60m.tif", 60.0)):
                with _open(archive, name) as mem, mem.open() as ds:
                    assert ds.crs.to_epsg() == 32632 and (ds.transform.a, -ds.transform.e) == (size, size)

    def test_a_common_resolution_is_a_coarser_lattice_from_the_same_origin(self) -> None:
        with _zip(["blue", "scl"], form="multi_band", common=60) as archive, _open(archive, "exports/bands_60m.tif") as mem, mem.open() as ds:
            assert ds.crs.to_epsg() == 32632 and (ds.transform.a, -ds.transform.e) == (60.0, 60.0)
            assert (ds.transform.c - ORIGIN[0]) % 60 == 0 and (ORIGIN[1] - ds.transform.f) % 60 == 0

    def test_the_mask_lies_on_the_same_grid_as_the_data(self) -> None:
        with _zip(["red"]) as archive, _open(archive, "exports/B04_red_10m.tif") as a, a.open() as data, _open(
            archive, "exports/B04_red_10m_mask.tif"
        ) as b, b.open() as mask:
            assert (mask.crs, mask.transform, mask.shape) == (data.crs, data.transform, data.shape)
            assert set(np.unique(mask.read(1))) == {0, 1}


class TestClasses:
    """M5-62: a band of classes keeps them in the ZIP: colour table, names and table beside the file, BANDS.txt."""

    def test_a_file_of_the_band_holds_its_colour_table_and_has_its_names_beside_it(self) -> None:
        with _zip(["scl"]) as archive, _open(archive, "exports/SCL_20m.tif") as mem, mem.open() as ds:
            assert ds.colormap(1)[3][:3] == (44, 160, 44)  # the third colour of the palette, for class 3
            beside = archive.read("exports/SCL_20m.tif.aux.xml").decode()
            assert "<Category>Cloud shadows</Category>" in beside
            assert "Classes of band 1 (SCL)\nValue | Class | Colour\n1 | Saturated or defective | #1f77b4" in (
                archive.read("exports/BANDS.txt").decode()
            )

    def test_in_a_stacked_file_only_the_band_of_classes_is_named_beside_it(self) -> None:
        with _zip(["blue", "scl"], form="multi_band", common=20) as archive:
            assert '<PAMRasterBand band="2">' in archive.read("exports/bands_20m.tif.aux.xml").decode()
            with _open(archive, "exports/bands_20m.tif") as mem, mem.open() as ds, pytest.raises(ValueError):
                ds.colormap(2)

    def test_bands_without_classes_have_nothing_beside_them(self) -> None:
        with _zip(["blue", "red"]) as archive:
            assert not [name for name in archive.namelist() if name.endswith(".aux.xml")]
            assert "Classes" not in archive.read("exports/BANDS.txt").decode()


def _point(x: float, y: float) -> dict:
    """A point ``x`` m east and ``y`` m south of the scene's corner, in WGS84."""
    return transform_geom(UTM32, "EPSG:4326", {"type": "Point", "coordinates": [ORIGIN[0] + x, ORIGIN[1] - y]})


class TestAPoint:
    """M5-69: a point crops the one pixel it lies on, each band in its own resolution or all in the common one."""

    POINT = _point(10 * 37 + 4, 10 * 52 + 6)

    def test_each_band_is_its_own_pixel_under_the_point(self) -> None:
        with _zip(["red", "rededge1", "coastal"], aoi=self.POINT) as archive:
            for name, asset, size in (
                ("exports/B04_red_10m.tif", "red", 10),
                ("exports/B05_rededge1_20m.tif", "rededge1", 20),
                ("exports/B01_coastal_60m.tif", "coastal", 60),
            ):
                col, row = (10 * 37 + 4) // size, (10 * 52 + 6) // size
                with _open(archive, name) as mem, mem.open() as ds:
                    assert (ds.width, ds.height) == (1, 1)
                    assert (ds.transform.c, ds.transform.f) == (ORIGIN[0] + col * size, ORIGIN[1] - row * size)
                    assert ds.read(1)[0, 0] == _array(asset)[0, row, col]
                with _open(archive, name.replace(".tif", "_mask.tif")) as mem, mem.open() as mask:
                    assert mask.read(1).tolist() == [[1]]
            assert json.loads(archive.read("aoi.geojson"))["type"] == "Point"

    def test_one_multi_band_file_is_the_one_pixel_of_the_common_resolution(self) -> None:
        with _zip(["blue", "scl"], form="multi_band", common=60, aoi=self.POINT) as archive, _open(
            archive, "exports/bands_60m.tif"
        ) as mem, mem.open() as ds:
            assert (ds.count, ds.width, ds.height) == (2, 1, 1)
            assert (ds.transform.c, ds.transform.f) == (ORIGIN[0] + 6 * 60, ORIGIN[1] - 8 * 60)
            assert ds.read(2)[0, 0] == _array("scl")[0, 8 * 3, 6 * 3]  # one class in each 60 m pixel

    def test_a_point_on_an_edge_takes_the_pixel_right_of_and_below_it(self) -> None:
        with _zip(["red"], aoi=_point(10 * 40, 10 * 30)) as archive, _open(archive, "exports/B04_red_10m.tif") as mem, mem.open() as ds:
            assert (ds.transform.c, ds.transform.f) == (ORIGIN[0] + 400, ORIGIN[1] - 300)

    def test_a_point_beside_the_scene_is_refused(self) -> None:
        with pytest.raises(dl.AoiOutsideItems):
            _zip(["red"], aoi=_point(-50, 50))


class TestQgisStyle:
    """M5-64: beside each data file its QGIS style, drawn as the order says, else with the collection's looks."""

    def test_each_data_file_has_its_style_and_no_mask_has_one(self) -> None:
        with _zip(["blue", "red", "scl"]) as archive:
            names = archive.namelist()
            data = [n for n in names if n.endswith(".tif") and not n.endswith("_mask.tif")]
            assert sorted(n for n in names if n.endswith(".qml")) == sorted(n[:-4] + ".qml" for n in data)

    def test_the_style_of_a_band_of_classes_draws_the_colours_of_its_colour_table(self) -> None:
        with _zip(["scl"]) as archive, _open(archive, "exports/SCL_20m.tif") as mem, mem.open() as ds:
            table = ds.colormap(1)
            qml = archive.read("exports/SCL_20m.qml").decode()
            assert 'type="paletted"' in qml
            for row in SENTINEL_2_L2A.class_rows("scl") or ():
                colour = "#{:02x}{:02x}{:02x}".format(*table[row.value][:3])
                assert f'value="{row.value}" color="{colour}" alpha="255" label="{row.name}"' in qml

    def test_the_drawn_band_is_drawn_in_a_stacked_file_on_its_number(self) -> None:
        style = ExportStyle(band="red", colormap="magma", range=(0.02, 0.24))
        with _zip(["blue", "red"], form="multi_band", common=10, style=style) as archive:
            qml = archive.read("exports/bands_10m.qml").decode()
            assert 'band="2"' in qml and 'classificationMin="0.02"' in qml and 'classificationMax="0.24"' in qml

    def test_the_true_colour_bands_in_one_file_are_one_colour_picture(self) -> None:
        assets, true_color = ["blue", "red", "rededge1"], ("red", "rededge1", "blue")
        with _zip(assets, form="multi_band", common=10, true_color=true_color) as archive:
            qml = archive.read("exports/bands_10m.qml").decode()
            assert 'type="multibandcolor"' in qml and 'redBand="2"' in qml and 'greenBand="3"' in qml and 'blueBand="1"' in qml

    def test_sld_lies_beside_each_file_and_none_leaves_them_out(self) -> None:
        with _zip(["blue", "scl"], style_format="sld") as archive:
            names = archive.namelist()
            assert {"exports/B02_blue_10m.sld", "exports/SCL_20m.sld"} <= set(names)
            assert not [n for n in names if n.endswith(".qml")]
            assert 'label="' in archive.read("exports/SCL_20m.sld").decode(), "the classes by name"
        with _zip(["blue", "scl"], style_format="none") as archive:
            assert not [n for n in archive.namelist() if n.endswith((".qml", ".sld"))]

    def test_a_file_of_one_channel_of_the_drawn_picture_is_grey_in_its_stretch(self) -> None:
        style = ExportStyle(rgb=("red", "rededge1", "blue"), ranges=((0.0, 0.3), (0.0, 0.25), (0.0, 0.2)))
        with _zip(["blue", "red"], style=style) as archive:
            qml = archive.read("exports/B02_blue_10m.qml").decode()
            assert 'type="singlebandgray"' in qml and "<maxValue>0.2</maxValue>" in qml

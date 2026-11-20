"""The classes of a band in the export (M5-62): colour table in the GeoTIFF, names and table beside it, and BANDS.txt."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import replace

import numpy
import pytest
import rasterio
from rasterio.io import MemoryFile
from rio_cogeo.cogeo import cog_translate

from earthx.access.band_export import (
    AUX_SUFFIX,
    BandMeta,
    BandsFile,
    apply_band_tags,
    band_meta,
    bands_text,
    class_aux_xml,
    class_files,
    colour_table,
)
from earthx.access.crop_rules import COG_PROFILE
from earthx.catalog.registry import ClassRow

CLASSES = (ClassRow(10, "Tree cover", "#006400"), ClassRow(60, "Bare / sparse vegetation", "#b4b4b4"))
TIFF = "image/tiff; application=geotiff; profile=cloud-optimized"


def _meta(classes: tuple[ClassRow, ...] | None = CLASSES, *, nodata: float | None = 0.0, name: str = "map") -> BandMeta:
    item = {"assets": {name: {"type": TIFF, "raster:bands": [{"data_type": "uint8", "nodata": nodata}]}}}
    return band_meta(item, name, classes=classes)


def _cog(dtype: str, metas: list[BandMeta]) -> rasterio.DatasetReader:
    """A small file written as crop and export write theirs: tags first, then ``cog_translate``; read back."""
    profile = {
        "driver": "GTiff", "dtype": dtype, "count": len(metas), "width": 64, "height": 64, "crs": "EPSG:4326",
        "transform": rasterio.transform.from_origin(0, 1, 0.01, 0.01), "nodata": 0,
    }  # fmt: skip
    with MemoryFile() as plain:
        with plain.open(**profile) as dst:
            apply_band_tags(dst, metas)
            dst.write(numpy.full((len(metas), 64, 64), 10, dtype=dtype))
        with plain.open() as source, MemoryFile() as out:
            cog_translate(source, out.name, COG_PROFILE, in_memory=True, quiet=True)
            return MemoryFile(out.read()).open()


class TestTheBand:
    def test_a_band_of_classes_is_categorical(self) -> None:
        assert _meta().categorical
        assert not _meta(None).categorical

    def test_the_classes_travel_in_the_json_of_a_job(self) -> None:
        meta = _meta()
        assert BandMeta.from_json(meta.to_json()) == meta
        assert meta.to_json()["classes"][1] == {"value": 60, "name": "Bare / sparse vegetation", "colour": "#b4b4b4"}

    def test_json_from_before_the_classes_reads_as_a_band_without_them(self) -> None:
        data = _meta().to_json()
        del data["classes"]
        assert BandMeta.from_json(data).classes is None

    @pytest.mark.parametrize(
        "classes",
        [[], "Tree cover", [{"value": 10, "name": "Tree cover"}], [{"value": True, "name": "A", "colour": "#000000"}],
         [{"value": 10, "name": 3, "colour": "#000000"}], [{"value": 10, "name": "A", "colour": "green"}],
         [{"value": 10, "name": "A", "colour": "#000000", "extra": 1}]],
        ids=["empty", "text", "no colour", "boolean value", "number as name", "colour name", "unknown field"],
    )  # fmt: skip
    def test_wrong_classes_in_the_json_are_refused(self, classes) -> None:
        data = {**_meta().to_json(), "classes": classes}
        with pytest.raises(ValueError):
            BandMeta.from_json(data)


class TestTheGeoTiff:
    @pytest.mark.parametrize("dtype", ["uint8", "uint16"])
    def test_one_band_of_classes_holds_its_colour_table_after_cog_translate(self, dtype: str) -> None:
        with _cog(dtype, [_meta()]) as written:
            table = written.colormap(1)
        assert table[10] == (0, 100, 0, 255)
        assert table[60] == (180, 180, 180, 255)
        assert table[0][3] == 0

    def test_a_float_file_has_no_colour_table(self) -> None:
        with _cog("float32", [_meta()]) as written, pytest.raises(ValueError):
            written.colormap(1)

    def test_a_file_of_several_bands_has_no_colour_table(self) -> None:
        with _cog("uint8", [_meta(), _meta(None, name="red")]) as written, pytest.raises(ValueError):
            written.colormap(1)

    def test_a_band_without_classes_has_no_colour_table(self) -> None:
        with _cog("uint8", [_meta(None)]) as written, pytest.raises(ValueError):
            written.colormap(1)

    def test_nodata_that_is_no_whole_number_is_left_out_of_the_table(self) -> None:
        assert set(colour_table(_meta(nodata=None))) == {10, 60}
        assert set(colour_table(_meta(nodata=float("nan")))) == {10, 60}


class TestTheFileBeside:
    def test_names_and_table_of_each_band_of_classes(self) -> None:
        root = ET.fromstring(class_aux_xml([_meta(None, name="red"), _meta()]))
        (band,) = root.findall("PAMRasterBand")
        assert band.get("band") == "2"
        names = [category.text or "" for category in band.find("CategoryNames")]
        assert len(names) == 61
        assert (names[10], names[60], names[0]) == ("Tree cover", "Bare / sparse vegetation", "")
        table = band.find("GDALRasterAttributeTable")
        assert [field.findtext("Name") for field in table.findall("FieldDefn")] == ["Value", "Class", "Red", "Green", "Blue"]
        assert [field.findtext("Usage") for field in table.findall("FieldDefn")] == ["5", "2", "6", "7", "8"]
        rows = [[cell.text for cell in row.findall("F")] for row in table.findall("Row")]
        assert rows == [["10", "Tree cover", "0", "100", "0"], ["60", "Bare / sparse vegetation", "180", "180", "180"]]

    def test_a_name_is_written_as_text_of_the_xml(self) -> None:
        odd = (ClassRow(1, "Rock & <ice>", "#ffffff"),)
        root = ET.fromstring(class_aux_xml([_meta(odd)]))
        assert root.find("PAMRasterBand/CategoryNames")[1].text == "Rock & <ice>"

    def test_values_below_zero_get_the_table_but_no_list_of_names(self) -> None:
        band = ET.fromstring(class_aux_xml([_meta((ClassRow(-1, "Sea", "#0000ff"),))])).find("PAMRasterBand")
        assert band.find("CategoryNames") is None
        assert band.find("GDALRasterAttributeTable/Row/F").text == "-1"

    def test_no_band_of_classes_no_file(self) -> None:
        assert class_aux_xml([_meta(None)]) is None
        files = [BandsFile("exports/map.tif", [_meta()], ["none"], [10.0]), BandsFile("exports/red.tif", [_meta(None)], ["none"], [10.0])]
        assert [path for path, _ in class_files(files)] == ["exports/map.tif" + AUX_SUFFIX]


class TestTheBandList:
    def test_bands_txt_lists_the_classes_of_a_band_after_its_file(self) -> None:
        files = [BandsFile("exports/stack.tif", [_meta(None, name="red"), _meta()], ["none", "none"], [10.0, 10.0])]
        text = bands_text(title="WorldCover", form="per_resolution", files=files)
        assert text.endswith(
            "Classes of band 2 (map)\nValue | Class | Colour\n10 | Tree cover | #006400\n60 | Bare / sparse vegetation | #b4b4b4\n"
        )

    def test_a_band_without_classes_adds_nothing(self) -> None:
        files = [BandsFile("exports/red.tif", [_meta(None, name="red")], ["none"], [10.0])]
        assert "Classes" not in bands_text(title="x", form="per_band", files=files)

    def test_the_name_of_the_band_is_the_one_its_row_shows(self) -> None:
        files = [BandsFile("exports/map.tif", [replace(_meta(), name="Land cover")], ["none"], [10.0])]
        assert "Classes of band 1 (Land cover)" in bands_text(title="x", form="per_band", files=files)

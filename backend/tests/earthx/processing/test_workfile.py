"""Work files only below the work directory: no URL, no /vsi…, no way out (plan M4-07a §8, F4)."""

from __future__ import annotations

import os
from pathlib import Path

import numpy
import pytest
import rasterio
from rasterio.transform import from_origin

from earthx.processing.errors import WorkfileRejected
from earthx.processing.workfile import open_workfile, open_workfile_band, workfile_path

PROFILE = {"driver": "GTiff", "dtype": "uint8", "count": 1, "width": 4, "height": 4}


class TestTheCounterSample:
    """What must work, so the refusals below are refusals and not a broken helper."""

    def test_a_plain_name_is_written_and_read_back_inside_the_directory(self, tmp_path: Path) -> None:
        with open_workfile(tmp_path, "pass-0.tif", "w", **PROFILE) as dst:
            dst.write(numpy.full((1, 4, 4), 7, dtype="uint8"))
        assert (tmp_path / "pass-0.tif").is_file()
        with open_workfile(tmp_path, "pass-0.tif") as src:
            assert src.read(1).tolist() == [[7] * 4] * 4

    def test_the_path_is_the_resolved_directory_plus_the_name(self, tmp_path: Path) -> None:
        assert workfile_path(tmp_path, "result.tif") == tmp_path.resolve() / "result.tif"


class TestRefusals:
    @pytest.mark.parametrize(
        "name",
        [
            "../escape.tif",
            "..",
            ".",
            ".hidden.tif",
            "a..b.tif",
            "sub/file.tif",
            "sub\\file.tif",
            "/etc/passwd",
            "/vsicurl/https://example.invalid/a.tif",
            "/vsimem/a.tif",
            "https://example.invalid/a.tif",
            "s3://bucket/a.tif",
            "file:a.tif",
            "",
            "a" * 200,
        ],
    )
    def test_a_name_that_is_not_a_plain_file_name(self, tmp_path: Path, name: str) -> None:
        with pytest.raises(WorkfileRejected):
            workfile_path(tmp_path, name)
        with pytest.raises(WorkfileRejected):
            open_workfile(tmp_path, name, "w", **PROFILE)
        assert list(tmp_path.iterdir()) == []

    def test_a_symbolic_link_out_of_the_directory(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside"
        inside = tmp_path / "work"
        outside.mkdir()
        inside.mkdir()
        os.symlink(outside / "target.tif", inside / "link.tif")
        with pytest.raises(WorkfileRejected):
            open_workfile(inside, "link.tif", "w", **PROFILE)
        assert list(outside.iterdir()) == []

    def test_a_work_directory_given_as_a_string_or_missing(self, tmp_path: Path) -> None:
        with pytest.raises(WorkfileRejected):
            workfile_path(str(tmp_path), "a.tif")  # type: ignore[arg-type]
        with pytest.raises(FileNotFoundError):
            workfile_path(tmp_path / "missing", "a.tif")
        (tmp_path / "file").write_text("")
        with pytest.raises(WorkfileRejected):
            workfile_path(tmp_path / "file", "a.tif")

    def test_only_read_and_write(self, tmp_path: Path) -> None:
        for mode in ("r+", "a", "w+"):
            with pytest.raises(WorkfileRejected):
                open_workfile(tmp_path, "a.tif", mode)


def _two_band_file(directory: Path, name: str = "pass-0.tif") -> Path:
    profile = {**PROFILE, "dtype": "float64", "count": 2, "nodata": float("nan"), "crs": "EPSG:32632"}
    with open_workfile(directory, name, "w", **{**profile, "transform": from_origin(600000, 5200000, 10, 10)}) as dst:
        dst.write(numpy.stack([numpy.full((4, 4), 1.0), numpy.full((4, 4), 2.0)]))
    return directory / name


class TestABandOfAWorkFile:
    """The view of one band (NM4-43b) opens nothing but the work file it is made from."""

    def test_each_band_is_a_dataset_of_one_band(self, tmp_path: Path) -> None:
        _two_band_file(tmp_path)
        with open_workfile(tmp_path, "pass-0.tif") as source:
            for band, value in ((1, 1.0), (2, 2.0)):
                with open_workfile_band(source, band) as view:
                    assert (view.count, view.width, view.height) == (1, 4, 4)
                    assert view.read(1).tolist() == [[value] * 4] * 4

    def test_a_directory_with_markup_characters_in_its_name(self, tmp_path: Path) -> None:
        directory = tmp_path / "a&b <c> 'd'"
        directory.mkdir()
        _two_band_file(directory)
        with open_workfile(directory, "pass-0.tif") as source, open_workfile_band(source, 2) as view:
            assert view.read(1).tolist() == [[2.0] * 4] * 4

    @pytest.mark.parametrize("band", [0, 3, -1])
    def test_a_band_the_file_does_not_have(self, tmp_path: Path, band: int) -> None:
        _two_band_file(tmp_path)
        with open_workfile(tmp_path, "pass-0.tif") as source, pytest.raises(WorkfileRejected, match="no such band"):
            open_workfile_band(source, band)

    def test_a_file_that_is_not_a_plain_work_file_is_refused(self, tmp_path: Path) -> None:
        """A file whose name could not be a work file is not made into a view, wherever it lies."""
        odd = tmp_path / "a&b <c>.tif"
        with rasterio.open(odd, "w", **{**PROFILE, "dtype": "float64", "count": 2}) as dst:
            dst.write(numpy.zeros((2, 4, 4)))
        with rasterio.open(odd) as source, pytest.raises(WorkfileRejected):
            open_workfile_band(source, 1)

    def test_a_symbolic_link_is_refused(self, tmp_path: Path) -> None:
        real = _two_band_file(tmp_path, "real.tif")
        (tmp_path / "link.tif").symlink_to(real)
        with rasterio.open(tmp_path / "link.tif") as source, pytest.raises(WorkfileRejected):
            open_workfile_band(source, 1)

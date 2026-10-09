"""Work files only below the work directory: no URL, no /vsi…, no way out (plan M4-07a §8, F4)."""

from __future__ import annotations

import os
from pathlib import Path

import numpy
import pytest

from earthx.processing.errors import WorkfileRejected
from earthx.processing.workfile import open_workfile, workfile_path

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

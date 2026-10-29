"""The passes a later pass reads are stored band by band; the files of a job stay as they were (NM4-43b).

``reproject`` Version 4 reads one band at a time from the previous pass, and reading one band of a
pixel-interleaved, deflated tile unpacks all of its bands (``adr/0014``, addendum NM4-43b). So the core writes
such a pass with ``INTERLEAVE=BAND``. Otto's condition (28.10.2026): only those intermediate files; ``result.tif`` and
``mask.tif`` keep their layout and, up to three bands, their bytes. "Before" is the same run with GDAL's layout
for every file, which these tests switch back on.
"""

from __future__ import annotations

from pathlib import Path

import numpy
import pytest
import rasterio

from earthx.processing import core, run
from earthx.processing.operators import REGISTRY
from earthx.processing.recipe import recipe_from_data
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import resolved

WIDTH, HEIGHT = 1300, 1100
ASSETS = ("red", "nir", "swir", "green")


def _step(version: int) -> dict:
    params = {"crs": "EPSG:3035", "resolution": 10.0, "resampling": "bilinear"}
    return {"op": "reproject", "op_version": version, "params": params}


def _recipe(count: int, version: int = 4) -> dict:
    assets = ASSETS[:count]
    entries = [resolved("ITEM_A", asset, href=sources.url(asset)) for asset in assets]
    return {
        "recipe_version": 1,
        "inputs": [
            {"name": "s2", "dataset": "synthetic", "groups": [["ITEM_A"]], "assets": list(assets), "resolved": entries}
        ],
        "aoi": sources.whole(WIDTH, HEIGHT),
        "steps": [_step(version)],
        "output": {"kind": "raster", "format": "cog", "dtype": "float32"},
    }


@pytest.fixture(scope="module")
def cogs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("interleave")
    return {
        asset: sources.build_band_cog(root / f"{asset}.tif", sources.ramp(WIDTH, HEIGHT, 1200 + 700 * index))
        for index, asset in enumerate(ASSETS)
    }


@pytest.fixture
def served(cogs: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    sources.serve({sources.url(asset): path for asset, path in cogs.items()}, monkeypatch)
    return monkeypatch


def _run(tmp_path: Path, count: int, version: int = 4, *, gdal_layout: bool = False, monkeypatch=None):
    """One run; with ``gdal_layout`` every work file gets GDAL's own layout, as before NM4-43b."""
    if gdal_layout:
        original = core._profile
        monkeypatch.setattr(core, "_profile", lambda meta, dtype, nodata, interleave=None: original(meta, dtype, nodata))
    tmp_path.mkdir()
    return run(
        recipe_from_data(_recipe(count, version), REGISTRY), workdir=tmp_path, progress=lambda done, total: None
    )


def _profile_of(path: Path) -> dict:
    with rasterio.open(path) as dataset:
        profile = {**dataset.profile, "interleave": dataset.interleaving, "tags": dataset.tags()}
        profile["nodata"] = "nan" if dataset.nodata != dataset.nodata else dataset.nodata
        return profile


@pytest.mark.usefixtures("served")
class TestWhichFilesAreStoredByBand:
    def test_only_a_pass_that_a_later_pass_reads(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        opened: list[tuple[str, str | None]] = []
        real = core.open_workfile

        def spy(workdir, name, mode="r", **profile):
            if mode == "w":
                opened.append((name, profile.get("interleave")))
            return real(workdir, name, mode, **profile)

        monkeypatch.setattr(core, "open_workfile", spy)
        _run(tmp_path / "run", 2)
        names = [name for name, _ in opened]
        assert names[0] == core.MASK_NAME and len(names) >= 3 and len(set(names)) == len(names)
        assert [layout for _, layout in opened] == [None, *["band"] * (len(names) - 2), None]

    @pytest.mark.parametrize("count", [1, 3, 4])
    def test_the_files_of_a_job_have_the_format_of_before(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, count: int
    ) -> None:
        before = _run(tmp_path / "before", count, 3, gdal_layout=True, monkeypatch=monkeypatch)
        after = _run(tmp_path / "after", count, 4)
        for path_before, path_after in ((before.path, after.path), (before.mask_path, after.mask_path)):
            assert _profile_of(path_after) == _profile_of(path_before)


@pytest.mark.usefixtures("served")
class TestTheFilesOfAJobAreBytesOfBefore:
    @pytest.mark.parametrize("count", [1, 2, 3])
    def test_up_to_three_bands_result_and_mask_are_byte_identical_to_version_3_before(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, count: int
    ) -> None:
        before = _run(tmp_path / "before", count, 3, gdal_layout=True, monkeypatch=monkeypatch)
        after = _run(tmp_path / "after", count, 4)
        assert after.path.read_bytes() == before.path.read_bytes()
        assert after.mask_path.read_bytes() == before.mask_path.read_bytes()

    @pytest.mark.parametrize("version", [3, 4])
    def test_the_layout_alone_changes_no_byte_of_four_bands(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, version: int
    ) -> None:
        before = _run(tmp_path / "before", 4, version, gdal_layout=True, monkeypatch=monkeypatch)
        after = _run(tmp_path / "after", 4, version)
        assert after.path.read_bytes() == before.path.read_bytes()
        assert after.mask_path.read_bytes() == before.mask_path.read_bytes()

    def test_four_bands_differ_from_version_3_in_values_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        before = _run(tmp_path / "before", 4, 3, gdal_layout=True, monkeypatch=monkeypatch)
        after = _run(tmp_path / "after", 4, 4)
        assert _profile_of(after.path) == _profile_of(before.path)
        assert after.mask_path.read_bytes() == before.mask_path.read_bytes()
        with rasterio.open(before.path) as one, rasterio.open(after.path) as two:
            old, new = one.read(masked=True), two.read(masked=True)
        assert old.shape == new.shape
        assert old[0].tobytes() != new[0].tobytes()  # band 1 is the band version 4 fixes
        assert numpy.nanmax(numpy.abs(old.filled(numpy.nan)[0] - new.filled(numpy.nan)[0])) < 0.05

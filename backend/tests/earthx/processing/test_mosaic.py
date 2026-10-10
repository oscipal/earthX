"""The mosaic of one overpass in the core, on synthetic scenes over two UTM zones (M4-12a).

Scene A and B are two tiles of zone 32 on one grid, overlapping by a kilometre; scene C is a
tile of zone 33 that overlaps B's east edge and reaches past it. The values of each scene are a
ramp around a base of its own (1 000, 20 000, 40 000), so that the winner of a pixel can be
read off its value. Everything is served through the real `readers` (``sources.serve``).
"""

from __future__ import annotations

import contextlib
import logging
import threading
from pathlib import Path

import numpy
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin
from rio_cogeo.cogeo import cog_translate, cog_validate
from rio_cogeo.profiles import cog_profiles
from shapely.geometry import box, mapping

from earthx.processing import RunCancelled, run
from earthx.processing import core as core_module
from earthx.processing.errors import AoiOutsideInputs, UnsupportedRecipe
from earthx.processing.mosaic import mosaic_order, target_crs
from earthx.processing.plan import DISK_RESERVE_BYTES, disk_needed
from earthx.processing.recipe import recipe_from_data
from earthx.processing.source import Source
from tests.conftest import own_log_text
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import resolved
from tests.earthx.processing.testops import OPERATORS

ZONE_32, ZONE_33 = "EPSG:32632", "EPSG:32633"
ROWS = 300
BASES = {"A": 1000, "B": 20000, "C": 40000}
SCALE_2 = {"op": "scale", "op_version": 1, "params": {"factor": 2.0}}

#: B reaches 1 000 m (100 px) into A, and C starts 1 000 m before B's east edge. C's origin is
#: the zone-33 coordinate of that point, rounded to the pixel.
_TO_33 = Transformer.from_crs(ZONE_32, ZONE_33, always_xy=True)
_C_X, _C_Y = (round(value / 10) * 10 for value in _TO_33.transform(sources.ORIGIN_X + 6000.0, sources.ORIGIN_Y - 1500.0))

#: item → (CRS, origin x, origin y, width, height)
GEOMETRY = {
    "A": (ZONE_32, sources.ORIGIN_X, sources.ORIGIN_Y, 400, ROWS),
    "B": (ZONE_32, sources.ORIGIN_X + 3000.0, sources.ORIGIN_Y, 400, ROWS),
    "C": (ZONE_33, float(_C_X), float(_C_Y), 300, 200),
}


def _ramp(item: str, width: int, height: int) -> numpy.ndarray:
    rows, cols = numpy.indices((height, width))
    return (BASES[item] + (3 * rows + cols) % 5000).astype("uint16")


def _cog(path: Path, item: str, *, resolution: float = 10.0, scale: float | None = sources.SCALE) -> Path:
    crs, x, y, width, height = GEOMETRY[item]
    width, height = round(width * 10 / resolution), round(height * 10 / resolution)
    plain = path.with_suffix(".plain.tif")
    profile = {
        "driver": "GTiff", "dtype": "uint16", "count": 1, "height": height, "width": width, "crs": crs,
        "transform": from_origin(x, y, resolution, resolution), "nodata": 0,
    }  # fmt: skip
    with rasterio.open(plain, "w", **profile) as destination:
        destination.write(_ramp(item, width, height), 1)
        if scale is not None:
            destination.scales, destination.offsets = (scale,), (sources.OFFSET,)
    cog_profile = cog_profiles.get("deflate")
    cog_profile.update({"blockxsize": 256, "blockysize": 256})
    cog_translate(plain, path, cog_profile, overview_resampling="nearest", quiet=True)
    plain.unlink()
    return path


@pytest.fixture(scope="module")
def scenes(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("mosaic-scenes")
    return {item: _cog(root / f"{item}.tif", item) for item in "ABC"}


@pytest.fixture
def served(scenes: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return sources.serve({sources.url(f"{item}_red"): path for item, path in scenes.items()}, monkeypatch)


def _everything() -> dict:
    """An AOI around all three scenes, in EPSG:4326."""
    corners = []
    for item in "ABC":
        crs, x, y, width, height = GEOMETRY[item]
        to_4326 = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        corners += [to_4326.transform(x, y), to_4326.transform(x + width * 10, y - height * 10)]
    lons, lats = zip(*corners, strict=True)
    return mapping(box(min(lons) - 0.01, min(lats) - 0.01, max(lons) + 0.01, max(lats) + 0.01))


def _recipe(items: list[str], *, steps: list | None = None, scale: float | None = sources.SCALE, **overrides) -> dict:
    entries = []
    for item in items:
        entry = resolved(item, "red", href=sources.url(f"{item}_red"), scale=scale, offset=sources.OFFSET if scale else None)
        entry["asset"]["crs"] = GEOMETRY[item][0]
        entries.append(entry)
    data = {
        "recipe_version": 1,
        "inputs": [{"name": "s2", "dataset": "synthetic", "groups": [list(items)], "assets": ["red"], "resolved": entries}],
        "aoi": _everything(),
        "steps": steps or [],
        "output": {"kind": "raster", "format": "cog", "dtype": "float32"},
    }
    data.update(overrides)
    return data


def _run(data: dict, workdir: Path, progress=lambda done, total: None):
    return run(recipe_from_data(data, OPERATORS), workdir=workdir, progress=progress, operators=OPERATORS)


def _at(dataset: rasterio.DatasetReader, data: numpy.ma.MaskedArray, x: float, y: float) -> float | None:
    """The value at a zone-32 point (metres), or ``None`` where the mosaic is masked there."""
    if dataset.crs != ZONE_32:
        x, y = Transformer.from_crs(ZONE_32, dataset.crs, always_xy=True).transform(x, y)
    row, col = dataset.index(x, y)
    return None if data.mask[0, row, col] else float(data[0, row, col])


def _physical(base_value: float) -> float:
    return float(numpy.float32(base_value) * numpy.float32(sources.SCALE) + numpy.float32(sources.OFFSET))


def _scene_of(value: float | None) -> str | None:
    """Which scene a physical value came from (the bases differ by far more than the ramp)."""
    if value is None:
        return None
    raw = round((value - sources.OFFSET) / sources.SCALE)
    return "A" if raw < 10000 else ("B" if raw < 30000 else "C")


@pytest.mark.usefixtures("served")
class TestAMosaicOverTwoZones:
    def test_the_grid_is_the_zone_most_scenes_share(self, tmp_path: Path) -> None:
        result = _run(_recipe(["A", "B", "C"]), tmp_path)
        assert result.meta.crs == ZONE_32
        assert result.properties["proj:code"] == ZONE_32
        assert result.properties["earthx:resampled"] is True
        assert result.properties["processing:lineage"] == "mosaic of 3 scenes"
        assert cog_validate(str(result.path), quiet=True)[0]
        with rasterio.open(result.path) as dataset:
            assert dataset.transform.a == 10.0 and dataset.bounds.left == sources.ORIGIN_X
            assert dataset.bounds.right >= sources.ORIGIN_X + 9000

    def test_the_first_scene_in_the_list_wins_where_scenes_overlap(self, tmp_path: Path) -> None:
        result = _run(_recipe(["A", "B", "C"]), tmp_path)
        with rasterio.open(result.path) as dataset:
            data = dataset.read(masked=True)
            x0, y0 = sources.ORIGIN_X, sources.ORIGIN_Y
            assert _scene_of(_at(dataset, data, x0 + 1000, y0 - 1500)) == "A"
            assert _scene_of(_at(dataset, data, x0 + 3500, y0 - 1500)) == "A"  # A ∩ B
            assert _scene_of(_at(dataset, data, x0 + 5500, y0 - 1500)) == "B"
            assert _scene_of(_at(dataset, data, x0 + 6500, y0 - 2500)) == "B"  # B ∩ C
            assert _scene_of(_at(dataset, data, x0 + 8000, y0 - 2500)) == "C"  # C alone, warped
            assert _at(dataset, data, x0 + 8000, y0 - 200) is None  # no scene reaches here

    def test_a_scene_on_the_grid_is_copied_not_resampled(self, tmp_path: Path) -> None:
        result = _run(_recipe(["A", "B", "C"]), tmp_path)
        with rasterio.open(result.path) as dataset:
            data = dataset.read(1, masked=True)
            expected = numpy.ma.masked_all(data.shape, dtype="float32")
            for item in ("B", "A"):  # the list is A, B: A is laid last, over B
                _, x, y, width, height = GEOMETRY[item]
                row, col = dataset.index(x + 5, y - 5)
                raw = _ramp(item, width, height).astype("float32")
                expected[row : row + height, col : col + width] = raw * numpy.float32(sources.SCALE) + numpy.float32(
                    sources.OFFSET
                )
            on_grid = ~expected.mask
            on_grid[:, dataset.index(sources.ORIGIN_X + 6050, 0)[1] :] &= False  # leave out what C may take
            # a pixel is the source's, not a neighbour's: equal up to the last digit of float32 arithmetic
            numpy.testing.assert_allclose(data.filled(-1)[on_grid], expected.filled(-2)[on_grid], rtol=0, atol=1e-6)

    def test_the_warped_scene_keeps_the_values_of_its_source(self, tmp_path: Path) -> None:
        result = _run(_recipe(["A", "B", "C"]), tmp_path)
        with rasterio.open(result.path) as dataset:
            data = dataset.read(1, masked=True)
            _, x, y, width, height = GEOMETRY["C"]
            to_32 = Transformer.from_crs(ZONE_33, ZONE_32, always_xy=True)
            ex, ey = to_32.transform(x + 2000, y - 1500)  # a point well inside C
            assert ex > sources.ORIGIN_X + 7000  # past B
            row, col = dataset.index(ex, ey)
            raw = round((float(data[row, col]) - sources.OFFSET) / sources.SCALE)
            assert raw in set(_ramp("C", width, height).ravel().tolist())  # nearest: a value C has

    def test_the_list_decides_not_the_scene(self, tmp_path: Path) -> None:
        result = _run(_recipe(["B", "A"]), tmp_path)
        with rasterio.open(result.path) as dataset:
            data = dataset.read(masked=True)
            assert _scene_of(_at(dataset, data, sources.ORIGIN_X + 3500, sources.ORIGIN_Y - 1500)) == "B"

    def test_the_first_scene_gives_the_zone(self, tmp_path: Path) -> None:
        result = _run(_recipe(["C", "B", "A"]), tmp_path)
        assert result.meta.crs == ZONE_33
        with rasterio.open(result.path) as dataset:
            data = dataset.read(masked=True)
            assert _scene_of(_at(dataset, data, sources.ORIGIN_X + 8000, sources.ORIGIN_Y - 2500)) == "C"
            assert _scene_of(_at(dataset, data, sources.ORIGIN_X + 6500, sources.ORIGIN_Y - 2500)) == "C"  # C ∩ B

    def test_the_steps_run_on_the_mosaic_and_the_scaling_applies_to_every_scene(self, tmp_path: Path) -> None:
        result = _run(_recipe(["A", "B", "C"], steps=[SCALE_2]), tmp_path)
        assert result.properties["processing:lineage"] == "mosaic of 3 scenes; scaled by 2.0"
        with rasterio.open(result.path) as dataset:
            data = dataset.read(masked=True)
            value = _at(dataset, data, sources.ORIGIN_X + 1000, sources.ORIGIN_Y - 1500)
            assert value is not None
            row, col = dataset.index(sources.ORIGIN_X + 1000, sources.ORIGIN_Y - 1500)
            raw = float(_ramp("A", 400, ROWS)[row - dataset.index(sources.ORIGIN_X + 5, sources.ORIGIN_Y - 5)[0],
                                              col - dataset.index(sources.ORIGIN_X + 5, sources.ORIGIN_Y - 5)[1]])
            assert value == pytest.approx(2 * _physical(raw), rel=1e-6)

    def test_the_mask_follows_the_aoi_and_covers_the_scenes(self, tmp_path: Path) -> None:
        result = _run(_recipe(["A", "B", "C"]), tmp_path)
        with rasterio.open(result.path) as data, rasterio.open(result.mask_path) as mask:
            assert (data.width, data.height, data.transform) == (mask.width, mask.height, mask.transform)
            assert mask.read(1).min() == 1  # the AOI reaches around every scene


@pytest.mark.usefixtures("served")
class TestTheBlocks:
    def test_the_block_size_does_not_change_the_result(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        (tmp_path / "big").mkdir()
        (tmp_path / "small").mkdir()
        big = _run(_recipe(["A", "B", "C"]), tmp_path / "big")
        monkeypatch.setattr(core_module, "BLOCK_SIZE", 128)
        small = _run(_recipe(["A", "B", "C"]), tmp_path / "small")
        assert small.blocks > big.blocks
        with rasterio.open(big.path) as a, rasterio.open(small.path) as b:
            numpy.testing.assert_array_equal(a.read(masked=True).filled(-1), b.read(masked=True).filled(-1))

    def test_a_scene_that_a_filled_block_does_not_need_is_not_read(
        self, tmp_path: Path, scenes: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """B lies wholly inside A: the first scene fills every block, so B is never read."""
        reads: list[str] = []
        original = Source.read

        def counting(self, window, grid=None):  # type: ignore[no-untyped-def]
            reads.append(self.entry.asset.item_id)
            return original(self, window, grid)

        monkeypatch.setattr(Source, "read", counting)
        GEOMETRY["D"] = (ZONE_32, sources.ORIGIN_X + 500.0, sources.ORIGIN_Y - 500.0, 100, 100)
        BASES["D"] = 20000
        try:
            small = _cog(tmp_path / "D.tif", "D")
            sources.serve(
                {sources.url("A_red"): scenes["A"], sources.url("D_red"): small}, monkeypatch
            )
            data = _recipe(["A", "D"])
            data["aoi"] = mapping(box(*_bounds_4326("A")))
            monkeypatch.setattr(core_module, "BLOCK_SIZE", 128)
            _run(data, tmp_path)
        finally:
            del GEOMETRY["D"], BASES["D"]
        assert reads.count("A") > 0
        assert reads.count("D") == 0


def _bounds_4326(item: str) -> tuple[float, float, float, float]:
    crs, x, y, width, height = GEOMETRY[item]
    to_4326 = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    left, bottom = to_4326.transform(x + 5, y - height * 10 + 5)
    right, top = to_4326.transform(x + width * 10 - 5, y - 5)
    return left, bottom, right, top


@pytest.mark.usefixtures("served")
class TestAMosaicThatCannotBeRun:
    def test_scenes_with_another_scaling_are_refused_by_name(
        self, tmp_path: Path, scenes: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both the item and the file of B say 0.0002: each is consistent, together they are no one scaling."""
        other = _cog(tmp_path / "B2.tif", "B", scale=0.0002)
        sources.serve({sources.url("A_red"): scenes["A"], sources.url("B_red"): other}, monkeypatch)
        data = _recipe(["A", "B"])
        data["inputs"][0]["resolved"][1]["bands"][0]["scale"] = 0.0002
        work = tmp_path / "work"
        work.mkdir()
        with pytest.raises(UnsupportedRecipe, match="scale 'red' differently"):
            _run(data, work)
        assert list(work.iterdir()) == []

    def test_a_zarr_mosaic_over_two_crs_is_refused_before_anything_is_read(self, tmp_path: Path) -> None:
        data = _recipe(["A", "C"])
        for entry in data["inputs"][0]["resolved"]:
            entry["asset"]["reader"] = "zarr"
            entry["asset"]["variable"] = "red"
            entry["scaling"] = "item"
        with pytest.raises(UnsupportedRecipe, match="one CRS"):
            _run(data, tmp_path)

    def test_several_groups_stay_refused(self, tmp_path: Path) -> None:
        data = _recipe(["A", "B"])
        data["inputs"][0]["groups"] = [["A"], ["B"]]
        with pytest.raises(UnsupportedRecipe, match="one group"):
            _run(data, tmp_path)

    def test_a_cancel_in_the_middle_leaves_nothing_behind(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(core_module, "BLOCK_SIZE", 128)

        def stop(done: int, total: int) -> None:
            if done == 5:
                raise RunCancelled("stop")

        with pytest.raises(RunCancelled):
            _run(_recipe(["A", "B", "C"]), tmp_path, stop)
        assert list(tmp_path.iterdir()) == []

    def test_an_aoi_that_no_scene_reaches_is_refused(self, tmp_path: Path) -> None:
        data = _recipe(["A", "B"])
        data["aoi"] = mapping(box(2.0, 2.0, 2.01, 2.01))
        with pytest.raises(AoiOutsideInputs):
            _run(data, tmp_path)

    def test_the_log_names_counts_only(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="earthx.processing"):
            _run(_recipe(["A", "B", "C"]), tmp_path)
        text = " ".join(own_log_text(record) for record in caplog.records)
        assert "scenes" in text
        for marker in (sources.HOST, "A_red", "c1:", "coordinates"):
            assert marker not in text


class TestTheOrderOfAnOverpass:
    def test_the_crs_most_scenes_have_is_the_target(self) -> None:
        crs = {"T1": ZONE_33, "T2": ZONE_32, "T3": ZONE_33}
        assert target_crs(crs) == ZONE_33

    def test_a_tie_goes_to_the_smaller_epsg_number_whatever_the_order(self) -> None:
        forward = {"T1": ZONE_33, "T2": ZONE_32}
        backward = {"T2": ZONE_32, "T1": ZONE_33}
        assert target_crs(forward) == target_crs(backward) == ZONE_32

    def test_scenes_in_the_target_come_first_each_part_by_id(self) -> None:
        crs = {"Z": ZONE_32, "B": ZONE_33, "A": ZONE_33, "Y": ZONE_32, "C": ZONE_33}
        assert mosaic_order(crs) == ["A", "B", "C", "Y", "Z"]

    def test_the_order_asked_for_does_not_matter(self) -> None:
        crs = {"A": ZONE_33, "B": ZONE_32, "C": ZONE_32, "D": ZONE_33}
        assert mosaic_order(crs) == mosaic_order(dict(reversed(list(crs.items())))) == ["B", "C", "A", "D"]

    def test_scenes_without_a_crs_are_the_others_when_some_name_one(self) -> None:
        assert mosaic_order({"A": None, "B": ZONE_32, "C": ZONE_32}) == ["B", "C", "A"]

    def test_no_crs_at_all_is_a_plain_order_by_id(self) -> None:
        assert target_crs({"B": None, "A": None}) is None
        assert mosaic_order({"B": None, "A": None}) == ["A", "B"]


@pytest.mark.usefixtures("served")
def test_the_work_directory_stays_within_what_the_supervisor_checked(tmp_path: Path) -> None:
    """The disk check of M4-11a (``disk_needed``) holds for a mosaic: the peak is below need minus reserve."""
    data = _recipe(["A", "B", "C"])
    recipe = recipe_from_data(data, OPERATORS)
    peak = 0
    done = threading.Event()

    def watch() -> None:
        nonlocal peak
        while not done.is_set():
            size = 0
            for path in tmp_path.iterdir():
                with contextlib.suppress(OSError):
                    size += path.stat().st_size
            peak = max(peak, size)

    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    try:
        run(recipe, workdir=tmp_path, progress=lambda done_, total: None, operators=OPERATORS)
    finally:
        done.set()
        watcher.join()
    assert 0 < peak <= disk_needed(recipe, OPERATORS) - DISK_RESERVE_BYTES


def test_the_need_does_not_grow_with_the_scenes_but_with_the_area() -> None:
    one = disk_needed(recipe_from_data(_recipe(["A"]), OPERATORS), OPERATORS)
    three = disk_needed(recipe_from_data(_recipe(["A", "B", "C"]), OPERATORS), OPERATORS)
    assert one == three  # the same AOI and the same bands: the same output


class TestTheRuleOfTheExport:
    """The export job and the mosaic job apply one rule to one list: the same scene wins (F3)."""

    @staticmethod
    def _flat(path: Path, x: float, value: int, gap: slice) -> Path:
        """A one-band ``uint8`` tile of zone 32 with one value, nodata in the columns of ``gap``."""
        data = numpy.full((ROWS, 400), value, dtype="uint8")
        data[:, gap] = 0
        plain = path.with_suffix(".plain.tif")
        profile = {
            "driver": "GTiff", "dtype": "uint8", "count": 1, "height": ROWS, "width": 400, "crs": ZONE_32,
            "transform": from_origin(x, sources.ORIGIN_Y, 10.0, 10.0), "nodata": 0,
        }  # fmt: skip
        with rasterio.open(plain, "w", **profile) as destination:
            destination.write(data, 1)
        cog_translate(plain, path, cog_profiles.get("deflate"), quiet=True)
        plain.unlink()
        return path

    def _recipes(self, items: list[str], output: dict, footprints: bool) -> dict:
        entries = []
        for item in items:
            entry = resolved(item, "red", href=sources.url(f"{item}_red"), scale=None, offset=None)
            entry["bands"] = [{"data_type": "uint8", "nodata": 0, "scale": None, "offset": None}]
            entries.append(entry)
        entry = {"name": "input", "dataset": "synthetic", "groups": [items], "assets": ["red"], "resolved": entries}
        if footprints:
            to_4326 = Transformer.from_crs(ZONE_32, "EPSG:4326", always_xy=True).transform
            from shapely.ops import transform as shapely_transform

            x0 = {"A": sources.ORIGIN_X, "B": sources.ORIGIN_X + 3000.0}
            entry["footprints"] = {
                item: mapping(
                    shapely_transform(
                        to_4326, box(x0[item], sources.ORIGIN_Y - ROWS * 10, x0[item] + 4000, sources.ORIGIN_Y)
                    )
                )
                for item in items
            }
        aoi = mapping(box(*_bounds_4326("A")[:2], *_bounds_4326("B")[2:]))
        return {
            "recipe_version": 1, "inputs": [entry], "aoi": aoi, "steps": [], "output": output,
        }  # fmt: skip

    @pytest.mark.parametrize("items", [["A", "B"], ["B", "A"]])
    def test_the_same_scene_wins_at_the_same_places(
        self, items: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from earthx.processing.export import Attachments
        from tests.earthx.processing.recipes import CROP

        files = {
            sources.url("A_red"): self._flat(tmp_path / "a.tif", sources.ORIGIN_X, 111, gap=slice(300, 350)),
            sources.url("B_red"): self._flat(tmp_path / "b.tif", sources.ORIGIN_X + 3000.0, 222, gap=slice(0, 0)),
        }
        sources.serve(files, monkeypatch)
        mosaic_dir, export_dir = tmp_path / "mosaic", tmp_path / "export"
        mosaic_dir.mkdir()
        export_dir.mkdir()
        raster = {"kind": "raster", "format": "cog", "dtype": "uint8"}
        mosaic = run(
            recipe_from_data(self._recipes(items, raster, footprints=False), OPERATORS),
            workdir=mosaic_dir, progress=lambda done, total: None, operators=OPERATORS,
        )  # fmt: skip
        attachments = Attachments(
            files={"ATTRIBUTION.txt": "x", "citation.bib": "x", "aoi.geojson": "{}"}, attribution=("synthetic",)
        )
        export = run(
            recipe_from_data(self._recipes(items, dict(CROP), footprints=True) | {"recipe_id": "R" * 22}, OPERATORS),
            workdir=export_dir, progress=lambda done, total: None, operators=OPERATORS, attachments=attachments,
        )  # fmt: skip
        import zipfile

        with zipfile.ZipFile(export.path) as archive:
            (export_dir / "red.tif").write_bytes(archive.read("red.tif"))
        # points of a zone-32 line: A alone, in A's gap that B fills, in A ∩ B where A has data, B alone
        probes = {"a-only": 601000.0, "gap": 603250.0, "overlap": 603750.0, "b-only": 606000.0}
        winners = {}
        for name, path in (("mosaic", mosaic.path), ("export", export_dir / "red.tif")):
            with rasterio.open(path) as dataset:
                data = dataset.read(1)
                for label, x in probes.items():
                    px, py = Transformer.from_crs(ZONE_32, dataset.crs, always_xy=True).transform(
                        x, sources.ORIGIN_Y - 1500.0
                    )
                    row, col = dataset.index(px, py)
                    winners[name, label] = int(data[row, col])
        for label in probes:
            assert winners["mosaic", label] == winners["export", label], label
        # and the rule itself: B fills A's gap, and where both have data the first scene of the list wins
        assert winners["mosaic", "a-only"] == 111
        assert winners["mosaic", "gap"] == 222
        assert winners["mosaic", "overlap"] == {"A": 111, "B": 222}[items[0]]
        assert winners["mosaic", "b-only"] == 222

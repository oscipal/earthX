"""DS-03c (Otto, 05.11.2026, on #293): the scenes of a pass are read in parallel, each inside its own ``enter(path)``, and a pass
that runs past its time ends cleanly with every reader freed.

Synthetic COGs on disk; ``enter`` stands in for the slot of a host and the GDAL environment, and records what runs at once.
"""

from __future__ import annotations

import threading
import time
import warnings
from contextlib import contextmanager
from pathlib import Path

import numpy
import pytest
import rasterio
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.transform import from_origin

from earthx.access import aoi_clouds
from earthx.access.aoi_clouds import READ_DEADLINE, ReadDeadlineExceeded, measure_aoi_clouds, measure_aoi_pass
from earthx.readers.cog import AssetPath

CRS = "EPSG:32632"
ORIGIN_X, ORIGIN_Y, PIXEL, SIZE = 500_000.0, 5_500_000.0, 20.0, 512
CLOUDS = frozenset({8, 9, 10})
TO_LONLAT = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)


def _scene(path: Path, value: int, left: float = 0.0) -> AssetPath:
    profile = {
        "driver": "GTiff", "dtype": "uint8", "count": 1, "height": SIZE, "width": SIZE, "crs": CRS,
        "transform": from_origin(ORIGIN_X + left, ORIGIN_Y, PIXEL, PIXEL), "nodata": 0, "tiled": True,
        "blockxsize": 256, "blockysize": 256,
    }
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with rasterio.open(path, "w", **profile) as destination:
            destination.write(numpy.full((SIZE, SIZE), value, dtype="uint8"), 1)
        with rasterio.open(path, "r+") as destination:
            destination.build_overviews([2, 4, 8, 16], Resampling.mode)
    return AssetPath(str(path), dataset_id="synthetic", item_id=path.stem, asset="scl")


def _aoi(x: float, y: float, side: float) -> dict:
    corners = [(x, y), (x + side, y), (x + side, y + side), (x, y + side), (x, y)]
    return {"type": "Polygon", "coordinates": [[list(TO_LONLAT.transform(ORIGIN_X + cx, ORIGIN_Y - cy)) for cx, cy in corners]]}


@pytest.fixture
def scenes(tmp_path: Path) -> list[AssetPath]:
    return [_scene(tmp_path / f"s{n}.tif", 4 + n, left=n * SIZE * PIXEL / 3) for n in range(4)]


class Recorder:
    """``enter(path)``: how many readings are inside at once, and that every one that went in came out."""

    def __init__(self, pause: float = 0.05) -> None:
        self.pause = pause
        self.inside = self.peak = self.entered = self.left = 0
        self.lock = threading.Lock()

    @contextmanager
    def __call__(self, path: AssetPath):
        with self.lock:
            self.inside += 1
            self.entered += 1
            self.peak = max(self.peak, self.inside)
        try:
            time.sleep(self.pause)
            yield
        finally:
            with self.lock:
                self.inside -= 1
                self.left += 1


class TestParallel:
    def test_the_scenes_are_read_at_once(self, scenes: list[AssetPath]) -> None:
        recorder = Recorder()
        measure_aoi_pass(scenes, _aoi(1_000, 1_000, 6_000), CLOUDS, enter=recorder)
        assert recorder.peak == len(scenes)

    def test_one_reader_at_a_time_is_the_other_way_round(self, scenes: list[AssetPath], monkeypatch: pytest.MonkeyPatch) -> None:
        """Gegenprobe: with one reader the peak is one, and the counts are the same."""
        aoi = _aoi(1_000, 1_000, 6_000)
        parallel = measure_aoi_pass(scenes, aoi, CLOUDS, enter=Recorder(0))
        monkeypatch.setattr(aoi_clouds, "PASS_READERS", 1)
        recorder = Recorder()
        one = measure_aoi_pass(scenes, aoi, CLOUDS, enter=recorder)
        assert recorder.peak == 1 and one == parallel

    def test_it_is_faster_than_one_after_the_other_where_each_read_waits(self, scenes: list[AssetPath], monkeypatch: pytest.MonkeyPatch) -> None:
        aoi = _aoi(1_000, 1_000, 6_000)
        started = time.monotonic()
        measure_aoi_pass(scenes, aoi, CLOUDS, enter=Recorder(0.2))
        together = time.monotonic() - started
        monkeypatch.setattr(aoi_clouds, "PASS_READERS", 1)
        started = time.monotonic()
        measure_aoi_pass(scenes, aoi, CLOUDS, enter=Recorder(0.2))
        one_by_one = time.monotonic() - started
        assert together < one_by_one * 0.6

    def test_the_counts_do_not_depend_on_the_readers(self, scenes: list[AssetPath], monkeypatch: pytest.MonkeyPatch) -> None:
        aoi = _aoi(1_000, 1_000, 8_000)
        monkeypatch.setattr(aoi_clouds, "PASS_CHUNK", 16)
        small = measure_aoi_pass(scenes, aoi, CLOUDS, enter=Recorder(0))
        monkeypatch.setattr(aoi_clouds, "PASS_CHUNK", 2048)
        assert measure_aoi_pass(scenes, aoi, CLOUDS) == small

    def test_every_reading_that_went_in_comes_out_when_one_fails(self, scenes: list[AssetPath], tmp_path: Path) -> None:
        recorder = Recorder(0)
        missing = AssetPath(str(tmp_path / "missing.tif"), dataset_id="synthetic", item_id="missing", asset="scl")
        with pytest.raises(rasterio.errors.RasterioIOError):
            measure_aoi_pass([*scenes[:2], missing], _aoi(1_000, 1_000, 6_000), CLOUDS, enter=recorder)
        assert recorder.entered == recorder.left and recorder.inside == 0


class TestTheDeadline:
    def test_a_pass_past_its_time_ends_with_every_reader_freed(self, scenes: list[AssetPath]) -> None:
        recorder = Recorder(0)
        token = READ_DEADLINE.set(time.monotonic() - 1.0)
        try:
            with pytest.raises(ReadDeadlineExceeded):
                measure_aoi_pass(scenes, _aoi(1_000, 1_000, 6_000), CLOUDS, enter=recorder)
        finally:
            READ_DEADLINE.reset(token)
        assert recorder.entered == recorder.left and recorder.inside == 0

    def test_a_pass_in_time_is_read(self, scenes: list[AssetPath]) -> None:
        token = READ_DEADLINE.set(time.monotonic() + 30.0)
        try:
            assert measure_aoi_pass(scenes, _aoi(1_000, 1_000, 6_000), CLOUDS).data_pixels > 0
        finally:
            READ_DEADLINE.reset(token)

    def test_a_pass_that_runs_out_of_time_between_two_blocks_stops_there(self, scenes: list[AssetPath], monkeypatch: pytest.MonkeyPatch) -> None:
        """Each block of the grid takes a little; the time runs out in the middle and the next block is not read."""
        monkeypatch.setattr(aoi_clouds, "PASS_CHUNK", 16)
        recorder = Recorder(0.02)
        token = READ_DEADLINE.set(time.monotonic() + 0.15)
        try:
            with pytest.raises(ReadDeadlineExceeded):
                measure_aoi_pass(scenes, _aoi(500, 500, 9_000), CLOUDS, enter=recorder)
        finally:
            READ_DEADLINE.reset(token)
        assert recorder.entered == recorder.left
        # Gegenprobe: the same pass without a limit reads on to the end, with many more readings.
        free = Recorder(0)
        measure_aoi_pass(scenes, _aoi(500, 500, 9_000), CLOUDS, enter=free)
        assert free.entered > recorder.entered

    def test_a_scene_past_its_time_stops_between_two_blocks(self, scenes: list[AssetPath]) -> None:
        token = READ_DEADLINE.set(time.monotonic() - 1.0)
        try:
            with pytest.raises(ReadDeadlineExceeded):
                measure_aoi_clouds(scenes[0], _aoi(1_000, 1_000, 6_000), CLOUDS)
        finally:
            READ_DEADLINE.reset(token)
        assert measure_aoi_clouds(scenes[0], _aoi(1_000, 1_000, 6_000), CLOUDS).data_pixels > 0, "no limit, no stop"

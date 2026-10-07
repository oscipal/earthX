"""The child process of one run (adr/0013 §5.3, §6.2, §8 point 11; plan M4-08a §3.5).

What the child loads, how it speaks over the pipe, and a real run of the core in it on a
synthetic scene, with the same two seams the core's own tests use.
"""

from __future__ import annotations

import json
import multiprocessing
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from rio_cogeo.cogeo import cog_validate

import earthx.jobs as jobs_package
from earthx.jobs.child import high_water_mb
from tests.earthx.jobs import child_targets
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import resolved

FORBIDDEN = ("psycopg", "psycopg_pool", "asyncpg", "botocore", "boto3", "earthx.objectstore")
SIZE = 512


def _start(context: str, target: Callable[..., None], *args: Any) -> tuple[multiprocessing.process.BaseProcess, Any]:
    ctx = multiprocessing.get_context(context)
    parent, child = ctx.Pipe(duplex=True)
    process = ctx.Process(target=target, args=(*args, child))
    process.start()
    child.close()
    return process, parent


def _messages(process: multiprocessing.process.BaseProcess, parent: Any, timeout: float = 90) -> list[tuple]:
    """Everything the child sends until it closes its end; then the child is joined."""
    received = []
    while parent.poll(timeout):
        try:
            received.append(parent.recv())
        except EOFError:
            break
    process.join(timeout)
    assert not process.is_alive()
    return received


class TestWhatTheChildLoads:
    """The reverse of tests/earthx/processing/test_import_is_pure.py: not the core alone, but the child as `jobs` starts it."""

    def test_a_spawned_child_has_no_database_pool_object_store_or_supervisor(self) -> None:
        process, parent = _start("spawn", child_targets.probe_modules)
        (method, loaded), *rest = _messages(process, parent)
        assert rest == [] and method == "spawn"
        assert "earthx.jobs.child" in loaded and "earthx.processing.core" in loaded
        offenders = [name for name in loaded if name.split(".")[0] in FORBIDDEN or name.startswith(FORBIDDEN)]
        assert offenders == []
        supervisor = [
            name
            for name in loaded
            if name
            in {
                "earthx.jobs.worker",
                "earthx.jobs.queue",
                "earthx.jobs.submit",
                "earthx.jobs.cleanup",
                "earthx.jobs.main",
            }
        ]
        assert supervisor == []

    def test_counter_sample_a_forked_child_inherits_the_database_driver(self) -> None:
        """M9 of adr/0013: `fork` carried psycopg into the child. If this stops seeing it, the check above proves nothing."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)  # fork in a process with threads
            process, parent = _start("fork", child_targets.probe_modules)
            (method, loaded), *_ = _messages(process, parent)
        assert method == "fork"
        assert "psycopg" in loaded

    def test_the_package_imports_nothing_so_importing_the_child_does_not_load_the_supervisor(self) -> None:
        init = Path(jobs_package.__file__)
        assert [line for line in init.read_text().splitlines() if line.startswith(("import ", "from "))] == []


class TestPeak:
    def test_the_peak_is_vmhwm_of_this_process_in_mb(self) -> None:
        assert high_water_mb() > 10
        before = high_water_mb()
        block = bytearray(150 * 1024 * 1024)
        block[::4096] = b"x" * len(block[::4096])  # touch the pages
        assert high_water_mb() >= before + 100
        del block
        assert high_water_mb() >= before + 100, "a high-water mark does not fall"


def _scene(tmp_path: Path) -> Path:
    return sources.build_band_cog(tmp_path / "scene.tif", sources.ramp(SIZE, SIZE, 1200))


def _recipe_json(href: str | None = None) -> str:
    entry = resolved("ITEM_BIG", "big", href=href or sources.url("big"))
    data = {
        "recipe_version": 1,
        "inputs": [
            {"name": "s2", "dataset": "synthetic", "groups": [["ITEM_BIG"]], "assets": ["big"], "resolved": [entry]}
        ],
        "aoi": sources.whole(SIZE, SIZE),
        "steps": [],
        "output": {"kind": "raster", "format": "cog", "dtype": "float32"},
    }
    return json.dumps(data)


def _run_real_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, recipe: str, *, cancel: bool = False
) -> tuple[list[tuple], Path]:
    workdir = tmp_path / "run"
    workdir.mkdir()
    (workdir / "recipe.json").write_text(recipe)
    monkeypatch.setenv("CHILD_COG", str(_scene(tmp_path)))
    process, parent = _start("spawn", child_targets.end_to_end, str(workdir))
    if cancel:
        parent.send("cancel")
    return _messages(process, parent), workdir


class TestARealRun:
    def test_the_child_runs_the_recipe_and_leaves_result_and_mask(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        messages, workdir = _run_real_child(tmp_path, monkeypatch, _recipe_json())
        kinds = [message[0] for message in messages]
        assert kinds[-1] == "done" and kinds.count("done") == 1 and set(kinds[:-1]) == {"progress"}
        done = messages[-1][1]
        assert (workdir / "result.tif").is_file() and (workdir / "mask.tif").is_file()
        assert cog_validate(str(workdir / "result.tif"))[0]
        assert (done["width"], done["height"], done["bands"]) == (SIZE, SIZE, 1)
        assert done["bytes"] == (workdir / "result.tif").stat().st_size
        assert done["blocks"] >= 1 and done["valid_pixels"] > 0

    def test_progress_counts_blocks_and_carries_the_peak(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        messages, _ = _run_real_child(tmp_path, monkeypatch, _recipe_json())
        progress = [message for message in messages if message[0] == "progress"]
        assert progress and [(m[1], m[2]) for m in progress][-1][0] == progress[-1][2]
        assert all(m[3] > 0 for m in progress)

    def test_the_peak_of_the_whole_child_stays_under_the_limit_of_m4_07a(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """M4-07a F11: 500 MB per child, measured as VmHWM and as in the image, without boto3."""
        messages, _ = _run_real_child(tmp_path, monkeypatch, _recipe_json())
        peak = messages[-1][1]["peak_mb"]
        assert 100 < peak < 500, peak

    def test_what_the_child_reports_about_the_result_names_no_address_and_no_coordinate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        messages, _ = _run_real_child(tmp_path, monkeypatch, _recipe_json())
        text = json.dumps(messages[-1][1])
        assert sources.HOST not in text and "https://" not in text and "ITEM_BIG" not in text
        assert "coordinates" not in text

    def test_a_cancel_message_stops_the_run_at_the_next_block_and_removes_the_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        messages, workdir = _run_real_child(tmp_path, monkeypatch, _recipe_json(), cancel=True)
        assert messages[-1] == ("failed", "cancelled")
        assert sorted(path.name for path in workdir.iterdir()) == ["recipe.json"]


class TestEveryFailureIsNamedAndNothingElseLeaves:
    def test_a_recipe_that_does_not_validate(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        messages, _ = _run_real_child(tmp_path, monkeypatch, json.dumps({"recipe_version": 2}))
        assert messages == [("failed", "recipe_invalid")]

    def test_text_that_is_not_json(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        messages, _ = _run_real_child(tmp_path, monkeypatch, "not json {")
        assert messages == [("failed", "recipe_invalid")]

    def test_an_address_the_gateway_refuses(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        messages, _ = _run_real_child(tmp_path, monkeypatch, _recipe_json("https://127.0.0.1/ITEM_BIG/big.tif"))
        assert messages == [("failed", "rejected")]

    def test_a_missing_recipe_file_is_unknown_and_gives_no_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        workdir = tmp_path / "empty"
        workdir.mkdir()
        monkeypatch.setenv("CHILD_COG", str(_scene(tmp_path)))
        process, parent = _start("spawn", child_targets.end_to_end, str(workdir))
        assert _messages(process, parent) == [("failed", "unknown")]

    def test_a_memory_error_is_named_out_of_memory(self, tmp_path: Path) -> None:
        process, parent = _start("spawn", child_targets.run_out_of_memory, str(tmp_path))
        assert _messages(process, parent) == [("progress", 1, 2, 1.0), ("failed", "out_of_memory")]
        assert process.exitcode == 0, "the child reported it and ended by itself; nothing was killed"

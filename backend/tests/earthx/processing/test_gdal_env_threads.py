"""The GDAL options of `readers` hold in every reading thread (adr/0014 §3.6, §7.3 point 2).

Entered in the main thread, ``rasterio.Env`` sets them process-wide; entered in any
other thread, only for that thread. So ``worker_environment()`` refuses any thread
but the main one, and ``run`` enters the options itself on the thread that reads.
Both checked with ``rasterio._env.get_gdal_config``, as in the measurement §17.8.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from rasterio._env import get_gdal_config

from earthx.processing import run, worker_environment
from earthx.processing import source as source_module
from earthx.processing.recipe import recipe_from_data
from earthx.readers import process_gdal_options
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import resolved
from tests.earthx.processing.testops import OPERATORS

OPTIONS = ("GDAL_HTTP_TIMEOUT", "GDAL_DISABLE_READDIR_ON_OPEN", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS", "GDAL_CACHEMAX")


def _seen() -> dict[str, str]:
    # `get_gdal_config` hands back a number for a numeric value; compare as text.
    return {name: str(get_gdal_config(name)) for name in OPTIONS}


EXPECTED = {name: str(process_gdal_options()[name]) for name in OPTIONS}


@pytest.fixture(autouse=True)
def nothing_set_beforehand() -> None:
    assert get_gdal_config("GDAL_DISABLE_READDIR_ON_OPEN") is None


def test_worker_environment_reaches_threads_started_after_it() -> None:
    with worker_environment(), ThreadPoolExecutor(max_workers=2) as pool:
        seen = list(pool.map(lambda _: _seen(), range(4)))
    assert seen == [EXPECTED] * 4


def test_worker_environment_refuses_any_thread_but_the_main_one() -> None:
    def enter() -> None:
        with worker_environment():
            pass

    with ThreadPoolExecutor(max_workers=1) as pool, pytest.raises(RuntimeError, match="main thread"):
        pool.submit(enter).result()


def test_run_reads_under_the_options_from_a_pool_thread_without_worker_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cog = sources.build_band_cog(tmp_path / "red.tif", sources.ramp(64, 64, 1200))
    sources.serve({sources.url("red"): cog}, monkeypatch)
    seen: list[dict[str, object]] = []
    original = source_module.Source.read

    def probe(self, window, grid=None):
        seen.append(_seen())
        return original(self, window, grid)

    monkeypatch.setattr(source_module.Source, "read", probe)
    data = {
        "recipe_version": 1,
        "inputs": [
            {
                "name": "s2",
                "dataset": "synthetic",
                "groups": [["ITEM_A"]],
                "assets": ["red"],
                "resolved": [resolved("ITEM_A", "red", href=sources.url("red"))],
            }
        ],
        "aoi": sources.whole(64, 64),
        "steps": [],
        "output": {"kind": "raster", "format": "cog", "dtype": "float32"},
    }
    recipe = recipe_from_data(data, OPERATORS)
    work = tmp_path / "work"
    work.mkdir()
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(run, recipe, workdir=work, progress=lambda done, total: None, operators=OPERATORS).result()
    assert seen and all(entry == EXPECTED for entry in seen)
    assert get_gdal_config("GDAL_DISABLE_READDIR_ON_OPEN") is None

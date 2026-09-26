"""Repeated real downloads, every file read back (M3-22, stress test with bounded runtime).

The scenario is the one that went red in the CI of #86
(`test_a_slanted_aoi_masks_agree_and_values_are_near_identical`): a slanted
AOI over the synthetic COG, once through the windowed path inside a full ZIP,
once through the whole-array path. It runs many times in one process, because
the old failure depended on what the process allocated in between, and each
round reads every file back with its ``MemoryFile`` held by a ``with``.

``EARTHX_DOWNLOAD_STRESS_RUNS`` raises the count for a local measurement
(plan m3-22: 500); the default keeps the CI run to a few seconds.
"""

from __future__ import annotations

import os
import time
import zipfile
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest

from earthx.access import download as dl
from earthx.access.tiles import open_asset
from earthx.catalog.datasets import SENTINEL_2_L2A
from tests.earthx.access.test_download_mask import (
    ITEM,
    _asset,
    _diamond_aoi,
    _open_bytes,
    _open_zip_member,
    _rectangle_aoi,
)
from tests.earthx.readers import mini_cog

RUNS = int(os.environ.get("EARTHX_DOWNLOAD_STRESS_RUNS", "50"))
# The CI budget for the default count; measured at under 2 s in the cloud session.
BUDGET_SECONDS = 30.0


@pytest.fixture(scope="module")
def cog_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return mini_cog.build_mini_cog(tmp_path_factory.mktemp("cog") / "mini.tif")


@pytest.fixture
def served(cog_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return mini_cog.serve_cog(cog_path, monkeypatch)


def _one_round(aoi_geometry: dict) -> None:
    zip_bytes = dl.build_download_zip(
        config=SENTINEL_2_L2A,
        open_reader=open_asset,
        crops=[dl.AssetCrop(asset="visual", paths=(_asset(),))],
        aoi_geometry=aoi_geometry,
        item_ids=[ITEM],
    )
    image = dl.crop_asset(open_asset, (_asset(),), aoi_geometry)
    naive_bytes = dl._masked_array_to_cog_bytes(image.array, image.transform, image.crs, image.nodata)
    with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
        assert archive.testzip() is None
    with (
        _open_zip_member(zip_bytes, "visual.tif") as windowed,
        _open_zip_member(zip_bytes, "visual_mask.tif") as mask,
        _open_bytes(naive_bytes) as naive,
    ):
        assert windowed.shape == naive.shape == mask.shape
        assert (windowed.dataset_mask() == naive.dataset_mask()).mean() > 0.99
        assert np.abs(windowed.read().astype(int) - naive.read().astype(int)).mean() < 1.0
        assert set(np.unique(mask.read(1))) <= {0, 1}


def test_repeated_downloads_always_read_back(served: list[str]) -> None:
    started = time.perf_counter()
    for run in range(RUNS):
        _one_round(_diamond_aoi() if run % 2 == 0 else _rectangle_aoi())
    elapsed = time.perf_counter() - started
    if RUNS <= 50:
        assert elapsed < BUDGET_SECONDS, f"{RUNS} rounds took {elapsed:.1f} s"

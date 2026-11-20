"""Fixtures of the processing tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def memory_scene(tmp_path_factory: pytest.TempPathFactory) -> Callable[..., Path]:
    """The scene of ``test_memory_8192.build_scene`` at ``size``² with ``bands`` bands, made once per process (M5-61 §3.2).

    The memory tests of reproject, mask and normalize measure the same scenes; they are seeded, so one file serves all of
    them. Only read, never written to.
    """
    from tests.earthx.processing.test_memory_8192 import build_scene

    root = tmp_path_factory.mktemp("memory-scenes")
    made: dict[tuple[int, int], Path] = {}

    def scene(size: int, bands: int = 2) -> Path:
        if (size, bands) not in made:
            made[(size, bands)] = build_scene(root / f"scene-{size}-{bands}.tif", size, bands=bands)
        return made[(size, bands)]

    return scene

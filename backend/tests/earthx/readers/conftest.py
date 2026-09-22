"""The synthetic store of `mini_zarr.py`, as pytest fixtures.

The store is written once per test module and served through the reader's own
gateway seam; `mini_zarr.serve_store` says what that does and why nothing here can
reach a network.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from tests.earthx.readers.mini_zarr import build_mini_zarr, serve_store


@pytest.fixture(scope="module")
def store_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The store on disk, written once per test module by the script that builds it."""
    return build_mini_zarr(tmp_path_factory.mktemp("zarr") / "mini.zarr")


@pytest.fixture
def serve(monkeypatch: pytest.MonkeyPatch) -> Callable[[Path], list[httpx.Request]]:
    """Put a store directory behind the reader's gateway; returns its request log."""

    def serve_root(root: Path) -> list[httpx.Request]:
        return serve_store(root, monkeypatch)

    return serve_root


@pytest.fixture
def requests(store_root: Path, serve: Callable[[Path], list[httpx.Request]]) -> list[httpx.Request]:
    """Every request the reader made against the mini store, in order."""
    return serve(store_root)

"""A flaky read of the whole scene must not become a false verdict (M3-03 review).

``/statistics`` is the one route that reads a dataset's *whole* extent in a single
call (``.preview()``, no window — ``access.tiles._read_statistics``), which touches
far more scattered blocks over ``vsicurl`` than a tile or the AOI crop ever do
(both always read a small window). Two things made a real occurrence of this
harder to diagnose than it had to be, and both are checked here against a real
synthetic COG (``readers/mini_cog.py``) opened by the real ``CogReader``/GDAL, with
only the reader's first call(s) made to fail — no network:

* a single transient ``RasterioIOError`` failed the whole request instead of
  being retried, even though this route's own oversized read makes hitting one
  more likely than the small reads everywhere else do;
* the app-level handler mapped *every* ``RasterioError`` — not just a real read
  failure — to "the asset could not be read from the source", which would hide a
  genuine code-level bug behind the same message a real upstream failure gets.

Every test below failed before the fix (see the PR) except the happy path, which
is a plain regression guard against the retry loop itself — a failure can happen
at the open or partway through the read, so both are covered.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from rasterio.errors import RasterioError, RasterioIOError

from earthx.access.tiles import EarthxTilerFactory, open_asset
from earthx.api.tiler import _rasterio_error, _rasterio_io_error
from earthx.readers.cog import AssetPath
from tests.earthx.readers.mini_cog import build_mini_cog


class _FailsToOpen:
    """A context manager that raises before yielding anything.

    Stands in for GDAL failing to fetch one of the many scattered blocks a
    full-extent decimated read touches, without needing a real, unreliable
    network to produce one.
    """

    def __init__(self, error: Exception) -> None:
        self._error = error

    def __enter__(self) -> "_FailsToOpen":
        raise self._error

    def __exit__(self, *exc_info: object) -> bool:
        return False


class FlakyReader:
    """``open_asset``, except the first ``fail_first`` calls raise ``error``.

    Every later call opens the real synthetic COG for real — the point is that a
    fix has to *recover*, not merely detect the failure. Fails at *open*, one of
    the two places a real read can fail; :class:`FlakyPreviewReader` below covers
    the other.
    """

    def __init__(self, *, fail_first: int, error: Exception | None = None) -> None:
        self.fail_first = fail_first
        self.error = error or RasterioIOError("simulated: a block of the asset could not be fetched")
        self.calls = 0

    def __call__(self, src_path: Any, **reader_params: Any) -> Any:
        self.calls += 1
        if self.calls <= self.fail_first:
            return _FailsToOpen(self.error)
        return open_asset(src_path, **reader_params)


class _OpensFineFailsOnPreview:
    """A real, opened reader whose ``preview()`` raises ``error`` if ``should_fail()``
    still says so — a fresh instance is built per attempt, but the failure count is
    the *reader's* to track, not this wrapper's (a retry opens a new one of these).

    Stands in for a block fetch failing *after* the file opened successfully —
    the far more likely place for one of the many scattered blocks a full-extent
    decimated read touches to fail, as against :class:`_FailsToOpen` above, which
    only covers the open itself.
    """

    def __init__(self, real: Any, *, should_fail: Any, error: Exception) -> None:
        self._real = real
        self._should_fail = should_fail
        self._error = error

    def __enter__(self) -> "_OpensFineFailsOnPreview":
        self._src_dst = self._real.__enter__()
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return self._real.__exit__(*exc_info)

    def preview(self, *args: Any, **kwargs: Any) -> Any:
        if self._should_fail():
            raise self._error
        return self._src_dst.preview(*args, **kwargs)


class FlakyPreviewReader:
    """``open_asset``, except the *first* reader it hands back fails its ``preview()``.

    The open always succeeds; only the read after it does not, once.
    """

    def __init__(self) -> None:
        self.calls = 0
        self._failed_once = False

    def _should_fail(self) -> bool:
        if self._failed_once:
            return False
        self._failed_once = True
        return True

    def __call__(self, src_path: Any, **reader_params: Any) -> Any:
        self.calls += 1
        real = open_asset(src_path, **reader_params)
        error = RasterioIOError("simulated: a block failed partway through the read")
        return _OpensFineFailsOnPreview(real, should_fail=self._should_fail, error=error)


@pytest.fixture
def local_cog(tmp_path: Path) -> AssetPath:
    """A real, local, overviewed COG (`readers/mini_cog.py`) — no network."""
    path = build_mini_cog(tmp_path / "mini.tif")
    return AssetPath(str(path), dataset_id="d", item_id="i", asset="visual")


def _client(path: AssetPath, reader: Any) -> TestClient:
    """The real statistics route and the real exception mapping, around a reader
    a test controls — the same shape ``test_tiles.py`` builds its client in, but
    with a reader that actually opens something instead of one that is faked away.
    """
    factory = EarthxTilerFactory(
        reader=reader,
        path_dependency=lambda: path,
        environment_dependency=lambda: {},
        stats_cache_dependency=lambda: None,
        name="tiles",
    )
    app = FastAPI()
    app.include_router(factory.router)
    app.add_exception_handler(RasterioIOError, _rasterio_io_error)
    app.add_exception_handler(RasterioError, _rasterio_error)
    return TestClient(app)


def test_the_happy_path_is_unaffected(local_cog: AssetPath) -> None:
    reader = FlakyReader(fail_first=0)
    response = _client(local_cog, reader).get("/statistics")

    assert response.status_code == 200
    assert reader.calls == 1


def test_one_transient_read_failure_is_retried_and_recovers(local_cog: AssetPath) -> None:
    reader = FlakyReader(fail_first=1)
    response = _client(local_cog, reader).get("/statistics")

    assert response.status_code == 200
    assert reader.calls == 2, "the retry must open a fresh reader, not reuse the failed one"


def test_a_read_failure_that_never_recovers_is_still_reported_as_unreadable(local_cog: AssetPath) -> None:
    """The retry is bounded: a real, persistent failure is still a 502 with the
    same message as before — not silence, and not retried forever."""
    reader = FlakyReader(fail_first=99)
    response = _client(local_cog, reader).get("/statistics")

    assert response.status_code == 502
    assert response.json()["detail"] == "the asset could not be read from the source"
    assert reader.calls == 2, "retried exactly once, not forever"


def test_a_failure_partway_through_the_read_is_also_retried_and_recovers(local_cog: AssetPath) -> None:
    """The open can succeed and the read still fail — a fresh reader per attempt
    covers that too, not only a reader that never opened at all."""
    reader = FlakyPreviewReader()
    response = _client(local_cog, reader).get("/statistics")

    assert response.status_code == 200
    assert reader.calls == 2, "the retry must open a fresh reader, not retry .preview() on the failed one"


def test_a_non_io_rasterio_error_is_not_reported_as_unreadable(local_cog: AssetPath) -> None:
    """`RasterioError` is not only about the source being unreachable — GDAL
    raises it for a request it could not process, too. The asset is never even
    fetched here (`fail_first` covers every call), so a message claiming it
    "could not be read from the source" would be false."""
    reader = FlakyReader(
        fail_first=99,
        error=RasterioError("unsupported resampling algorithm for this driver"),
    )
    response = _client(local_cog, reader).get("/statistics")

    assert response.status_code == 500
    assert response.json() == {"detail": "the asset could not be processed"}
    assert reader.calls == 1, "a non-I/O error is not worth retrying"

"""Nothing the object store does leaves a key or a signature in the log (adr/0015 §9.2).

At DEBUG, `botocore` writes the access key id, the canonical request and the
signature (§3.2); `configure_logging` raises it to WARNING. The counter-check
shows that the capture would see them otherwise.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from earthx.logging import configure_logging
from earthx.objectstore.results import Store, lifecycle_ok, new_result_id, signed_download, upload_result

from .conftest import ACCESS_KEY, SECRET_KEY

LEAKS = (ACCESS_KEY, SECRET_KEY, "X-Amz-Signature", "Signature=")


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.text: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.text.append(f"{record.name} {record.getMessage()}")


@pytest.fixture
def debug_log() -> Iterator[_Capture]:
    """`configure_logging(DEBUG)`, then a capture on the root logger; restored afterwards."""
    root = logging.getLogger()
    previous_level, previous_handlers = root.level, list(root.handlers)
    capture = _Capture()
    configure_logging(logging.DEBUG)
    root.addHandler(capture)
    try:
        yield capture
    finally:
        root.handlers = previous_handlers
        root.setLevel(previous_level)
        for name in ("botocore", "urllib3"):
            logging.getLogger(name).setLevel(logging.NOTSET)


def _use_the_store(store: Store, tmp_path: Path) -> None:
    path = tmp_path / "recipe.json"
    path.write_text("{}")
    result_id = new_result_id()
    upload_result(store, result_id, "recipe.json", path)
    signed_download(
        store, result_id, "recipe.json", not_after=datetime.now(UTC) + timedelta(days=1), filename="recipe.json"
    )
    lifecycle_ok(store)


def test_at_debug_nothing_secret_is_logged(store: Store, tmp_path: Path, debug_log: _Capture) -> None:
    _use_the_store(store, tmp_path)
    logged = "\n".join(debug_log.text)
    for leak in LEAKS:
        assert leak not in logged


def test_the_capture_would_see_botocore_at_debug(store: Store, tmp_path: Path, debug_log: _Capture) -> None:
    logging.getLogger("botocore").setLevel(logging.DEBUG)
    _use_the_store(store, tmp_path)
    logged = "\n".join(debug_log.text)
    assert ACCESS_KEY in logged

"""What the child of a pyramid build says about its own failure (M5-30b, Otto 15.11.2026).

The supervisor logs the kind, the step, the exception class, a short reason and the tile as ``z/x/y``; the reason has every
URL and path taken out, and a lookup error has none (its message is the key, which can be an item's id).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from rasterio.errors import RasterioIOError

from earthx.jobs import overview_child
from earthx.jobs.overview_child import failure_detail
from earthx.processing import overview_build


class Pipe:
    def __init__(self) -> None:
        self.sent: list[Any] = []

    def send(self, message: Any) -> None:
        self.sent.append(message)

    def close(self) -> None:
        pass


def test_the_detail_names_step_class_reason_and_tile() -> None:
    error = RasterioIOError("HTTP response code: 503")
    setattr(error, overview_build.TILE_ATTRIBUTE, "6/33/22")
    assert failure_detail(error, "build") == {
        "step": "build",
        "error": "RasterioIOError",
        "reason": "HTTP response code: 503",
        "tile": "6/33/22",
    }


@pytest.mark.parametrize(
    "text",
    [
        "HTTP response code on /vsicurl/https://bucket.example.invalid/some/Item_N46E007.tif: 503",
        "cannot open https://bucket.example.invalid/some/Item_N46E007.tif",
        "no such file /tmp/overview-build/tiles/6/33/22.tif",
        "CURL error: Could not resolve host bucket.example.invalid for s3://bucket.example.invalid/key.tif",
    ],
)
def test_no_url_and_no_path_is_in_the_reason(text: str) -> None:
    reason = failure_detail(RasterioIOError(text), "build")["reason"]
    for forbidden in ("example.invalid", "Item_N46E007", "/tmp", "overview-build", "/vsicurl", "://", "key.tif"):
        assert forbidden not in reason, reason
    assert "<address>" in reason


def test_a_lookup_error_has_no_reason_because_its_message_is_a_key_that_can_be_an_item_id() -> None:
    assert failure_detail(KeyError("ESA_WorldCover_10m_2020_v100_N00E006"), "build")["reason"] == ""
    assert failure_detail(IndexError("list index out of range"), "build")["reason"] == ""


def test_the_reason_is_short_and_one_line() -> None:
    reason = failure_detail(ValueError("a\n" * 500), "plan")["reason"]
    assert len(reason) <= 160 and "\n" not in reason


def test_a_failure_without_a_tile_names_none() -> None:
    assert "tile" not in failure_detail(ValueError("no items"), "plan")


def test_the_child_sends_kind_and_detail_for_a_failure_in_the_build_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / overview_build.JOB_NAME).write_text(json.dumps({"dataset_id": "x", "mode": "build"}))

    def broken(workdir: Path, progress: Any, **_: Any) -> None:
        error = RasterioIOError("Cannot open /vsicurl/https://bucket.example.invalid/a.tif: unsupported layout")
        setattr(error, overview_build.TILE_ATTRIBUTE, "4/8/5")
        raise error

    monkeypatch.setattr(overview_build, "build_pyramid", broken)
    monkeypatch.setattr(overview_child, "configure_logging", lambda: None)
    pipe = Pipe()
    overview_child.run_child(str(tmp_path), pipe)
    ((tag, kind, detail),) = pipe.sent
    assert (tag, kind) == ("failed", "unknown")
    assert detail == {"step": "build", "error": "RasterioIOError", "reason": "Cannot open <address> unsupported layout", "tile": "4/8/5"}


def test_a_child_that_cannot_read_its_job_says_the_step_it_never_got_to() -> None:
    pipe = Pipe()
    overview_child.run_child("/nonexistent-work-directory", pipe)
    ((tag, _, detail),) = pipe.sent
    assert tag == "failed" and detail["step"] == "start" and "nonexistent" not in detail["reason"]


class TestThePipePacer:
    """M5-37: the child asks the supervisor for each turn; it knows no database."""

    class Answering(Pipe):
        def __init__(self, answer: Any) -> None:
            super().__init__()
            self.answer = answer

        def recv(self) -> Any:
            return self.answer

    def test_a_turn_is_asked_for_and_waited_for(self) -> None:
        pipe = self.Answering(("go",))
        overview_child.PipePacer(pipe).wait("bucket.example.org")
        assert pipe.sent == [("pace", "bucket.example.org")]

    @pytest.mark.parametrize("answer", [("stop",), "go", ("go", 1), None])
    def test_any_other_answer_stops_the_read(self, answer: Any) -> None:
        with pytest.raises(RuntimeError):
            overview_child.PipePacer(self.Answering(answer)).wait("bucket.example.org")

    def test_an_account_says_requests_and_how_the_read_ended(self) -> None:
        pipe = Pipe()
        pacer = overview_child.PipePacer(pipe)
        pacer.account("bucket.example.org", 4)
        pacer.account("bucket.example.org", 2, failed=True, retry_after=7.0)
        assert pipe.sent == [
            ("account", "bucket.example.org", 4, False, None),
            ("account", "bucket.example.org", 2, True, 7.0),
        ]


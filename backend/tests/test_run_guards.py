"""The guards of a test run itself (M5-61 §3.1): `logging` put back after each test, and a warning on a full disk."""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest

from earthx.logging import configure_logging
from tests.conftest import LOW_DISK_BYTES, low_disk_warning
from tests.logging_guard import COLLECTING, CONFIGURED, LoggingGuard, _own, summary

NAME = "earthx.m561.guard"


@pytest.fixture
def probe() -> Iterator[logging.Logger]:
    logger = logging.getLogger(NAME)
    yield logger
    logger.setLevel(logging.NOTSET)
    logger.propagate, logger.disabled, logger.handlers = True, False, []


def test_a_level_propagate_disabled_and_a_handler_are_put_back_and_noted(probe: logging.Logger) -> None:
    guard = LoggingGuard()
    handler = logging.NullHandler()
    probe.setLevel(logging.DEBUG)
    probe.propagate, probe.disabled = False, True
    probe.addHandler(handler)
    assert guard.restore("t::one") == [NAME]
    assert (probe.level, probe.propagate, probe.disabled, probe.handlers) == (logging.NOTSET, True, False, [])
    assert guard.changed == [("t::one", [NAME])]


def test_the_root_logger_and_logging_disable_are_put_back() -> None:
    guard = LoggingGuard()
    root = logging.getLogger()
    level, handlers = root.level, list(root.handlers)
    stray = logging.StreamHandler()
    root.setLevel(logging.INFO)
    root.addHandler(stray)
    logging.disable(logging.CRITICAL)
    assert guard.restore("t::two") == ["logging.disable", "root"]
    assert root.level == level and stray not in root.handlers and root.handlers == handlers
    assert logging.root.manager.disable == logging.NOTSET


def test_pytests_own_capture_handler_is_left_where_it_is(caplog: pytest.LogCaptureFixture) -> None:
    root = logging.getLogger()
    guard = LoggingGuard()
    root.setLevel(logging.ERROR)
    guard.restore("t::three")
    assert caplog.handler in root.handlers
    logging.getLogger(NAME).warning("still captured")
    assert "still captured" in caplog.text


def test_a_logger_made_after_the_start_is_kept_as_first_seen(probe: logging.Logger) -> None:
    fresh = logging.getLogger(NAME + ".fresh")
    guard = LoggingGuard()
    later = logging.getLogger(NAME + ".later")
    later.setLevel(logging.WARNING)  # as a library might when imported
    guard.learn()
    assert guard.restore("t::four") == []
    later.setLevel(logging.DEBUG)
    fresh.setLevel(logging.DEBUG)
    assert sorted(guard.restore("t::four")) == [NAME + ".fresh", NAME + ".later"]
    assert (later.level, fresh.level) == (logging.WARNING, logging.NOTSET)
    later.setLevel(logging.NOTSET)


def test_without_a_note_it_is_put_back_all_the_same(probe: logging.Logger) -> None:
    guard = LoggingGuard()
    probe.setLevel(logging.DEBUG)
    assert guard.restore("t::five", note=False) == [NAME]
    assert probe.level == logging.NOTSET
    assert guard.changed == []


def test_configure_logging_is_named_as_such_and_put_back() -> None:
    guard = LoggingGuard()
    root = logging.getLogger()
    level, handlers = root.level, _own(root.handlers)
    configure_logging()
    assert CONFIGURED in guard.restore("t::six")
    # `configure_logging` drops pytest's capture handlers too; pytest adds them again for the next phase.
    assert root.level == level and _own(root.handlers) == handlers


def test_tests_that_only_built_an_app_are_one_line_with_their_number() -> None:
    changed = [
        ("a.py::t1", [CONFIGURED]),
        ("a.py::t2", [CONFIGURED]),
        ("b.py::t1", [CONFIGURED]),
        ("b.py::t2", [CONFIGURED, "httpx"]),
        (COLLECTING, [CONFIGURED]),
    ]
    assert summary(changed) == [
        f"b.py::t2: httpx, {CONFIGURED}",
        f"{COLLECTING}: {CONFIGURED}",
        "configure_logging of an app the test built: 3 tests in 2 files",
    ]


def test_the_summary_names_each_test_once_whichever_worker_saw_it() -> None:
    changed = [(COLLECTING, ["root"]), ("t::a", ["x", "root"]), (COLLECTING, ["root"])]
    assert summary(changed) == ["t::a: root, x", f"{COLLECTING}: root"]


@pytest.mark.parametrize("free", [0, LOW_DISK_BYTES - 1])
def test_too_little_free_space_is_named_with_the_directory_and_what_to_do(free: int) -> None:
    warning = low_disk_warning("/tmp", free)
    assert warning is not None
    assert "/tmp" in warning and "pytest-of-" in warning


def test_enough_free_space_says_nothing() -> None:
    assert low_disk_warning("/tmp", LOW_DISK_BYTES) is None

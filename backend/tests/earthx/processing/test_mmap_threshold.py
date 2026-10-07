"""``worker_environment()`` fixes glibc's mmap threshold for the worker process (M4-10b)."""

from __future__ import annotations

import ctypes
import logging
import platform

import pytest

from earthx.processing import core, worker_environment


@pytest.mark.skipif(platform.libc_ver()[0] != "glibc", reason="the image runs on glibc")
def test_glibc_takes_the_threshold() -> None:
    assert core._fix_mmap_threshold() is True


def test_it_asks_for_the_mmap_threshold_and_nothing_else(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    class Glibc:
        @staticmethod
        def mallopt(option: int, value: int) -> int:
            calls.append((option, value))
            return 1

    monkeypatch.setattr(core.ctypes, "CDLL", lambda name: Glibc())
    assert core._fix_mmap_threshold() is True
    assert calls == [(-3, 128 * 1024)]  # M_MMAP_THRESHOLD in glibc's malloc.h


def test_worker_environment_sets_it(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(core, "_fix_mmap_threshold", lambda: calls.append(True))
    with worker_environment():
        assert calls == [True]


def test_without_glibc_nothing_happens_and_the_worker_still_starts(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def no_glibc(name: str) -> ctypes.CDLL:
        raise OSError(f"{name}: cannot open shared object file")

    monkeypatch.setattr(core.ctypes, "CDLL", no_glibc)
    assert core._fix_mmap_threshold() is False
    with caplog.at_level(logging.WARNING, logger="earthx.processing"), worker_environment():
        pass
    assert [record.getMessage() for record in caplog.records] == ["mmap threshold left to the C library"]


def test_a_c_library_without_mallopt_is_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    class NoMallopt:
        def __getattr__(self, name: str) -> None:
            raise AttributeError(name)

    monkeypatch.setattr(core.ctypes, "CDLL", lambda name: NoMallopt())
    assert core._fix_mmap_threshold() is False


def test_a_refused_value_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    class Refusing:
        @staticmethod
        def mallopt(option: int, value: int) -> int:
            return 0

    monkeypatch.setattr(core.ctypes, "CDLL", lambda name: Refusing())
    assert core._fix_mmap_threshold() is False

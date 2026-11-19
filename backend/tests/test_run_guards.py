"""The guards of a test run itself (M5-61 §3.1): a warning on a full disk."""

from __future__ import annotations

import pytest

from tests.conftest import LOW_DISK_BYTES, low_disk_warning


@pytest.mark.parametrize("free", [0, LOW_DISK_BYTES - 1])
def test_too_little_free_space_is_named_with_the_directory_and_what_to_do(free: int) -> None:
    warning = low_disk_warning("/tmp", free)
    assert warning is not None
    assert "/tmp" in warning and "pytest-of-" in warning


def test_enough_free_space_says_nothing() -> None:
    assert low_disk_warning("/tmp", LOW_DISK_BYTES) is None

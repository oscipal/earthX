"""What a failed run is called (plan M4-08a F1, K7; adr/0013 §5.6)."""

from __future__ import annotations

import pytest

from earthx.gateway import UpstreamError, UpstreamTimeout
from earthx.processing import failure_kind
from earthx.processing.errors import (
    AoiOutsideInputs,
    GridMismatch,
    ProcessingError,
    RecipeInvalid,
    RunCancelled,
    ScalingMismatch,
    UnknownOperator,
    UnsupportedRecipe,
    WorkfileRejected,
)
from earthx.readers import AssetRejected


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (RunCancelled(), "cancelled"),
        (MemoryError(), "out_of_memory"),
        (RecipeInvalid("a field"), "recipe_invalid"),
        (UnknownOperator("an operator"), "recipe_invalid"),
        (UnsupportedRecipe("more than one item"), "unsupported_recipe"),
        (ScalingMismatch("a band"), "scaling_mismatch"),
        (GridMismatch("two grids"), "grid_mismatch"),
        (AoiOutsideInputs("outside"), "aoi_outside_inputs"),
        (UpstreamTimeout("slow"), "source_timeout"),
        (UpstreamError(502), "source_5xx"),
        (UpstreamError(404), "source_4xx"),
        (AssetRejected("an address"), "rejected"),
    ],
)
def test_each_failure_has_its_name(error: BaseException, kind: str) -> None:
    assert failure_kind(error) == kind


@pytest.mark.parametrize(
    "error",
    [WorkfileRejected("a name"), ProcessingError("something"), ValueError("x"), KeyError("k"), OSError("disk")],
)
def test_what_nothing_recognises_is_unknown(error: BaseException) -> None:
    assert failure_kind(error) == "unknown"


def test_a_memory_error_wins_over_a_source_failure_it_hides() -> None:
    try:
        try:
            raise UpstreamTimeout("slow")
        except UpstreamTimeout as inner:
            raise MemoryError from inner
    except MemoryError as error:
        assert failure_kind(error) == "out_of_memory"


def test_the_name_never_carries_the_message() -> None:
    error = UpstreamError(503, "https://secret.example.invalid/aoi/9.0,47.0")
    kind = failure_kind(error)
    assert "secret" not in kind and "9.0" not in kind and "/" not in kind

"""What a failed run is called (adr/0013 §5.6, plan M4-08a F1, K7).

`jobs` keeps a run's ``error_kind`` and decides from it alone whether a second
attempt can help; it may not look at the exception itself (it imports neither
`gateway` nor `readers`). The child calls :func:`failure_kind` at its edge and sends
the name over the pipe. Nothing but the name leaves: no message, no address, no
coordinate.
"""

from __future__ import annotations

from earthx.processing.errors import (
    AoiOutsideInputs,
    GridMismatch,
    RecipeInvalid,
    RunCancelled,
    ScalingMismatch,
    UnsupportedRecipe,
)
from earthx.readers import source_failure_kind

__all__ = ["failure_kind"]


def failure_kind(error: BaseException) -> str:
    """One short name for ``error``; ``"unknown"`` when nothing here recognises it."""
    if isinstance(error, RunCancelled):
        return "cancelled"
    if isinstance(error, MemoryError):
        return "out_of_memory"
    if isinstance(error, RecipeInvalid):
        return "recipe_invalid"
    if isinstance(error, UnsupportedRecipe):
        return "unsupported_recipe"
    if isinstance(error, ScalingMismatch):
        return "scaling_mismatch"
    if isinstance(error, GridMismatch):
        return "grid_mismatch"
    if isinstance(error, AoiOutsideInputs):
        return "aoi_outside_inputs"
    return source_failure_kind(error) or "unknown"

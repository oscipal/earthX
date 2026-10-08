"""The named failures of `processing` (adr/0014 §4.3, §5.4, K7).

Every text is short, English and redacted: it names fields, operators and
datasets, never an address, an AOI coordinate or a recipe hash (Q8, adr/0014
§4.7). `api` turns them into status codes; `jobs` into a job's error kind.
"""

from __future__ import annotations

__all__ = [
    "AoiOutsideInputs",
    "ExportTooLarge",
    "GridMismatch",
    "ProcessingError",
    "RecipeInvalid",
    "RunCancelled",
    "ScalingMismatch",
    "UnknownOperator",
    "UnsupportedRecipe",
    "WorkfileRejected",
]


class ProcessingError(Exception):
    """Base of every refusal and failure `processing` names itself."""


class RecipeInvalid(ProcessingError, ValueError):
    """The order or recipe does not validate; the text lists fields and reasons only."""


class UnknownOperator(RecipeInvalid):
    """A step names an operator, or an ``op_version`` of it, this platform does not run."""


class UnsupportedRecipe(ProcessingError):
    """A valid recipe asks for something this core does not run yet (plan M4-07a §8, F2)."""


class ExportTooLarge(UnsupportedRecipe):
    """An export would write more than ``crop_rules.MAX_EXPORT_JOB_BYTES`` (M4-11 F5)."""


class ScalingMismatch(ProcessingError):
    """Item and file disagree on scaling, or a file carries a scaling nothing declared (§5.4)."""


class GridMismatch(ProcessingError):
    """The assets of a pixel step do not share one grid."""


class AoiOutsideInputs(ProcessingError):
    """The AOI does not overlap the inputs' rasters."""


class RunCancelled(ProcessingError):
    """Raised by the progress callback to stop a run; the core cleans up and re-raises."""


class WorkfileRejected(ProcessingError, ValueError):
    """A file name that would leave the run's work directory (plan M4-07a §8, F4)."""

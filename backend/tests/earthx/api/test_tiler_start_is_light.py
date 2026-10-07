"""The tiler's start does not load the worker core (M4-14: the intake is imported on the first crop)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[3]


def _heavy_after(statement: str) -> str:
    code = (
        f"import sys; {statement}\n"
        "print([n for n in sys.modules if n == 'earthx.api.intake' or n.startswith('earthx.processing')])\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, check=True, timeout=120
    )
    return result.stdout.strip().splitlines()[-1]


def test_importing_the_tiler_loads_neither_the_intake_nor_processing() -> None:
    assert _heavy_after("import earthx.api.tiler") == "[]"


@pytest.mark.parametrize("module", ["earthx.api.intake", "earthx.processing"])
def test_the_check_would_see_one(module: str) -> None:
    """Counter-sample: the same probe does see the module when something imports it."""
    assert _heavy_after(f"import earthx.api.tiler, {module}") != "[]"

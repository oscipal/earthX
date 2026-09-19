"""M1-02 Abnahme: lint-imports actually rejects a forbidden import.

The tests in test_module_boundaries.py only check that `.importlinter` is
*written* consistently with architekturplan.md 3.1. They would stay green
even if `lint-imports` silently ignored every contract. This test runs the
real `lint-imports` CLI against a small fixture package that deliberately
violates the "readers import only gateway" rule, exactly the shape of
mistake a helper module could make, and checks that it is caught.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "import_violation"
LINT_IMPORTS = Path(sys.executable).with_name("lint-imports")


def test_forbidden_import_in_a_helper_module_is_caught() -> None:
    env = {**os.environ, "PYTHONPATH": str(FIXTURE_ROOT)}
    result = subprocess.run(
        [
            str(LINT_IMPORTS),
            "--config",
            str(FIXTURE_ROOT / "import-violation.importlinter"),
            "--no-logo",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode != 0, result.stdout
    assert "badpkg.readers" in result.stdout
    assert "badpkg.catalog" in result.stdout

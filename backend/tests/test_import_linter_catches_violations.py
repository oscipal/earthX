"""M1-02 Abnahme: lint-imports actually rejects a forbidden import.

The tests in test_module_boundaries.py only check that `.importlinter` is
*written* consistently with architekturplan.md 3.1. They would stay green
even if `lint-imports` silently ignored every contract. This test runs the
real `lint-imports` CLI against a small fixture package that deliberately
violates the "readers import only gateway" rule, exactly the shape of
mistake a helper module could make, and checks that it is caught.

Since M4-06 it also runs the real `.importlinter` over a copy of the real
package: green as it is, with exactly one ignored import, and broken by each
import adr/0015 §3.5 and §4.2 forbid — the counter-check the plan asks for.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

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


# --- M4-06: the real contracts against a copy of the real package ---------------

REPO = Path(__file__).resolve().parents[2]


def _lint_copy(tmp_path: Path, extra: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run `lint-imports` with the real `.importlinter` over a copy of `earthx` plus `extra` files."""
    shutil.copytree(REPO / "backend" / "earthx", tmp_path / "earthx", ignore=shutil.ignore_patterns("__pycache__"))
    for relative, source in extra.items():
        (tmp_path / relative).write_text(source, encoding="utf-8")
    return subprocess.run(
        [str(LINT_IMPORTS), "--config", str(REPO / ".importlinter"), "--no-logo", "--no-cache"],
        env={**os.environ, "PYTHONPATH": str(tmp_path)},
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_the_real_contracts_hold_with_exactly_one_ignored_import(tmp_path: Path) -> None:
    result = _lint_copy(tmp_path, {})
    assert result.returncode == 0, result.stdout
    assert "(1 ignored import)" in result.stdout


@pytest.mark.parametrize(
    ("extra", "broken"),
    [
        # adr/0015 §3.5: the exception is one import, not the module.
        ({"earthx/objectstore/other.py": "import botocore\n"}, "HTTP and S3 clients live only in gateway"),
        ({"earthx/processing/bad.py": "import botocore\n"}, "HTTP and S3 clients live only in gateway"),
        ({"earthx/access/bad.py": "import earthx.objectstore.results\n"}, "access imports only readers and catalog"),
        ({"earthx/processing/bad.py": "from earthx.objectstore import errors\n"}, "the worker core reaches no object store"),
        # A chain counts for B9: `processing -> catalog -> objectstore`.
        (
            {"earthx/catalog/bad.py": "import earthx.objectstore.errors\n", "earthx/processing/uses.py": "import earthx.catalog.bad\n"},
            "the worker core reaches no object store",
        ),
        ({"earthx/objectstore/bad.py": "import earthx.catalog\n"}, "objectstore imports nothing domain-specific"),
        # M4-08a (adr/0013 §6.1): the core reaches no database driver, pool or async driver.
        ({"earthx/processing/bad.py": "import psycopg\n"}, "the worker core reaches no database"),
        ({"earthx/processing/bad.py": "import psycopg_pool\n"}, "the worker core reaches no database"),
        ({"earthx/processing/bad.py": "import asyncpg\n"}, "the worker core reaches no database"),
        (
            {"earthx/catalog/bad_db.py": "import psycopg_pool\n", "earthx/processing/uses.py": "import earthx.catalog.bad_db\n"},
            "the worker core reaches no database",
        ),
    ],
    ids=["second-botocore-in-objectstore", "botocore-in-processing", "access-uses-store", "processing-uses-store",
         "chain-via-catalog", "store-imports-catalog", "psycopg-in-processing", "pool-in-processing",
         "asyncpg-in-processing", "pool-chain-via-catalog"],
)  # fmt: skip
def test_the_real_contracts_break_on_each_forbidden_import(tmp_path: Path, extra: dict[str, str], broken: str) -> None:
    result = _lint_copy(tmp_path, extra)
    assert result.returncode != 0, result.stdout
    assert [line for line in result.stdout.splitlines() if line.startswith(broken) and " BROKEN" in line]


def test_the_shell_may_use_the_database_driver(tmp_path: Path) -> None:
    """M4 Q4: `jobs` is the shell with the queue; only `processing` is held to B9."""
    result = _lint_copy(tmp_path, {"earthx/jobs/uses_db.py": "import psycopg\n"})
    assert result.returncode == 0, result.stdout

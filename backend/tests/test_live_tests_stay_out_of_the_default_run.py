"""The live smoke test must never join the run that gates a pull request.

adr/0002 §2: T-D reaches the real source, so it runs on a schedule in GitHub Actions
and nowhere else. That property rests on one line of configuration — ``testpaths`` —
and a line of configuration with nobody watching it is exactly what moves by accident.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LIVE = REPO / "backend" / "tests_live"


def _testpaths() -> list[str]:
    config = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    return config["tool"]["pytest"]["ini_options"]["testpaths"]


def test_the_live_directory_is_there_and_holds_tests() -> None:
    """Otherwise the check below would pass by having nothing to keep out."""
    assert sorted(path.name for path in LIVE.glob("test_*.py"))


def test_a_plain_pytest_does_not_reach_the_live_directory() -> None:
    assert "backend/tests_live" not in _testpaths()
    assert all(not LIVE.is_relative_to(REPO / path) for path in _testpaths())

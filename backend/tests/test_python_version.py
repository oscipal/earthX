"""Every place that chooses the Python version chooses the same one (M3-03).

The version is set in five files that nothing ties together: the base image in
`backend/Dockerfile`, `PYTHON_VERSION` in both workflows, ruff's `target-version`
and the interpreter the SessionStart hook builds the session's venv with. A bump
that misses one of them still passes everywhere else — CI tests one version, the
image runs another, and the session a third.

Each file must name its version exactly once. A file in which the pattern finds
nothing fails instead of dropping out of the comparison: otherwise rewording a line
would quietly take it out of the check.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# Deliberately equal, not "at least": moving on to 3.13 is a task of its own, as
# this one was (docs/plans/m3-03-python-312.md).
EXPECTED = (3, 12)

WORKFLOW_VERSION = re.compile(r'^\s*PYTHON_VERSION:\s*"(\d+\.\d+)"\s*$')
SOURCES = {
    "backend/Dockerfile": re.compile(r"^FROM\s+python:(\d+\.\d+)-slim\b"),
    ".github/workflows/ci.yml": WORKFLOW_VERSION,
    ".github/workflows/live-smoke.yml": WORKFLOW_VERSION,
    "pyproject.toml": re.compile(r'^target-version\s*=\s*"py(\d)(\d+)"\s*$'),
    "scripts/setup-cloud-session.sh": re.compile(r"^PYTHON=/usr/bin/python(\d+\.\d+)\s*$"),
}


def declared_version(text: str, pattern: re.Pattern[str]) -> str:
    """The one version ``pattern`` finds in ``text``, ignoring comment lines."""
    found = set()
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        match = pattern.search(line)
        if match:
            found.add(".".join(match.groups()))
    if len(found) != 1:
        raise ValueError(f"expected exactly one Python version, found {sorted(found) or 'none'}")
    return found.pop()


def test_the_interpreter_running_the_tests_is_the_expected_one() -> None:
    assert sys.version_info[:2] == EXPECTED, (
        f"tests run on Python {sys.version_info.major}.{sys.version_info.minor}, "
        f"expected {EXPECTED[0]}.{EXPECTED[1]}; in a cloud session an old .venv is "
        "rebuilt by scripts/setup-cloud-session.sh"
    )


@pytest.mark.parametrize("path", sorted(SOURCES))
def test_every_place_names_the_expected_version(path: str) -> None:
    text = (REPO / path).read_text(encoding="utf-8")
    assert declared_version(text, SOURCES[path]) == f"{EXPECTED[0]}.{EXPECTED[1]}"


@pytest.mark.parametrize("path", [".github/workflows/ci.yml", ".github/workflows/live-smoke.yml"])
def test_no_workflow_step_names_a_version_of_its_own(path: str) -> None:
    """`PYTHON_VERSION` is only one place if every `setup-python` step reads it."""
    lines = (REPO / path).read_text(encoding="utf-8").splitlines()
    literal = [line.strip() for line in lines if "python-version:" in line and "env.PYTHON_VERSION" not in line]
    assert literal == []


class TestDeclaredVersion:
    """The reading itself, against synthetic text rather than the real files."""

    def test_a_single_declaration_is_read(self) -> None:
        assert declared_version("FROM python:3.12-slim\nWORKDIR /app\n", SOURCES["backend/Dockerfile"]) == "3.12"

    def test_the_ruff_spelling_is_read_as_a_dotted_version(self) -> None:
        assert declared_version('target-version = "py312"\n', SOURCES["pyproject.toml"]) == "3.12"

    def test_a_file_without_a_declaration_is_an_error_not_a_pass(self) -> None:
        with pytest.raises(ValueError, match="none"):
            declared_version("FROM debian:bookworm-slim\n", SOURCES["backend/Dockerfile"])

    def test_two_different_declarations_in_one_file_are_an_error(self) -> None:
        text = 'env:\n  PYTHON_VERSION: "3.12"\njobs:\n  PYTHON_VERSION: "3.11"\n'
        with pytest.raises(ValueError, match="3.11"):
            declared_version(text, WORKFLOW_VERSION)

    def test_a_commented_out_old_version_does_not_count(self) -> None:
        text = "# FROM python:3.11-slim\nFROM python:3.12-slim\n"
        assert declared_version(text, SOURCES["backend/Dockerfile"]) == "3.12"

    def test_a_python3_found_on_path_does_not_count_for_the_hook(self) -> None:
        with pytest.raises(ValueError, match="none"):
            declared_version("PYTHON=python3.12\n", SOURCES["scripts/setup-cloud-session.sh"])

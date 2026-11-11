"""The four parts of the backend tests together run every test file, each exactly once.

`scripts/ci-backend-shard.sh` says what part 1 to 4 run; the matrix of `ci.yml` starts
them. A file that belongs to no part would stay green in CI without ever running, and a
file in two parts only costs time but shows the split is wrong. The rules of the script
are read here from what it prints (`CI_SHARD_PRINT_ARGS=1`), against the files on disk.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ci-backend-shard.sh"
TESTS = REPO / "backend" / "tests"
SHARDS = (1, 2, 3, 4)


def printed_args(shard: str) -> list[str]:
    result = subprocess.run(
        [str(SCRIPT), shard], cwd=REPO, capture_output=True, text=True,
        env={"PATH": os.environ["PATH"], "CI_SHARD_PRINT_ARGS": "1"},
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.splitlines()


def files_collected_by(args: list[str]) -> set[Path]:
    """What `pytest <args>` collects, by pytest's own rule for files: `test_*.py` and `*_test.py`."""
    given = [REPO / a for a in args if not a.startswith("--")]
    ignored = [REPO / a.removeprefix("--ignore=") for a in args if a.startswith("--ignore=")]
    found: set[Path] = set()
    for path in given:
        assert path.exists(), f"{path.relative_to(REPO)} does not exist"
        found |= {path} if path.is_file() else {*path.rglob("test_*.py"), *path.rglob("*_test.py")}
    return {f for f in found if not any(f == i or i in f.parents for i in ignored)}


def all_test_files() -> set[Path]:
    return {*TESTS.rglob("test_*.py"), *TESTS.rglob("*_test.py")}


@pytest.fixture(scope="module")
def parts() -> dict[int, set[Path]]:
    return {n: files_collected_by(printed_args(str(n))) for n in SHARDS}


def test_every_test_file_runs_in_some_part(parts: dict[int, set[Path]]) -> None:
    missing = all_test_files() - set().union(*parts.values())
    assert not missing, sorted(str(f.relative_to(REPO)) for f in missing)


def test_no_test_file_runs_in_two_parts(parts: dict[int, set[Path]]) -> None:
    twice = {
        str(f.relative_to(REPO)): [n for n, files in parts.items() if f in files]
        for f in all_test_files()
        if sum(f in files for files in parts.values()) > 1
    }
    assert not twice, twice


@pytest.mark.parametrize("shard", SHARDS)
def test_no_part_is_empty(parts: dict[int, set[Path]], shard: int) -> None:
    assert parts[shard], f"part {shard} runs nothing"


def test_the_memory_tests_are_found_by_their_glob() -> None:
    """An unmatched glob stays literal in bash; pytest would then fail, and the rest part
    would ignore nothing. Part 3 has to name exactly the files that exist."""
    on_disk = sorted(f"backend/tests/earthx/processing/{f.name}" for f in (TESTS / "earthx" / "processing").glob("test_memory_*.py"))
    named = sorted(a for a in printed_args("3") if "test_memory_" in a)
    assert on_disk and named == on_disk


@pytest.mark.parametrize("shard", ["", "0", "5", "x", "1 2"])
def test_an_unknown_part_is_refused_and_runs_nothing(shard: str) -> None:
    result = subprocess.run(
        [str(SCRIPT), shard], cwd=REPO, capture_output=True, text=True,
        env={"PATH": os.environ["PATH"], "CI_SHARD_PRINT_ARGS": "1"},
    )
    assert result.returncode == 2 and result.stdout == ""
    assert "usage" in result.stderr


def test_the_rest_part_ignores_exactly_what_the_named_parts_run() -> None:
    named = [a for n in (1, 2, 3) for a in printed_args(str(n))]
    rest = printed_args("4")
    assert rest[0] == "backend/tests"
    assert sorted(a.removeprefix("--ignore=") for a in rest[1:]) == sorted(named)

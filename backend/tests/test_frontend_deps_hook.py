"""SessionStart hook: `npm ci` only runs when the lockfile actually changed (M3-24).

Before this task the hook only checked whether `frontend/node_modules` existed
(`scripts/setup-cloud-session.sh`, pre-M3-24). A `node_modules` left over from an
older session then hid a `package-lock.json` that had since grown a new
dependency — `polyclip-ts` was missing in two sessions this way (M3-11c, M3-12).

The fix lives in `scripts/lib/frontend-deps.sh`, split out from the hook itself
so the comparison can be exercised here without running Postgres, the venv, or
any other part of the hook (`scripts/setup-cloud-session.sh` only runs at all
when ``CLAUDE_CODE_REMOTE=true``).
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
LIB = REPO / "scripts" / "lib" / "frontend-deps.sh"


def deps_current(lockfile: Path, node_modules: Path, hash_file: Path) -> bool:
    """Whether ``frontend_deps_current`` reports node_modules as up to date."""
    result = subprocess.run(
        [
            "bash",
            "-c",
            f'source "{LIB}" && frontend_deps_current "$1" "$2" "$3"',
            "frontend_deps_current",
            str(lockfile),
            str(node_modules),
            str(hash_file),
        ],
        check=False,
    )
    return result.returncode == 0


def lock_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def test_a_fresh_checkout_without_node_modules_needs_install(tmp_path: Path) -> None:
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text('{"lockfileVersion": 3}')
    assert not deps_current(lockfile, tmp_path / "node_modules", tmp_path / "node_modules" / ".package-lock.sha256")


def test_node_modules_without_a_recorded_hash_needs_install(tmp_path: Path) -> None:
    """node_modules from before this task, or a failed install, has no hash file."""
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text('{"lockfileVersion": 3}')
    node_modules = tmp_path / "node_modules"
    node_modules.mkdir()
    assert not deps_current(lockfile, node_modules, node_modules / ".package-lock.sha256")


def test_a_matching_hash_is_current(tmp_path: Path) -> None:
    content = '{"lockfileVersion": 3, "packages": {}}'
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text(content)
    node_modules = tmp_path / "node_modules"
    node_modules.mkdir()
    hash_file = node_modules / ".package-lock.sha256"
    hash_file.write_text(lock_hash(content) + "\n")
    assert deps_current(lockfile, node_modules, hash_file)


def test_a_changed_lockfile_needs_install(tmp_path: Path) -> None:
    """A new dependency (e.g. polyclip-ts) changes the lockfile after the hash was recorded."""
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text('{"lockfileVersion": 3, "packages": {"polyclip-ts": {}}}')
    node_modules = tmp_path / "node_modules"
    node_modules.mkdir()
    hash_file = node_modules / ".package-lock.sha256"
    hash_file.write_text(lock_hash('{"lockfileVersion": 3, "packages": {}}') + "\n")
    assert not deps_current(lockfile, node_modules, hash_file)


def test_a_missing_lockfile_is_not_current(tmp_path: Path) -> None:
    node_modules = tmp_path / "node_modules"
    node_modules.mkdir()
    hash_file = node_modules / ".package-lock.sha256"
    hash_file.write_text("anything\n")
    assert not deps_current(tmp_path / "package-lock.json", node_modules, hash_file)


@pytest.mark.parametrize(
    ("trailing", "expected_current"),
    [
        ("", True),  # `printf` without a newline
        ("\n", True),  # `frontend_lock_hash ... > hash_file` (a `sha256sum`/`awk` pipeline)
        ("\n\n", True),  # `$(cat hash_file)` strips every trailing newline, not just one
        (" \n", False),  # trailing whitespace other than a newline is not stripped
    ],
)
def test_the_recorded_hash_comparison_strips_trailing_newlines_only(
    tmp_path: Path, trailing: str, expected_current: bool
) -> None:
    content = '{"lockfileVersion": 3}'
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text(content)
    node_modules = tmp_path / "node_modules"
    node_modules.mkdir()
    hash_file = node_modules / ".package-lock.sha256"
    hash_file.write_text(lock_hash(content) + trailing)
    assert deps_current(lockfile, node_modules, hash_file) == expected_current

"""Docs-only pull requests skip the heavy CI steps, everything else runs in full (Otto, 2026-11-06).

`scripts/ci-scope.sh` decides from the files the PR itself changes; `ci.yml` has to
use the answer in every required job. Both can go wrong silently: a job that skips on a
wrong answer stays green over broken code.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ci-scope.sh"
CI = REPO / ".github" / "workflows" / "ci.yml"
GUARD = "steps.scope.outputs.docs_only != 'true'"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


def commit(cwd: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        path = cwd / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    git(cwd, "add", "-A")
    git(cwd, "commit", "-q", "-m", "x")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A clone of a one-commit `main`, with the PR branch checked out."""
    origin = tmp_path / "origin"
    origin.mkdir()
    git(origin, "init", "-q", "-b", "main")
    commit(origin, {"docs/a.md": "a", "backend/x.py": "x"})
    work = tmp_path / "work"
    git(tmp_path, "clone", "-q", str(origin), str(work))
    git(work, "checkout", "-q", "-b", "pr")
    return work


def scope(work: Path, event: str = "pull_request", base: str = "main") -> str:
    out = work / "out.txt"
    out.write_text("")
    subprocess.run(
        [str(SCRIPT)], cwd=work, check=True, capture_output=True,
        env={
            "PATH": os.environ["PATH"], "EVENT_NAME": event, "BASE_REF": base,
            "HEAD_SHA": git(work, "rev-parse", "HEAD"), "GITHUB_OUTPUT": str(out),
        },
    )
    return out.read_text().strip()


def advance_main(work: Path, files: dict[str, str]) -> None:
    """Code lands on main in the origin, after the PR branch was cut."""
    origin = Path(git(work, "remote", "get-url", "origin"))
    commit(origin, files)


def test_only_docs_changed(repo: Path) -> None:
    commit(repo, {"docs/new.md": "n"})
    assert scope(repo) == "docs_only=true"


def test_file_outside_docs_means_full_run(repo: Path) -> None:
    commit(repo, {"docs/new.md": "n", "backend/y.py": "y"})
    assert scope(repo) == "docs_only=false"


@pytest.mark.parametrize("name", ["README.md", "docsx/a.md", ".github/workflows/ci.yml", "scripts/docs/x.sh"])
def test_lookalike_paths_are_not_docs(repo: Path, name: str) -> None:
    commit(repo, {name: "n"})
    assert scope(repo) == "docs_only=false"


def test_moving_a_file_out_of_docs_is_not_docs_only(repo: Path) -> None:
    git(repo, "mv", "docs/a.md", "a.md")
    git(repo, "commit", "-q", "-am", "move")
    assert scope(repo) == "docs_only=false"


def test_main_merged_into_a_docs_pr_leaves_it_a_docs_pr(repo: Path) -> None:
    commit(repo, {"docs/new.md": "n"})
    advance_main(repo, {"backend/code.py": "new code"})
    git(repo, "fetch", "-q", "origin", "main")
    git(repo, "merge", "-q", "--no-edit", "origin/main")
    assert scope(repo) == "docs_only=true"


def test_main_moved_on_without_merge_does_not_count(repo: Path) -> None:
    commit(repo, {"docs/new.md": "n"})
    advance_main(repo, {"backend/code.py": "new code"})
    assert scope(repo) == "docs_only=true"


def test_no_changes_means_full_run(repo: Path) -> None:
    assert scope(repo) == "docs_only=false"


@pytest.mark.parametrize("event", ["push", "workflow_dispatch", ""])
def test_other_events_always_run_in_full(repo: Path, event: str) -> None:
    commit(repo, {"docs/new.md": "n"})
    assert scope(repo, event=event) == "docs_only=false"


def test_unknown_base_branch_falls_back_to_the_full_run(repo: Path) -> None:
    commit(repo, {"docs/new.md": "n"})
    assert scope(repo, base="nope") == "docs_only=false"


def jobs() -> dict[str, dict]:
    return yaml.safe_load(CI.read_text())["jobs"]


@pytest.mark.parametrize("job", ["backend", "frontend", "import-boundaries", "compose-topology"])
def test_every_required_job_decides_first_and_skips_the_rest(job: str) -> None:
    steps = jobs()[job]["steps"]
    assert "if" not in jobs()[job], "the job itself must always run"
    assert steps[0]["uses"].startswith("actions/checkout@")
    assert steps[0]["with"]["fetch-depth"] == 0
    assert steps[1]["id"] == "scope" and steps[1]["run"] == "scripts/ci-scope.sh"
    for step in steps[2:]:
        condition = str(step.get("if", ""))
        name = step.get("name") or step.get("uses") or step.get("run")
        if step.get("name") == "Docs checks (docs-only pull request)":
            assert job == "backend" and condition == "steps.scope.outputs.docs_only == 'true'"
        elif step.get("uses", "").startswith("actions/setup-python@") and job == "backend":
            assert "if" not in step, "the docs checks of the backend job need Python"
        else:
            assert GUARD in condition, f"{job}: step '{name}' runs on docs-only PRs"


def test_docs_only_backend_job_runs_the_two_docs_checks() -> None:
    step = next(s for s in jobs()["backend"]["steps"] if s.get("name", "").startswith("Docs checks"))
    for test in ("test_plans_layout.py", "test_decision_log_format.py"):
        assert (REPO / "backend" / "tests" / test).is_file()
        assert test in step["run"]

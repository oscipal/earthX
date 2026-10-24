"""`docs/plans/` is sorted into one folder per milestone, and every link follows (DOC-01).

Plans are linked from ADRs, the decision log, code comments and each other. A plan
moved into a folder, or a link written in the old flat form, breaks silently: nothing
opens these files at runtime, so only this test notices.

Two rules:

* Directly in `docs/plans/` lie only `README.md` and the living `nach-m4-backlog.md`.
* A link of the form `plans/<file>.md` (with or without `docs/` or `../` in front)
  names a file that exists there. A link with a folder (`plans/m4/<file>.md`) is
  never the flat form and is not touched by this rule.

Files the task may not change without Otto (`CLAUDE.md`, `.github/`, `.claude/`,
`CODEOWNERS`) are left out of the scan; `PROTECTED` is the one place to drop them
again once they are updated.

The migration files are left out as well: `apply_migrations` records a checksum per
file, so editing a comment in an applied migration breaks `catalog-load` on every
existing database (#183). Their old paths stay as they are.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PLANS = REPO / "docs" / "plans"

ROOT_FILES = {"README.md", "nach-m4-backlog.md"}
PROTECTED = ("CLAUDE.md", ".github", ".claude", "CODEOWNERS")
MIGRATIONS = Path("backend/earthx/catalog/migrations")
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", "dist", ".ruff_cache", ".pytest_cache"}
SELF = Path(__file__).resolve()

FLAT_LINK = re.compile(r"(?<![A-Za-z0-9_-])plans/([A-Za-z0-9_-]+\.md)(?![A-Za-z0-9_-])")


def flat_links(text: str) -> list[str]:
    """Names of every `plans/<file>.md` in ``text`` that has no folder in between."""
    return FLAT_LINK.findall(text)


def scanned_files():
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            path = Path(root) / name
            rel = path.relative_to(REPO)
            if path == SELF or rel.parts[0] in PROTECTED or rel.name in PROTECTED:
                continue
            if MIGRATIONS in rel.parents:
                continue
            yield path


def test_only_readme_and_backlog_lie_directly_in_plans():
    stray = sorted(p.name for p in PLANS.iterdir() if p.is_file() and p.name not in ROOT_FILES)
    assert not stray, f"Move these into a milestone folder under docs/plans/: {stray}"


def test_every_milestone_folder_holds_only_plans():
    for folder in (p for p in PLANS.iterdir() if p.is_dir()):
        nested = sorted(p.name for p in folder.iterdir() if p.is_dir() or p.suffix != ".md")
        assert not nested, f"{folder.name}/ holds something other than plan files: {nested}"


def test_no_link_uses_the_old_flat_path_of_a_plan():
    broken = []
    for path in scanned_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for name in flat_links(text):
            if not (PLANS / name).is_file():
                broken.append(f"{path.relative_to(REPO)}: plans/{name}")
    assert not broken, "Links to plans in the old flat form:\n" + "\n".join(sorted(broken))


def test_the_pattern_finds_the_old_form_and_not_the_new_one():
    assert flat_links("see `docs/plans/m4-processing-kern.md` §5") == ["m4-processing-kern.md"]
    assert flat_links("see ../plans/m1-fundament.md") == ["m1-fundament.md"]
    assert flat_links("see `docs/plans/m4/m4-processing-kern.md`") == []
    assert flat_links("a new plan `docs/plans/m3-xx-<kurzname>.md` or `plans/m4-xx-*.md`") == []


def test_migration_files_are_not_scanned() -> None:
    names = {p.relative_to(REPO) for p in scanned_files()}
    assert not any(MIGRATIONS in p.parents for p in names)
    assert any(p.suffix == ".py" for p in names)

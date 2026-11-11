"""The image carries the released registry entries and never the prototype entries (M5-13 plan §3.6, adr/0024 test 4).

Docker is not available in CI's unit job or a cloud session, so the definition is read as text, like
`test_runner_image_definition.py`. The runner stage builds on `app` and so carries the same entries.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
DOCKERFILE = (BACKEND / "Dockerfile").read_text(encoding="utf-8")


def _instructions(text: str) -> list[tuple[list[str], str]]:
    """Every ``COPY`` and ``ADD`` of ``text`` as (sources, destination), in shell and JSON form, flags dropped."""
    found = []
    joined = re.sub(r"\\\n", " ", text)
    for line in joined.splitlines():
        match = re.match(r"\s*(COPY|ADD)\s+(.*)$", line, flags=re.IGNORECASE)
        if not match:
            continue
        rest = match.group(2).strip()
        words = json.loads(rest) if rest.startswith("[") else rest.split()
        words = [word for word in words if not word.startswith("--")]
        found.append((words[:-1], words[-1]))
    return found


INSTRUCTIONS = _instructions(DOCKERFILE)
COPIES = [(source, destination) for sources, destination in INSTRUCTIONS for source in sources]
IGNORED = {
    line.strip().rstrip("/")
    for line in (BACKEND / ".dockerignore").read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.startswith("#")
}


def test_the_released_entries_are_copied_to_where_the_loader_reads_them() -> None:
    assert ("catalog/datasets", "./catalog/datasets") in COPIES
    assert ("catalog/retired.yaml", "./catalog/retired.yaml") in COPIES


@pytest.mark.parametrize("name", ["places.json", "glossary.yaml", "capability_terms.yaml"])
def test_the_files_of_the_search_text_are_copied_next_to_the_entries(name: str) -> None:
    assert (f"catalog/{name}", f"./catalog/{name}") in COPIES


def _reaches_a_held_back_directory(source: str) -> bool:
    path = source.removeprefix("./").rstrip("/")
    return path in {"", ".", "*", "catalog", "catalog/*"} or path.startswith(("catalog/prototype", "catalog/candidates"))


@pytest.mark.parametrize("source", [source for source, _ in COPIES])
def test_no_copy_reaches_the_prototype_or_candidate_entries(source: str) -> None:
    assert not _reaches_a_held_back_directory(source)


@pytest.mark.parametrize(
    "instruction",
    [
        "COPY catalog/datasets catalog/prototype ./catalog/",
        'COPY ["catalog", "./catalog"]',
        "ADD catalog ./catalog",
        "COPY --chown=1:1 . /app",
        "COPY \\\n    catalog/candidates ./catalog/candidates",
    ],
)
def test_the_reading_of_the_definition_finds_every_form(instruction: str) -> None:
    sources = [source for found, _ in _instructions(instruction) for source in found]
    assert any(_reaches_a_held_back_directory(source) for source in sources)


def test_the_build_context_leaves_both_out() -> None:
    assert {"catalog/prototype", "catalog/candidates"} <= IGNORED


def test_the_loader_reads_from_the_place_the_image_copies_to() -> None:
    from earthx.catalog.datasets import CATALOG_DIR

    assert CATALOG_DIR == BACKEND / "catalog"
    assert (CATALOG_DIR / "datasets").is_dir() and (CATALOG_DIR / "retired.yaml").is_file()

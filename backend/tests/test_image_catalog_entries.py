"""The image carries the released registry entries and never the prototype entries (M5-13 plan §3.6, adr/0024 test 4).

Docker is not available in CI's unit job or a cloud session, so the definition is read as text, like
`test_runner_image_definition.py`. The runner stage builds on `app` and so carries the same entries.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
DOCKERFILE = (BACKEND / "Dockerfile").read_text(encoding="utf-8")
COPIES = re.findall(r"^COPY\s+(?:--\S+\s+)*(\S+)\s+(\S+)\s*$", DOCKERFILE, flags=re.MULTILINE)
IGNORED = {
    line.strip().rstrip("/")
    for line in (BACKEND / ".dockerignore").read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.startswith("#")
}


def test_the_released_entries_are_copied_to_where_the_loader_reads_them() -> None:
    assert ("catalog/datasets", "./catalog/datasets") in COPIES
    assert ("catalog/retired.yaml", "./catalog/retired.yaml") in COPIES


@pytest.mark.parametrize("source", [source for source, _ in COPIES])
def test_no_copy_reaches_the_prototype_or_candidate_entries(source: str) -> None:
    path = source.rstrip("/")
    assert path not in {".", "catalog", "catalog/*", "catalog/prototype", "catalog/candidates"}
    assert not path.startswith(("catalog/prototype", "catalog/candidates"))


def test_the_build_context_leaves_both_out() -> None:
    assert {"catalog/prototype", "catalog/candidates"} <= IGNORED


def test_the_loader_reads_from_the_place_the_image_copies_to() -> None:
    from earthx.catalog.datasets import CATALOG_DIR

    assert CATALOG_DIR == BACKEND / "catalog"
    assert (CATALOG_DIR / "datasets").is_dir() and (CATALOG_DIR / "retired.yaml").is_file()

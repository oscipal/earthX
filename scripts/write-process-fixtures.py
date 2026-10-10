#!/usr/bin/env python3
"""Writes the process descriptions the panel is built and tested from (M4-13a, K3).

    PYTHONPATH=backend python scripts/write-process-fixtures.py          write the files
    PYTHONPATH=backend python scripts/write-process-fixtures.py --check  fail if a file is stale

One file per dataset in ``frontend/src/fixtures/processes/<dataset>.json``: the answer of
``GET /processing/processes/recipe?dataset=<dataset>`` with the real operators. The frontend
tests build the panel from exactly these files, and ``backend/tests/earthx/api/test_process_fixtures.py``
fails when a file differs from what the API says now, so a changed parameter model cannot leave the
panel behind unnoticed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from earthx.api.processing_docs import process_description
from earthx.catalog.datasets import REGISTRY as DATASETS
from earthx.processing.operators import REGISTRY as OPERATORS

DIRECTORY = Path(__file__).resolve().parent.parent / "frontend" / "src" / "fixtures" / "processes"


def fixtures() -> dict[str, str]:
    """File name -> text, for every dataset of the registry."""
    return {
        f"{config.dataset_id}.json": json.dumps(
            process_description("", OPERATORS, config), indent=2, sort_keys=True, ensure_ascii=False
        )
        + "\n"
        for config in DATASETS
    }


def main(argv: list[str]) -> int:
    wanted = fixtures()
    existing = {path.name: path.read_text(encoding="utf-8") for path in DIRECTORY.glob("*.json")}
    if argv == ["--check"]:
        stale = sorted(name for name in wanted if existing.get(name) != wanted[name])
        extra = sorted(set(existing) - set(wanted))
        for name in stale:
            print(f"stale: {name}")
        for name in extra:
            print(f"no dataset for: {name}")
        return 1 if stale or extra else 0
    if argv:
        print(__doc__)
        return 2
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    for name in sorted(set(existing) - set(wanted)):
        (DIRECTORY / name).unlink()
    for name, text in wanted.items():
        (DIRECTORY / name).write_text(text, encoding="utf-8")
        print(f"wrote {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

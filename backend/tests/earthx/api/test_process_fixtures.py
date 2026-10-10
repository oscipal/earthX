"""The process descriptions the frontend builds the panel from are the ones the API gives (M4-13a, K3).

``scripts/write-process-fixtures.py`` writes them. If a parameter model, an operator or a registry entry
changes, a file here is stale and the test names it; the fix is to run the script and commit the files.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from earthx.catalog.datasets import REGISTRY
from earthx.processing.operators import REGISTRY as OPERATORS
from earthx.processing.operators import OperatorRegistry

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "write-process-fixtures.py"
HOW_TO_FIX = "run `PYTHONPATH=backend python scripts/write-process-fixtures.py` and commit the files"


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("write_process_fixtures", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCRIPT_MODULE = _script()
DATASETS = [config.dataset_id for config in REGISTRY]


def test_there_is_a_dataset_to_check() -> None:
    assert len(DATASETS) >= 3


@pytest.mark.parametrize("dataset", DATASETS)
def test_the_file_is_what_the_api_says_now(dataset: str) -> None:
    path = SCRIPT_MODULE.DIRECTORY / f"{dataset}.json"
    assert path.is_file(), f"no fixture for {dataset!r}: {HOW_TO_FIX}"
    assert path.read_text(encoding="utf-8") == SCRIPT_MODULE.fixtures()[f"{dataset}.json"], (
        f"{path.name} is stale: {HOW_TO_FIX}"
    )


def test_no_file_is_left_for_a_dataset_that_is_gone() -> None:
    names = {path.name for path in SCRIPT_MODULE.DIRECTORY.glob("*.json")}
    assert names == {f"{dataset}.json" for dataset in DATASETS}, HOW_TO_FIX


def test_a_changed_operator_makes_the_check_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """The counter-proof: with one operator fewer the files are stale, and the script says so."""
    fewer = OperatorRegistry([operator for _, operator in sorted(OPERATORS.items()) if operator.op != "reproject"])
    monkeypatch.setattr(SCRIPT_MODULE, "OPERATORS", fewer)
    assert SCRIPT_MODULE.main(["--check"]) == 1


def test_the_check_passes_on_the_files_as_they_are() -> None:
    assert SCRIPT_MODULE.main(["--check"]) == 0


def test_an_unknown_argument_writes_nothing_and_fails() -> None:
    before = {path.name: path.read_bytes() for path in SCRIPT_MODULE.DIRECTORY.glob("*.json")}
    assert SCRIPT_MODULE.main(["--write-everything"]) == 2
    assert before == {path.name: path.read_bytes() for path in SCRIPT_MODULE.DIRECTORY.glob("*.json")}

"""The checks of CI on the approval files shipped in the repository, as one function (M5-67 fix 4).

The shipped files are checked in ``tests/catalog/test_approvals.py``; the files a harvest run writes are checked with
the same function in ``tests/integration/test_cycle_run.py``, so that a run cannot write a file CI would refuse
(25.11.2026: the second run of a day named its file ``-2``, and the test of the shipped files wanted none).
"""

from __future__ import annotations

from collections.abc import Container
from pathlib import Path

from earthx.catalog.approvals import file_number, load_approvals


def assert_approvals_are_consistent(directory: Path, sources: Container[str]) -> tuple[str, ...]:
    """Load every approval file of ``directory`` (the loader holds the rule for their names and their order) and check
    what CI checks beyond it. Returns the names, in the order the loader gives them."""
    found = load_approvals(directory)
    for approval, name, sha in found:
        assert approval.source_id in sources, name
        assert approval.decision in ("pending", "approved", "rejected"), name
        assert len(sha) == 64, name
        if approval.decision == "approved":
            assert approval.decided_on is not None, name
            assert approval.sample and all(check.ok is not None for check in approval.sample), name
        assert file_number(Path(name).stem, approval.created_on, approval.source_id) is not None, name
    return tuple(name for _, name, _ in found)

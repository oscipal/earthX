"""T-D lives outside ``backend/tests/`` on purpose.

``pyproject.toml`` points ``testpaths`` at ``backend/tests``, so a plain ``pytest`` —
the command a cloud session and the CI pull-request job both run (adr/0002 §6) — never
collects anything here. Only the scheduled workflow names this directory.

Two things follow from that, and both are the point:

* The network guard of ``backend/tests/conftest.py`` does not apply here. These tests
  are the one place that is *supposed* to reach the source.
* A pull request can never turn red because Earth Search is having a bad day
  (adr/0002 §2, T-D).
"""

from __future__ import annotations

import pytest


def pytest_xdist_auto_num_workers(config: pytest.Config) -> int:
    """One process, as before `-n auto` came into `pyproject.toml` (NM4-23).

    The smokes reach the real sources; in several processes each would bring its own
    gateway limits per host. 0 workers is xdist's serial run.
    """
    return 0


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"

"""The shell of the harvest command: what it refuses before it opens a connection (M5-19 plan §4.1, F7)."""

from __future__ import annotations

import pytest

from earthx.catalog.datasets import read_registry
from earthx.catalog.sources import read_sources
from earthx.discovery.harvest import _policy_for, main


def test_an_unknown_source_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["no-such-source"]) == 1
    assert "no source 'no-such-source'" in capsys.readouterr().err


def test_a_held_source_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["data-gv-at"]) == 1
    assert "held" in capsys.readouterr().err


def test_the_policy_asks_only_the_source_host_with_its_limits_and_robots() -> None:
    source = read_sources()["fsdi-stac"]
    policy = _policy_for(source, read_registry().host_limits)
    assert policy.allowed_hosts == frozenset({"data.geo.admin.ch"})
    assert policy.obey_robots
    assert (policy.connections_for("data.geo.admin.ch"), policy.interval_for("data.geo.admin.ch")) == (6, 1.0)

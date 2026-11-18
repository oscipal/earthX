"""The shell of the harvest command: what it refuses before it opens a connection (M5-19 plan §4.1, F7)."""

from __future__ import annotations

import pytest

from earthx.catalog.datasets import read_registry
from earthx.catalog.harvest_store import HarvestBusy
from earthx.catalog.sources import read_sources
from earthx.discovery import harvest as harvest_module
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


def test_a_ckan_source_asks_its_catalogue_host_with_two_connections_and_a_second_apart() -> None:
    hosts = read_registry().host_limits
    for source_id, host in (("govdata", "ckan.govdata.de"), ("opendata-swiss", "ckan.opendata.swiss")):
        policy = _policy_for(read_sources()[source_id], hosts)
        assert policy.allowed_hosts == frozenset({host})
        assert (policy.connections_for(host), policy.interval_for(host)) == (2, 1.0)


def test_full_is_handed_to_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, bool] = {}

    async def fake(source: object, hosts: object, *, reextract: bool, full: bool) -> None:
        seen.update(reextract=reextract, full=full)
        raise HarvestBusy("busy")

    monkeypatch.delenv("EARTHX_USER_AGENT", raising=False)
    monkeypatch.setattr(harvest_module, "_main_async", fake)
    assert main(["govdata", "--full"]) == 1
    assert seen == {"reextract": False, "full": True}


def test_the_policy_waives_robots_txt_only_where_the_source_file_says_so() -> None:
    hosts, sources = read_registry().host_limits, read_sources()
    swiss = _policy_for(sources["opendata-swiss"], hosts)
    assert swiss.robots_exceptions == {"ckan.opendata.swiss": ("/api/3/action/",)}
    assert swiss.robots_waived("ckan.opendata.swiss", "/api/3/action/package_search")
    assert not swiss.robots_waived("ckan.opendata.swiss", "/dataset/x")
    for source_id in ("govdata", "fsdi-stac", "earth-search"):
        assert _policy_for(sources[source_id], hosts).robots_exceptions == {}

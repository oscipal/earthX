"""The shell of the harvest command: what it refuses before it opens a connection (M5-19 plan §4.1, F7)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from earthx.catalog.datasets import read_registry
from earthx.catalog.harvest_store import HarvestBusy, RunCounts, SourceSummary
from earthx.catalog.sources import read_sources
from earthx.discovery import harvest as harvest_module
from earthx.discovery.harvest import EXIT_PAUSED, PAUSE_REASONS, HarvestResult, main, source_policy


def test_an_unknown_source_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["no-such-source"]) == 1
    assert "no source 'no-such-source'" in capsys.readouterr().err


def test_a_held_source_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["data-gv-at"]) == 1
    assert "held" in capsys.readouterr().err


def test_the_policy_asks_only_the_source_host_with_its_limits_and_robots() -> None:
    source = read_sources()["fsdi-stac"]
    policy = source_policy(source, read_registry().host_limits)
    assert policy.allowed_hosts == frozenset({"data.geo.admin.ch"})
    assert policy.obey_robots
    assert (policy.connections_for("data.geo.admin.ch"), policy.interval_for("data.geo.admin.ch")) == (6, 1.0)


def test_a_ckan_source_asks_its_catalogue_host_with_two_connections_and_a_second_apart() -> None:
    hosts = read_registry().host_limits
    for source_id, host in (("govdata", "ckan.govdata.de"), ("opendata-swiss", "ckan.opendata.swiss")):
        policy = source_policy(read_sources()[source_id], hosts)
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
    swiss = source_policy(sources["opendata-swiss"], hosts)
    assert swiss.robots_exceptions == {"ckan.opendata.swiss": ("/api/3/action/",)}
    assert swiss.robots_waived("ckan.opendata.swiss", "/api/3/action/package_search")
    assert not swiss.robots_waived("ckan.opendata.swiss", "/dataset/x")
    govdata = source_policy(sources["govdata"], hosts)
    assert govdata.robots_exceptions == {"ckan.govdata.de": ("/api/3/action/",)}
    for source_id in ("fsdi-stac", "earth-search"):
        assert source_policy(sources[source_id], hosts).robots_exceptions == {}


def test_a_resting_source_says_why_no_run_starts(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    async def resting(*_: object, **__: object) -> None:
        raise harvest_module.SourceResting("opendata-swiss", datetime(2026, 11, 19, 0, 0, tzinfo=UTC))

    monkeypatch.setattr(harvest_module, "_main_async", resting)
    monkeypatch.setattr(harvest_module, "_measure", resting)
    # A rest the source asked for is a pause of a run (the cycle goes on); a measurement that did not happen is not.
    for argv, code in ((["opendata-swiss"], EXIT_PAUSED), (["opendata-swiss", "--measure"], 1)):
        assert main(argv) == code
        assert capsys.readouterr().out.strip() == (
            "opendata-swiss: kein Lauf gestartet – die Quelle bat mit 429 um Pause und ruht bis 2026-11-19 00:00 UTC"
        )


def test_the_policy_of_opendata_swiss_waits_a_minute_for_an_answer() -> None:
    hosts, sources = read_registry().host_limits, read_sources()
    assert source_policy(sources["opendata-swiss"], hosts).read_timeout_for("ckan.opendata.swiss") == 60.0
    assert source_policy(sources["govdata"], hosts).read_timeout_for("ckan.govdata.de") == 60.0
    assert source_policy(sources["fsdi-stac"], hosts).read_timeout_for("data.geo.admin.ch") == 15.0


def test_explain_links_is_for_a_ckan_source(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["fsdi-stac", "--explain-links"]) == 1
    assert "--explain-links is for a ckan source" in capsys.readouterr().err


def _ended(monkeypatch: pytest.MonkeyPatch, status: str, stop_reason: str | None) -> None:
    async def fake(*_: object, **__: object) -> HarvestResult:
        return HarvestResult(
            run_id=1, kind="incremental", status=status, stop_reason=stop_reason, counts=RunCounts(),
            summary=SourceSummary(extracted=0, invalid={}, gone=0, extent_unknown=0),
        )

    monkeypatch.setattr(harvest_module, "_main_async", fake)


@pytest.mark.parametrize(
    ("status", "stop_reason", "code"),
    [
        ("done", None, 0),
        # A pause on purpose keeps its place and is no failure (M5-67 fix 1): the cycle reads it as success.
        ("interrupted", "page_budget", EXIT_PAUSED),
        ("interrupted", "request_budget", EXIT_PAUSED),
        ("interrupted", "rate_limited", EXIT_PAUSED),
        # What needs a look stays a failure: a robots.txt that forbids, a source that does not answer, a resting host,
        # a lease that ran out, a listing that cannot be read.
        ("interrupted", "robots", 1),
        ("interrupted", "upstream", 1),
        ("interrupted", "host_resting", 1),
        ("interrupted", "lease_expired", 1),
        ("failed", "shape", 1),
        # A status of a failure never counts as a pause, whatever its reason says.
        ("failed", "page_budget", 1),
    ],
)
def test_only_a_pause_on_purpose_has_its_own_exit_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], status: str, stop_reason: str | None, code: int
) -> None:
    _ended(monkeypatch, status, stop_reason)
    assert main(["govdata"]) == code
    assert "govdata:" in capsys.readouterr().out


def test_the_exit_code_of_a_pause_is_none_of_the_codes_a_shell_or_docker_uses() -> None:
    # 0 is success, 1 a failure, 2 a usage error (argparse), 125-127 are docker's own, above 128 a signal.
    assert EXIT_PAUSED not in {0, 1, 2} and 3 <= EXIT_PAUSED < 125
    assert PAUSE_REASONS == {"page_budget", "request_budget", "rate_limited"}

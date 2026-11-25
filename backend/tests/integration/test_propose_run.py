"""Candidates of the full way against Postgres (M5-20 plan §14.1): visible listed rasters become candidate files, a
full entry with the candidate's takeover takes over the listed row, and the grade of a tier changes no listed entry.

The finds are synthetic intermediate forms (``test_report.World``); files and items come from ``httpx.MockTransport``
behind the gateway. No source is asked (adr/0002).
"""

# ruff: noqa: F811  (the fixture `world` of test_report)

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from earthx.catalog.hosts import HostLimit
from earthx.catalog.listing_store import mark_listings
from earthx.discovery import propose as propose_module
from earthx.discovery import report as report_module
from earthx.discovery.dedupe import Member
from earthx.discovery.propose import run_propose
from earthx.gateway import Gateway, Policy
from tests.earthx.discovery.test_propose import COG, _ranged
from tests.integration.test_report import DAY, PUBLISHER, World, _find, _regions, world  # noqa: F401  (fixtures)

FILES = "files.example.org"


def _raster(key: str, **changes: Any) -> dict[str, Any]:
    files = changes.pop("files", [f"https://{FILES}/{key}.tif"])
    return _find(
        key,
        data_kind="raster",
        category="elevation",
        distributions=[{"href": h, "format": "GeoTIFF", "media_type": None, "title": None, "roles": []} for h in files],
        **changes,
    )


def _items(collection: str) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "id": f"{collection}-{n}", "properties": {"datetime": "2024-01-01T00:00:00Z"},
             "assets": {"data": {"href": f"https://{FILES}/{collection}/{n}.tif", "type": "image/tiff"}}}
            for n in range(2)
        ],
    }


class Answers:
    """Files and items as the stand-in transport serves them; ``requests`` counts what was asked."""

    def __init__(self) -> None:
        self.requests: list[str] = []
        ranged = _ranged(COG)
        self.files: dict[str, Callable[[httpx.Request], httpx.Response]] = {"/locked.tif": lambda r: httpx.Response(401)}
        self.default = ranged

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(f"{request.method} {request.headers['host']}{request.url.path}")
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.headers["host"] == "stac.example.org":
            collection = request.url.path.split("/collections/", 1)[1].split("/", 1)[0]
            return httpx.Response(200, json=_items(collection))
        return self.files.get(request.url.path, self.default)(request)

    def opener(self):  # type: ignore[no-untyped-def]
        async def nosleep(_: float) -> None:
            return None

        @asynccontextmanager
        async def open_gateway(policy: Policy) -> AsyncIterator[Gateway]:
            transport = httpx.MockTransport(self.handle)
            async with Gateway(policy, transport=transport, resolve=lambda h, p: ("93.184.216.34",), sleep=nosleep) as gateway:
                yield gateway

        return open_gateway


HOSTS = {"stac.example.org": HostLimit(connections=1, interval_s=1.0, reason="test")}


def _grant_both(world: World) -> None:
    grants = world.licence_dir / "grants"
    text = (grants / f"{world.ckan.source_id}.yaml").read_text(encoding="utf-8")
    (grants / f"{world.stac.source_id}.yaml").write_text(text, encoding="utf-8")


def _publish(world: World, source: Any) -> None:
    result = world.report(source)
    assert result.files, "the report formed no stack"
    world.approve(result.files[0])
    world.publish()


@pytest.fixture
def published(world: World, monkeypatch: pytest.MonkeyPatch) -> World:
    monkeypatch.setenv("EARTHX_USER_AGENT", "earthx-test/0 (+https://example.org/contact)")
    _grant_both(world)
    world.put(
        world.ckan,
        _raster("r1", identifier="ID-R1"),
        _raster("r2"),  # no identifier, no DOI: no key a full entry could take it over by
        _raster("r3", identifier="ID-R3", files=[]),  # no file in a readable format
        _raster("r4", identifier="ID-R4", files=["https://files.example.org/locked.tif"]),  # an account
        _raster("r5", doi="10.1234/r5"),  # a DOI only
        _find("v1", identifier="ID-V1"),  # a vector: never a candidate
    )
    world.put(world.stac, _raster("ch.example.dem", files=[]))
    _publish(world, world.ckan)
    _publish(world, world.stac)
    return world


def _run(world: World, out: Path, answers: Answers, *, day: date = DAY, trial: bool = False):  # type: ignore[no-untyped-def]
    return run_propose(
        world.conn,
        [world.ckan, world.stac],
        licences=world.licences,
        hosts=HOSTS,
        out=out,
        day=day,
        trial=trial,
        open_gateway=answers.opener(),
    )


def _candidate(out: Path, world: World, source: Any, key: str) -> dict[str, Any]:
    return yaml.safe_load((out / source.source_id / f"{source.source_id}.{key}.yaml").read_text(encoding="utf-8"))


def test_visible_rasters_become_candidates_with_takeover_licence_and_verify(published: World, tmp_path: Path) -> None:
    world, out, answers = published, tmp_path / "candidates", Answers()
    run = _run(world, out, answers)
    ckan, stac = run.sources[world.ckan.source_id], run.sources[world.stac.source_id]
    assert (ckan.new, stac.new) == (2, 1)
    assert dict(ckan.skipped) == {"no_takeover": 1, "no_format": 1, "account": 1}

    r1 = _candidate(out, world, world.ckan, "r1")
    assert r1["listed_id"] == f"{world.ckan.source_id}.r1" and r1["listed_state"] == "published"
    assert r1["proposed_id"] == "bodenkarte-r1"
    assert r1["takeover"] == {
        "via": "also_listed_as",
        "key": f"also:{world.ckan.source_id}:ID-R1",
        "also_listed_as": [f"{world.ckan.source_id}:ID-R1"],
    }
    licence = r1["licence"]
    assert (licence["legal_status"], licence["decided_by"], licence["decided_on"]) == ("cleared", "rules", DAY)
    assert licence["license"]["tier"] == "processing" and licence["license"]["attribution_unmodified"] == PUBLISHER
    assert licence["license_ref"] == ["cc-by-4.0"]
    verify = r1["verify"]
    assert verify["account"] == "none" and verify["files"][0]["outcome"] == "passed"
    assert verify["files"][0]["format"]["format"] == "cog" and verify["files"][0]["partial"] is True
    assert r1["onboarding"] == {"way": None, "profile": None, "notes": None}

    assert _candidate(out, world, world.ckan, "r5")["takeover"] == {"via": "doi", "key": "doi:10.1234/r5"}

    dem = _candidate(out, world, world.stac, "ch.example.dem")
    assert dem["proposed_id"] == "ch.example.dem"
    assert dem["takeover"] == {"via": "coll", "key": "coll:stac.example.org/ch.example.dem"}
    probe = json.loads((out / world.stac.source_id / f"{world.stac.source_id}.ch.example.dem.probe.json").read_text())
    assert [item["id"] for item in probe["items"]] == ["ch.example.dem-0", "ch.example.dem-1"]
    assert probe["collection"]["id"] == f"{world.stac.source_id}.ch.example.dem"
    assert [f["outcome"] for f in probe["verify"]["files"]] == ["passed", "passed"]
    # The items through the STAC host, two files each of one item.
    assert sum(1 for r in answers.requests if r.startswith("GET stac.example.org/api/stac/v1/collections/")) == 1


def test_an_unchanged_candidate_asks_nothing_and_a_changed_one_is_written_again(published: World, tmp_path: Path) -> None:
    world, out = published, tmp_path / "candidates"
    _run(world, out, Answers())
    path = out / world.ckan.source_id / f"{world.ckan.source_id}.r1.yaml"
    before = path.read_text(encoding="utf-8")
    again = Answers()
    run = _run(world, out, again)
    assert run.sources[world.ckan.source_id].unchanged == 2 and run.sources[world.stac.source_id].unchanged == 1
    assert run.sources[world.ckan.source_id].new == 0
    # Only the finds that are no candidate are asked again (their files).
    assert not any("/r1.tif" in r or "ch.example.dem" in r for r in again.requests)
    assert path.read_text(encoding="utf-8") == before
    # A change of the title at the source: written again, the day it was first proposed kept.
    world.put(world.ckan, _raster("r1", identifier="ID-R1", title="Höhenmodell r1"))
    world.report(world.ckan)
    run = _run(world, out, Answers(), day=DAY.replace(day=26))
    assert run.sources[world.ckan.source_id].changed == 1
    changed = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert changed["harvested"]["title"] == "Höhenmodell r1" and changed["first_proposed"] == DAY
    assert changed["proposed_id"] == "bodenkarte-r1"  # the proposal stays once made


def test_the_trial_run_decides_nothing(published: World, tmp_path: Path) -> None:
    out = tmp_path / "candidates"
    _run(published, out, Answers(), trial=True)
    licence = _candidate(out, published, published.ckan, "r1")["licence"]
    assert (licence["legal_status"], licence["decided_by"], licence["decided_on"]) == (None, None, None)
    # The next run decides it: a change, written again.
    run = _run(published, out, Answers())
    assert run.sources[published.ckan.source_id].changed == 2
    assert _candidate(out, published, published.ckan, "r1")["licence"]["legal_status"] == "cleared"


def test_at_most_twenty_a_source_and_no_request_beyond(
    published: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Review: Verify stops once the limit is reached; the rest waits for the next run (A34).
    monkeypatch.setattr(propose_module, "MAX_PER_SOURCE", 1)
    answers = Answers()
    run = _run(published, tmp_path / "candidates", answers)
    ckan = run.sources[published.ckan.source_id]
    # r1, r4 and r5 wait for Verify in the turning order; r4 (an account) may come before the one that passes. What is
    # left after the pass is never asked.
    assert ckan.new == 1 and ckan.skipped["limit"] + ckan.skipped["account"] == 2
    asked = {key for key in ("/r1.tif", "/locked.tif", "/r5.tif") if any(key in r for r in answers.requests)}
    assert len(asked) == 1 + ckan.skipped["account"]


def test_a_find_that_always_fails_does_not_keep_the_others_from_their_turn(
    published: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Review: with one find verified a run, the order turns with the day, so every find has its turn.
    monkeypatch.setattr(propose_module, "MAX_VERIFIED_PER_SOURCE", 1)
    out, first = tmp_path / "candidates", set()
    for day in range(1, 15):
        answers = Answers()
        _run(published, out, answers, day=DAY.replace(day=day))
        first |= {key for key in ("/r1.tif", "/locked.tif", "/r5.tif") if any(key in r for r in answers.requests)}
    assert first == {"/r1.tif", "/locked.tif", "/r5.tif"}


def test_a_spoilt_candidate_file_is_left_alone_and_counted(published: World, tmp_path: Path) -> None:
    out = tmp_path / "candidates"
    _run(published, out, Answers())
    path = out / published.ckan.source_id / f"{published.ckan.source_id}.r1.yaml"
    path.write_text("title: [unclosed\n", encoding="utf-8")
    run = _run(published, out, Answers())
    assert run.sources[published.ckan.source_id].skipped["file_unreadable"] == 2  # once read for the state, once here
    assert path.read_text(encoding="utf-8") == "title: [unclosed\n"


def test_a_full_entry_takes_over_the_listed_row_by_each_way(
    published: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world, out = published, tmp_path / "candidates"
    _run(world, out, Answers())
    r1 = _candidate(out, world, world.ckan, "r1")
    r5 = _candidate(out, world, world.ckan, "r5")
    dem = _candidate(out, world, world.stac, "ch.example.dem")

    # also_listed_as: catalog-load marks the row at once.
    listing = r1["takeover"]["also_listed_as"][0]
    assert mark_listings(world.conn, {listing: r1["proposed_id"]}) == (r1["listed_id"],)
    assert world.row("r1")["state"] == "duplicate" and world.row("r1")["duplicate_of"] == "bodenkarte-r1"

    # coll: and doi: the next report finds the full entry's keys.
    # The keys the full entries made from the three candidates carry (report._full_members): their STAC source, their
    # DOI, their also_listed_as.
    full = [
        Member("full-dem", (dem["takeover"]["key"],), (0,)),
        Member("full-r5", (r5["takeover"]["key"],), (0,)),
        Member(r1["proposed_id"], (r1["takeover"]["key"],), (0,)),
    ]
    monkeypatch.setattr(report_module, "_full_members", lambda: list(full))  # the report appends to it
    monkeypatch.setattr(report_module, "_listings", lambda: {listing: r1["proposed_id"]})
    world.report(world.stac)
    world.report(world.ckan)
    assert (world.row("ch.example.dem", world.stac)["state"], world.row("ch.example.dem", world.stac)["duplicate_of"]) == (
        "duplicate",
        "full-dem",
    )
    assert (world.row("r5")["state"], world.row("r5")["duplicate_of"]) == ("duplicate", "full-r5")
    assert world.row("r1")["state"] == "duplicate"

    # The candidates say so at the next propose, without a request and without being deleted (A37).
    monkeypatch.setattr(propose_module, "_full_members", lambda: list(full))
    answers = Answers()
    run = _run(world, out, answers)
    assert run.sources[world.ckan.source_id].state_updated == 2 and run.sources[world.stac.source_id].state_updated == 1
    assert _candidate(out, world, world.stac, "ch.example.dem")["listed_state"] == "duplicate"
    assert _candidate(out, world, world.ckan, "r1")["listed_state"] == "duplicate"
    assert not any("ch.example.dem" in r for r in answers.requests)


def test_a_licence_in_the_catalogue_tier_makes_no_candidate_and_its_grade_changes_no_listed_entry(
    published: World, tmp_path: Path
) -> None:
    world = published
    terms = world.licence_dir / "terms.yaml"
    terms.write_text(terms.read_text(encoding="utf-8").replace("tier: processing", "tier: catalog"), encoding="utf-8")
    # Otto's grade of the tier is no change of a listed entry (A18 holds only for its flags): it stays visible.
    world.report(world.ckan)
    assert world.row("r1")["state"] == "published"
    assert world.row("r1")["content"]["earthx:license_flags"]["tier"] == "catalog"
    run = _run(world, tmp_path / "candidates", Answers())
    assert run.sources[world.ckan.source_id].new == 0
    assert run.sources[world.ckan.source_id].skipped["tier_catalog"] == 3  # r1, r4 and r5; r2 has no key before

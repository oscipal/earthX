"""T-C: the Python steps of one harvest run, in the order of ``scripts/harvest-cycle.ps1`` (M5-67 fix 1, 24.11.2026).

Otto's first trial run broke after the step ``spellings``: the file it wrote held a YAML alias (one day shared by several
lines), and the next step refused it. No test ran the steps one after the other, each on the files of the one before.
This one does: ``sources`` -> ``harvest`` of every source -> ``spellings`` -> ``grants`` -> ``report`` of every source ->
the link check as a trial run -> ``decide`` -> ``summary``, through the ``main`` of each module with the arguments the
compose services give them, on synthetic finds, with one source that pauses and statements of one licence that several
finds spell in several ways. A source is never asked: the catalogues are ``httpx.MockTransport`` and the pages of the
link check too (adr/0002).
"""

# The fixtures of test_report are imported, so every test's parameter `world` shadows the import.
# ruff: noqa: F811

from __future__ import annotations

import re
import shutil
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import date
from functools import partial
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest
import yaml

from earthx.catalog import licences as licences_module
from earthx.catalog.approvals import load_approvals
from earthx.catalog.licences import load_licences
from earthx.catalog.sources import SourceConfig
from earthx.discovery import cycle, grants, harvest, linkcheck, propose, report, spellings
from earthx.discovery.harvest import EXIT_PAUSED, run_harvest
from earthx.gateway import Gateway, Policy
from tests.integration.test_harvest_ckan import Catalogue, _gateway, _package
from tests.integration.test_report import World, _ckan, _regions, world  # noqa: F401  (fixtures)

REPO = Path(__file__).resolve().parents[3]
SCRIPT = (REPO / "scripts" / "harvest-cycle.ps1").read_text(encoding="utf-8")
BEFUNDE = REPO / "docs" / "harvest" / "befunde.md"
TODAY = date.today()
HTML = "text/html; charset=utf-8"

#: The steps this test runs, by the name the script gives them; `test_the_steps_run_in_the_order_of_the_script` holds
#: this list against the text of the script, so that the two cannot drift apart.
STEPS = ("sources", "harvest", "spellings", "grants", "report", "linkcheck", "propose", "decide", "summary")

TERMS = """\
- license_ref: cc-by-4.0
  licence_class: K2
  matches: [CC-BY-4.0, "https://creativecommons.org/licenses/by/4.0/"]
  license: {spdx_id: CC-BY-4.0, name: CC BY 4.0, url: "https://creativecommons.org/licenses/by/4.0/",
            commercial_use: true, distribution: true, derivatives: true, share_alike: false,
            attribution_required: true, tier: processing, attribution_modified: "{publisher} (modified)",
            attribution_unmodified: "{publisher}", terms: null}
  approved_on: 2026-11-19
"""
GRANT_TO_ALL = "licenses: [cc-by-4.0]\napproved_on: 2026-11-19\n"

#: Spellings of CC BY 4.0 that the catalogue does not know (S1 an address, S2 an identifier) and one that nobody knows.
SPELLINGS = (
    ("https://creativecommons.org/licenses/by/4.0/legalcode", "CC BY 4.0"),
    ("http://creativecommons.org/licenses/by/4.0/deed.de", "cc-by 4.0"),
    ("https://creativecommons.org/licenses/by/4.0/legalcode", "CC BY 4.0"),
    ("Nutzungsbedingungen der Stadt Beispiel", "Nutzungsbedingungen der Stadt Beispiel"),
    ("Nutzungsbedingungen der Stadt Beispiel", "Nutzungsbedingungen der Stadt Beispiel"),
)


def _packages(prefix: str, count: int) -> list[dict[str, Any]]:
    """Packages of one publisher, each with a licence address and a licence identifier from ``SPELLINGS``."""
    found = []
    for number in range(count):
        key = f"{prefix}{number}"
        url, identifier = SPELLINGS[number % len(SPELLINGS)]
        found.append(
            _package(
                key,
                title=f"Bodenkarte {key}",
                license_id=identifier,
                license_url=url,
                spatial="Kanton Bern",
                organization={"title": "Kanton Zug"},
                extras=[],
                resources=[{"url": f"https://amt.example.org/daten/{key}.tif", "format": "GeoTIFF"}],
            )
        )
    return found


@dataclass
class Run:
    """What the steps of one run left: the exit code and the printed text of each, and the run's own folder."""

    folder: Path
    codes: dict[str, int]
    printed: dict[str, str]
    approvals: list[str]


class Cycle:
    """The steps of ``scripts/harvest-cycle.ps1`` against a synthetic world, each through its ``main``."""

    def __init__(self, world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
        suffix = world.ckan.source_id.removeprefix("t-")
        # Two sources of one catalogue host: `a` is read to its end, `b` pauses after a page (max_pages_per_run).
        self.a = replace(_ckan(f"a-{suffix}"), dedupe_rank=1, max_pages_per_run=None)
        self.b = replace(_ckan(f"b-{suffix}"), dedupe_rank=2, max_pages_per_run=1)
        world.sources = {self.a.source_id: self.a, self.b.source_id: self.b}
        self.world, self.tmp, self.capsys = world, tmp_path, capsys
        self.catalogues = {
            self.a.source_id: Catalogue(_packages("a", 5), size=10),
            self.b.source_id: Catalogue(_packages("b", 5), size=2),
        }
        self.licences = world.licence_dir
        (self.licences / "terms.yaml").write_text(TERMS, encoding="utf-8")
        (self.licences / "grant-to-all.yaml").write_text(GRANT_TO_ALL, encoding="utf-8")
        for stale in (self.licences / "grants").glob("*.yaml"):
            stale.unlink()  # a first run: no publisher has a grant yet, the step `grants` writes them
        self.approvals = world.out
        self.approvals.mkdir(parents=True, exist_ok=True)
        self.candidates = tmp_path / "candidates"
        self.harvest_dir = tmp_path / "docs-harvest"
        self.harvest_dir.mkdir()
        shutil.copy(BEFUNDE, self.harvest_dir / "befunde.md")
        self.runs = 0
        self._patch(monkeypatch)

    def _patch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sources = self.world.sources
        for module in (cycle, spellings, grants, report, linkcheck, harvest, propose):
            monkeypatch.setattr(module, "read_sources", lambda: sources)
        monkeypatch.setattr(spellings, "LICENSES_DIR", self.licences)
        grant_to_all = self.licences / "grant-to-all.yaml"
        monkeypatch.setattr(grants, "load_licences", partial(load_licences, directory=self.licences))
        monkeypatch.setattr(grants, "read_grant_to_all", partial(grants.read_grant_to_all, path=grant_to_all))
        monkeypatch.setattr(report, "load_licences", partial(load_licences, directory=self.licences))
        monkeypatch.setattr(propose, "load_licences", partial(load_licences, directory=self.licences))
        monkeypatch.setattr(licences_module, "LICENSES_DIR", self.licences)
        monkeypatch.setenv("EARTHX_USER_AGENT", "earthx-test/0 (+https://example.org/contact)")

        async def read_source(source: SourceConfig, hosts: object, *, reextract: bool, full: bool):  # type: ignore[no-untyped-def]
            with psycopg.connect(autocommit=True) as conn:
                gateway = _gateway(self.catalogues[source.source_id], source)
                async with gateway:
                    return await run_harvest(conn, source, gateway=gateway, full=full)

        monkeypatch.setattr(harvest, "_main_async", read_source)
        monkeypatch.setattr(linkcheck, "run_linkcheck", partial(linkcheck.run_linkcheck, open_gateway=self._pages()))

    def _pages(self) -> Callable[[Policy], Any]:
        """The pages the link check asks for: one for every package, titled as the package is."""

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return httpx.Response(404)
            key = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(
                200, headers={"content-type": HTML}, text=f"<html><body><h1>Bodenkarte {key}</h1></body></html>"
            )

        async def nosleep(_: float) -> None:
            return None

        @asynccontextmanager
        async def open_gateway(policy: Policy) -> AsyncIterator[Gateway]:
            transport = httpx.MockTransport(handler)
            async with Gateway(policy, transport=transport, resolve=lambda h, p: ("93.184.216.34",), sleep=nosleep) as gateway:
                yield gateway

        return open_gateway

    def step(self, name: str, code: int, run: Run) -> int:
        out = self.capsys.readouterr()
        run.codes[name] = code
        run.printed[name] = out.out + out.err
        return code

    def run(self, *, trial: bool) -> Run:
        """One run: every step in the order of the script, and an error where the script would stop."""
        self.runs += 1
        folder = self.tmp / f"run-{self.runs}"
        folder.mkdir()
        run = Run(folder, {}, {}, [])
        day = TODAY.isoformat()
        before = {path.name for path in self.approvals.glob("*.yaml")}

        assert self.step("sources", cycle.main(["sources"]), run) == 0
        sources = run.printed["sources"].split()
        # The order of the sources is the rank among duplicates (FSDI first): `a` before `b`.
        assert sources == [self.a.source_id, self.b.source_id]

        harvested = []
        for source_id in sources:
            code = harvest.main([source_id])
            self.step(f"harvest {source_id}", code, run)
            # What the script reads: only the exit code. 0 and the pause are a success, everything else a failure.
            assert code in (0, EXIT_PAUSED), run.printed[f"harvest {source_id}"]
            harvested.append(source_id)
        run.codes["harvest"] = 0

        assert self.step("spellings", spellings.main(["--out", str(self.licences), "--json", str(folder / "spellings.json")]), run) == 0, run.printed["spellings"]
        assert self.step("grants", grants.main([*sources, "--out", str(self.licences / "grants")]), run) == 0, run.printed["grants"]

        for source_id in harvested:
            code = report.main([source_id, "--out", str(self.approvals), "--json", str(folder / f"report-{source_id}.json")])
            assert self.step(f"report {source_id}", code, run) == 0, run.printed[f"report {source_id}"]
        run.codes["report"] = 0

        check = ["--json", str(folder / "linkcheck.json")] + (["--dry-run"] if trial else [])
        assert self.step("linkcheck", linkcheck.main(check), run) == 0, run.printed["linkcheck"]

        propose_args = ["--out", str(self.candidates), "--json", str(folder / "propose.json"), "--day", day]
        code = propose.main(propose_args + (["--trial"] if trial else []) + harvested)
        assert self.step("propose", code, run) == 0, run.printed["propose"]

        run.approvals = sorted({path.name for path in self.approvals.glob("*.yaml")} - before)
        decide = ["decide", "--run", str(folder), "--approvals", str(self.approvals), "--day", day]
        code = cycle.main(decide + (["--trial"] if trial else []) + run.approvals)
        assert self.step("decide", code, run) == 0, run.printed["decide"]

        summary = ["summary", "--run", str(folder), "--harvest", str(self.harvest_dir), "--approvals", str(self.approvals), "--day", day]
        code = cycle.main(summary + (["--trial"] if trial else []))
        assert self.step("summary", code, run) == 0, run.printed["summary"]
        return run


@pytest.fixture
def cycle_world(
    world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> Iterator[Cycle]:
    made = Cycle(world, tmp_path, monkeypatch, capsys)
    try:
        yield made
    finally:
        # A real harvest run leaves rows `World.clean` does not know; the link check leaves its results.
        ids = list(world.sources)
        world.conn.execute("DELETE FROM public.earthx_link_check WHERE split_part(dataset_id, '.', 1) = ANY(%s)", (ids,))
        for table in ("earthx_state_transition", "earthx_raw_record", "earthx_harvest_source"):
            world.conn.execute(f"DELETE FROM public.{table} WHERE source_id = ANY(%s)", (ids,))


def test_the_steps_run_in_the_order_of_the_script() -> None:
    code = "\n".join(line for line in SCRIPT.splitlines() if not line.lstrip().startswith("#"))
    markers = {
        "sources": r"'harvest-cycle', 'sources'",
        "harvest": r'Compose "harvest \$source"',
        "spellings": r"Compose 'spellings'",
        "grants": r"Compose 'grants'",
        "report": r'Compose "report \$source"',
        "linkcheck": r"Compose 'linkcheck'",
        "propose": r"Compose 'propose'",
        "decide": r"Compose 'decide'",
        "summary": r"Compose 'summary' \$Summary",
    }
    found = {name: re.search(pattern, code) for name, pattern in markers.items()}
    assert all(found.values()), [name for name, match in found.items() if not match]
    assert tuple(sorted(found, key=lambda name: found[name].start())) == STEPS  # type: ignore[union-attr]


def test_the_trial_run_goes_through_every_step_and_a_source_that_pauses_is_no_failure(cycle_world: Cycle) -> None:
    run = cycle_world.run(trial=True)
    a, b = cycle_world.a.source_id, cycle_world.b.source_id
    assert (run.codes[f"harvest {a}"], run.codes[f"harvest {b}"]) == (0, EXIT_PAUSED)
    assert "interrupted" in run.printed[f"harvest {b}"] and "Seiten je Lauf erreicht" in run.printed[f"harvest {b}"]
    # The paused source's finds read so far go through the report like the others.
    for source_id, finds in ((a, 5), (b, 2)):
        numbers = yaml.safe_load((run.folder / f"report-{source_id}.json").read_text(encoding="utf-8"))
        assert numbers["finds"] == finds, source_id
    # The trial run decided nothing: every file is still pending, and the link check hid nothing.
    assert run.approvals and all(
        yaml.safe_load((cycle_world.approvals / name).read_text(encoding="utf-8"))["decision"] == "pending"
        for name in run.approvals
    )
    assert "Probelauf" in run.printed["linkcheck"]
    # The candidates ran for both harvested sources (tables, so none is a candidate) and the run files say so.
    numbers = yaml.safe_load((run.folder / "propose.json").read_text(encoding="utf-8"))
    assert numbers["trial"] and set(numbers["sources"]) == {a, b}
    assert all(count["new"] == 0 and count["error"] is None for count in numbers["sources"].values())
    readme = sorted((cycle_world.harvest_dir / "laeufe").iterdir())[-1] / "README.md"
    assert "## Kandidaten des vollen Wegs" in readme.read_text(encoding="utf-8")
    assert not cycle_world.candidates.exists() or not any(cycle_world.candidates.rglob("*.yaml"))


def test_spellings_that_occur_several_times_are_written_without_an_alias_and_read_by_every_later_step(
    cycle_world: Cycle,
) -> None:
    run = cycle_world.run(trial=True)
    path = cycle_world.licences / "spellings.yaml"
    text = path.read_text(encoding="utf-8")
    assert not re.search(r"[&*]id\d+", text), text
    added = yaml.safe_load(text)
    assert {item["statement"] for item in added} == {
        "https://creativecommons.org/licenses/by/4.0/legalcode",
        "http://creativecommons.org/licenses/by/4.0/deed.de",
        "CC BY 4.0",
        "cc-by 4.0",
    }
    # Several lines, one day: the shape that was written with `&id001` / `*id001`.
    assert len(added) >= 3 and len({str(item["added_on"]) for item in added}) == 1
    # What the next steps read (grants, report) is this file, through the strict loader of the catalogue.
    catalogue = load_licences(cycle_world.world.sources, cycle_world.licences)
    assert {"CC BY 4.0", "cc-by 4.0"} <= set(catalogue.by_statement)
    assert run.codes["report"] == 0 and "Nutzungsbedingungen der Stadt Beispiel" in run.printed["spellings"]
    # And the files of the run name the spellings that were added.
    readme = next((cycle_world.harvest_dir / "laeufe").glob("*/lizenzangaben.md")).read_text(encoding="utf-8")
    assert "CC BY 4.0" in readme


def test_a_second_run_on_the_same_day_takes_the_files_of_the_first_and_changes_nothing_in_them(cycle_world: Cycle) -> None:
    first = cycle_world.run(trial=True)
    spellings_text = (cycle_world.licences / "spellings.yaml").read_text(encoding="utf-8")
    grants_text = {p.name: p.read_text(encoding="utf-8") for p in (cycle_world.licences / "grants").glob("*.yaml")}
    second = cycle_world.run(trial=False)
    assert set(first.codes) == set(second.codes)
    assert (cycle_world.licences / "spellings.yaml").read_text(encoding="utf-8") == spellings_text
    assert {p.name: p.read_text(encoding="utf-8") for p in (cycle_world.licences / "grants").glob("*.yaml")} == grants_text
    # The files of the day: the second run's folder next to the first, never over it.
    folders = sorted(p.name for p in (cycle_world.harvest_dir / "laeufe").iterdir())
    assert folders == [TODAY.isoformat(), f"{TODAY.isoformat()}-2"]
    # Nothing a run writes may be refused by the loaders of the next one.
    load_approvals(cycle_world.approvals)
    load_licences(cycle_world.world.sources, cycle_world.licences)


def test_the_files_of_the_run_say_that_a_pause_is_a_note_and_not_an_error(cycle_world: Cycle) -> None:
    b = cycle_world.b.source_id
    run = cycle_world.run(trial=True)
    # The script writes the sources that paused and keeps what each printed; the summary only reads them.
    (run.folder / "quellen-pause.txt").write_text(f"{b}\n", encoding="utf-8")
    (run.folder / f"harvest-{b}.txt").write_text(run.printed[f"harvest {b}"], encoding="utf-8")
    cycle.main(["summary", "--run", str(run.folder), "--harvest", str(cycle_world.harvest_dir),
                "--approvals", str(cycle_world.approvals), "--day", TODAY.isoformat(), "--trial"])
    folders = sorted((cycle_world.harvest_dir / "laeufe").iterdir())
    readme = (folders[-1] / "README.md").read_text(encoding="utf-8")
    assert f"**{b}:** Hinweis, planmäßige Pause (kein Fehler)" in readme and "Seiten je Lauf erreicht" in readme
    assert "Harvest gescheitert" not in readme and "**Gescheitert:**" not in readme
    # The line is the report line of the harvest, not one of the JSON log lines that come before it.
    assert f"**{b}:** Hinweis, planmäßige Pause (kein Fehler): {b}: Lauf" in readme and '"logger"' not in readme
    befunde = (cycle_world.harvest_dir / "befunde.md").read_text(encoding="utf-8")
    assert f"QUELLE {b}" not in befunde and "LAUF" not in befunde.split("<!-- auto:start -->")[1].split("<!-- auto:end -->")[0]
    assert (folders[-1] / "fehler.log").read_text(encoding="utf-8").strip() == "keine"


def test_a_failed_step_puts_its_own_line_into_the_window_the_error_log_and_the_pull_request(
    cycle_world: Cycle, capsys: pytest.CaptureFixture[str]
) -> None:
    # What the script does with a step that fails: the line that says why goes into lauf-fehler.txt, and from there
    # into fehler.log and the text of the pull request (plan §10).
    (cycle_world.licences / "spellings.yaml").write_text("- &a {statement: x}\n- *a\n", encoding="utf-8")
    code = report.main([cycle_world.a.source_id, "--out", str(cycle_world.approvals)])
    why = capsys.readouterr().err.strip()
    assert code == 1 and "spellings.yaml: not valid YAML: an anchor is not allowed (line 1)" in why
    folder = cycle_world.tmp / "failed"
    folder.mkdir()
    (folder / "lauf-fehler.txt").write_text(f"Bericht: Der Bericht von x ist gescheitert. Grund: {why}", encoding="utf-8")
    cycle.main(["summary", "--run", str(folder), "--harvest", str(cycle_world.harvest_dir),
                "--approvals", str(cycle_world.approvals), "--day", TODAY.isoformat(), "--trial"])
    written = sorted((cycle_world.harvest_dir / "laeufe").iterdir())[-1]
    assert "an anchor is not allowed" in (written / "fehler.log").read_text(encoding="utf-8")
    assert "an anchor is not allowed" in (folder / "pr-body.md").read_text(encoding="utf-8")
    assert "an anchor is not allowed" in (cycle_world.harvest_dir / "befunde.md").read_text(encoding="utf-8")

"""T-C: a harvest run's approval by rules and its files against Postgres (M5-67 plan §6, §8, §9).

Built on the synthetic world of ``test_report``; no source and no page is asked.
"""

# The fixtures of test_report are imported, so every test's parameter `world` shadows the import.
# ruff: noqa: F811

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import yaml

from earthx.catalog.approvals import load_approvals, publish
from earthx.catalog.link_checks import LinkResult, record_results
from earthx.discovery.cycle import decide_files, read_approval_rules, summary
from earthx.discovery.report import report_numbers
from tests.integration.test_report import World, _find, _regions, world  # noqa: F401  (fixtures)

DAY = date(2026, 11, 25)
BEFUNDE = Path(__file__).resolve().parents[3] / "docs" / "harvest" / "befunde.md"


def _checked(world: World, outcomes: dict[str, str]) -> None:
    from datetime import UTC, datetime

    record_results(
        world.conn,
        [
            LinkResult(f"{world.ckan.source_id}.{key}", f"https://amt.example.org/daten/{key}", "amt.example.org",
                       "amt.example.org/daten/{x}", outcome, "ok" if outcome == "passed" else "no_title", 200,
                       "amt.example.org")
            for key, outcome in outcomes.items()
        ],
        datetime.now(UTC),
    )


def test_a_stack_within_the_rules_is_approved_by_them_and_publishes_only_passed_links(world: World) -> None:
    world.put(world.ckan, _find("a"), _find("b"), _find("s", title="Bodenkarte und Bibliothekenstatistik"))
    result = world.report()
    numbers = report_numbers(world.conn, result)
    assert numbers["flagged"]["W1"]["count"] == 1 and numbers["stack"]["entries"] == 3
    _checked(world, {"a": "passed", "b": "failed"})
    approval = result.files[0]
    decided = decide_files(world.conn, [approval], reports={world.ckan.source_id: numbers},
                           rules=read_approval_rules(), day=DAY, trial=False)
    assert decided[0]["decision"] == "approved" and decided[0]["sample_passed"] == 1
    document = yaml.safe_load(approval.read_text(encoding="utf-8"))
    assert (document["decision"], document["decided_by"], str(document["decided_on"])) == ("approved", "rules", "2026-11-25")
    checks = {item["dataset_id"].rsplit(".", 1)[1]: (item["ok"], item["check"]["outcome"]) for item in document["sample"]}
    assert checks == {"a": (True, "passed"), "b": (False, "failed")}
    # The rules decide, the links decide what becomes visible: a published, b stays in review, s is out.
    assert publish(world.conn, load_approvals(world.out)).published == {f"approvals/{approval.name}": 1}
    assert [world.row(k)["state"] for k in "abs"] == ["published", "in_review", "in_review"]


def test_the_trial_decides_nothing_and_a_big_stack_waits(world: World) -> None:
    world.put(world.ckan, _find("a"))
    result = world.report()
    approval = result.files[0]
    decided = decide_files(world.conn, [approval], reports={}, rules=read_approval_rules(), day=DAY, trial=True)
    document = yaml.safe_load(approval.read_text(encoding="utf-8"))
    assert decided[0]["would_approve"] and document["decision"] == "pending" and "decided_by" not in document
    assert all(item["ok"] is None and item["check"]["reason"] == "not_checked" for item in document["sample"])
    # Many finds the report could not derive: the stack waits even outside the trial.
    reports = {world.ckan.source_id: {"finds": 10, "failed": 5}}
    decided = decide_files(world.conn, [approval], reports=reports, rules=read_approval_rules(), day=DAY, trial=False)
    assert decided[0]["decision"] == "pending" and "nicht ableitbar" in decided[0]["reasons"][0]


def test_the_summary_writes_the_files_of_the_run_and_the_findings(world: World, tmp_path: Path) -> None:
    world.put(world.ckan, _find("a"), _find("s", title="Bodenkarte und Bibliothekenstatistik"))
    result = world.report()
    run = tmp_path / "run"
    run.mkdir()
    (run / f"report-{world.ckan.source_id}.json").write_text(json.dumps(report_numbers(world.conn, result)),
                                                            encoding="utf-8")
    decided = decide_files(world.conn, list(result.files[:1]), reports={}, rules=read_approval_rules(), day=DAY,
                           trial=False)
    (run / "decide.json").write_text(json.dumps(decided), encoding="utf-8")
    (run / "quellen-fehler.txt").write_text("data-gv-at: Der Harvest endete mit Fehler\n", encoding="utf-8")
    harvest = tmp_path / "harvest"
    harvest.mkdir()
    shutil.copy(BEFUNDE, harvest / "befunde.md")
    line = summary(world.conn, run, harvest, world.out, DAY, trial=False)
    assert line.startswith("1 Quellen, 1 von 1 Stapeln freigegeben")
    folder = harvest / "laeufe" / "2026-11-25"
    assert (folder / "README.md").exists() and (folder / "warnzeichen.md").exists()
    befunde = (harvest / "befunde.md").read_text(encoding="utf-8")
    assert f"WARNZEICHEN W1 {world.ckan.source_id}" in befunde and "QUELLE data-gv-at" in befunde
    assert "H-2026-11-24-05" in befunde  # the part by hand stays
    assert (run / "pr-body.md").read_text(encoding="utf-8").startswith("# Harvest-Lauf 2026-11-25")
    # A second run the same day gets a folder of its own.
    summary(world.conn, run, harvest, world.out, DAY, trial=False)
    assert (harvest / "laeufe" / "2026-11-25-2" / "README.md").exists()


def test_a_file_already_decided_is_left_alone(world: World) -> None:
    world.put(world.ckan, _find("a"))
    approval = world.report().files[0]
    world.approve(approval)
    before = approval.read_text(encoding="utf-8")
    assert decide_files(world.conn, [approval], reports={}, rules=read_approval_rules(), day=DAY, trial=False) == []
    assert approval.read_text(encoding="utf-8") == before


def test_the_command_refuses_names_that_are_no_approval_files_and_a_missing_file(world: World, tmp_path: Path) -> None:
    from earthx.discovery import cycle

    run = tmp_path / "run"
    run.mkdir()
    assert cycle.main(["decide", "--run", str(run), "--approvals", str(tmp_path), "../../etc/passwd"]) == 1
    assert cycle.main(["decide", "--run", str(run), "--approvals", str(tmp_path), "2026-11-25-govdata.yaml"]) == 1
    (run / "report-govdata.json").write_text("{kaputt", encoding="utf-8")
    assert cycle.main(["decide", "--run", str(run), "--approvals", str(tmp_path)]) == 1

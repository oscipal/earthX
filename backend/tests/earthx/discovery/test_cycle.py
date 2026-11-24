"""The steps of a harvest run in the container (M5-67 plan §6, §9): the rules of approval, the cleaning of what goes into
the repository, the list of findings and the files of a run. Pure: no database, no request."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from earthx.catalog.entry_files import EntryFileError
from earthx.discovery.cycle import (
    APPROVAL_RULES_FILE,
    AUTO_END,
    AUTO_START,
    Finding,
    _pauses,
    _text,
    clean,
    decide,
    findings_of,
    merge_findings,
    read_approval_rules,
    run_files,
)

RULES = read_approval_rules()
DAY = date(2026, 11, 25)
BEFUNDE = Path(__file__).resolve().parents[4] / "docs" / "harvest" / "befunde.md"


def stack(entries: int, excluded: int = 0) -> dict[str, object]:
    return {"entries": entries, "excluded_entries": [f"x.{i}" for i in range(excluded)]}


# --- The rules (plan §6, F6 = 1) --------------------------------------------------------------------------------------


def test_the_shipped_rules() -> None:
    rules = read_approval_rules(APPROVAL_RULES_FILE)
    assert (rules.max_entries, rules.max_share_of_published, rules.min_cap, rules.max_failed_share) == (
        5000,
        0.25,
        200,
        0.01,
    )


def test_a_plain_stack_is_approved() -> None:
    assert decide(stack(40), published=1000, finds=5000, failed=0, rules=RULES) == []


@pytest.mark.parametrize(
    ("document", "published", "finds", "failed", "reason"),
    [
        (stack(3, excluded=3), 1000, 100, 0, "kein Eintrag"),
        (stack(5001), 100_000, 100_000, 0, "mehr als 5000"),
        (stack(251), 1000, 1000, 0, "mehr als 250"),
        (stack(201), 0, 1000, 0, "mehr als 200"),
        (stack(10), 1000, 1000, 11, "11 von 1000 Funden nicht ableitbar"),
    ],
)
def test_a_stack_that_waits(document: dict, published: int, finds: int, failed: int, reason: str) -> None:
    reasons = decide(document, published=published, finds=finds, failed=failed, rules=RULES)
    assert any(reason in r for r in reasons), reasons


def test_the_edges_still_pass() -> None:
    assert decide(stack(250), published=1000, finds=1000, failed=10, rules=RULES) == []
    assert decide(stack(200), published=0, finds=1000, failed=0, rules=RULES) == []
    assert decide(stack(5000), published=100_000, finds=1000, failed=0, rules=RULES) == []


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("max_entries: 0\nmax_share_of_published: 0.25\nmin_cap: 200\nmax_failed_share: 0.01\n", "max_entries"),
        ("max_entries: 5000\nmax_share_of_published: 1.5\nmin_cap: 200\nmax_failed_share: 0.01\n", "share"),
        ("max_entries: 5000\nmin_cap: 200\nmax_failed_share: 0.01\n", "holds exactly"),
    ],
)
def test_wrong_rules(tmp_path: Path, text: str, message: str) -> None:
    path = tmp_path / "approval_rules.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(EntryFileError, match=message):
        read_approval_rules(path)


# --- Cleaning ---------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "kept", "gone"),
    [
        ("https://b.example.org/x.tif?X-Amz-Signature=abc123&a=1", "a=1", "abc123"),
        ("https://b.example.org/x?token=geheim", "token=[entfernt]", "geheim"),
        ("Fingerabdruck " + "a" * 64, "[Hash]", "a" * 64),
        ("Fragen an hans.muster@amt.example.org", "[Mail]", "hans.muster"),
        ("PGPASSWORD=s3cret docker compose", "PGPASSWORD=[entfernt]", "s3cret"),
        ("Datei C:\\Users\\otto\\earthx-ausgaben\\x.txt fehlt", "[Pfad]", "otto"),
        ("Datei /home/otto/earthx/x.txt fehlt", "[Pfad]", "otto"),
    ],
)
def test_clean(text: str, kept: str, gone: str) -> None:
    cleaned = clean(text)
    assert kept in cleaned and gone not in cleaned


def test_clean_leaves_ids_and_plain_links() -> None:
    text = (
        "opendata-swiss.b1405e11-135b-47fb-becd-2aa88553ef02 <https://www.minergie.ch/de/gebaeude/?seite=2>"
        " <https://amt.example.org/home/karte>"
    )
    assert clean(text) == text


# --- The list of findings ---------------------------------------------------------------------------------------------


def _document(auto: str) -> str:
    return f"# Harvest-Befunde\n\n## Offen, von Hand\n\n- [ ] **H-1** · von Hand\n\n## Offen, aus den Läufen\n\n{AUTO_START}\n{auto}\n{AUTO_END}\n\n## Erledigt\n\n- [x] **H-0** · alt\n"


def test_findings_keep_their_first_day_and_vanished_ones_are_ticked() -> None:
    first = merge_findings(_document("Noch kein automatischer Lauf."), [Finding("A", "eins"), Finding("B", "zwei")],
                           date(2026, 11, 24))
    second = merge_findings(first, [Finding("A", "eins, jetzt"), Finding("C", "neu")], DAY)
    assert "- [ ] **A** · seit 2026-11-24 · zuletzt 2026-11-25 · eins, jetzt" in second
    assert "- [ ] **C** · seit 2026-11-25 · zuletzt 2026-11-25 · neu" in second
    assert "- [x] **B** · 2026-11-24 bis 2026-11-25 · im Lauf vom 2026-11-25 nicht mehr aufgetreten" in second
    # The parts by hand stay.
    assert "- [ ] **H-1** · von Hand" in second and "- [x] **H-0** · alt" in second
    assert second.count(AUTO_START) == 1


def test_no_finding_says_so_and_findings_are_cleaned() -> None:
    assert "Keine offenen Befunde" in merge_findings(_document(""), [], DAY)
    text = merge_findings(_document(""), [Finding("X", "an hans@amt.example.org")], DAY)
    assert "hans@" not in text


@pytest.mark.parametrize("key", ["LIZENZ CC *BY*", "LIZENZ zwei\nZeilen", "LIZENZ an hans@amt.example.org"])
def test_a_key_of_any_text_is_read_back_and_ticked(key: str) -> None:
    first = merge_findings(_document(""), [Finding(key, "x")], date(2026, 11, 24))
    assert "hans@" not in first and first.count("- [ ] **") == 2
    second = merge_findings(first, [], DAY)
    assert second.count("- [x] **") == 2 and "seit 2026-11-24" not in second.split("## Erledigt")[0]


def test_without_the_markers_nothing_is_written() -> None:
    with pytest.raises(ValueError, match="markers"):
        merge_findings("# Harvest-Befunde\n\n## Erledigt\n", [], DAY)


def test_the_shipped_list_has_the_markers() -> None:
    text = BEFUNDE.read_text(encoding="utf-8")
    assert merge_findings(text, [Finding("A", "eins")], DAY).count("**A**") == 1


LINKCHECK = {
    "dry_run": False,
    "due": 40,
    "checked": 30,
    "outcomes": {"passed": 20, "failed": 8, "unchecked": 2},
    "reasons": {"no_title": 8, "robots": 2},
    "applied": {"hidden": 3, "restored": 1, "publishable": 12},
    "due_by_host": [["amt.example.org", 30, 0.0]],
    "groups": [
        {"kind": "host", "key": "spa.example.org", "passed": 1, "failed": 19, "unchecked": 0, "transient": 0,
         "guarded": True},
        {"kind": "pattern", "key": "amt.example.org/daten/{x}", "passed": 10, "failed": 6, "unchecked": 0,
         "transient": 0, "guarded": False},
    ],
    "examples": {"amt.example.org/daten/{x}": [{"dataset_id": "t.a", "url": "https://amt.example.org/daten/a",
                                                "reason": "no_title"}]},
}
REPORTS = {
    "govdata": {
        "source_id": "govdata", "finds": 100, "written": 5, "blocked": 0, "failed": 0,
        "verdicts": {"ok": 90, "not_geodata": 10}, "waiting": {}, "stack": {"batch_id": 7, "entries": 12, "created": True},
        "files": ["2026-11-25-govdata.yaml"],
        "flagged": {"W6": {"count": 1, "examples": [{"dataset_id": "govdata.m", "title": "", "link": "", "why": "mail"}]},
                    "W1": {"count": 1, "examples": [{"dataset_id": "govdata.s", "title": "Verkehrsstatistik",
                                                     "link": "https://x.example.org/s", "why": "*statistik"}]}},
    }
}
DECIDED = [
    {"file": "2026-11-25-govdata.yaml", "source_id": "govdata", "batch_id": 7, "entries": 12, "excluded": 2,
     "decision": "pending", "would_approve": False, "reasons": ["6000 Einträge, mehr als 5000"], "sample_passed": 9,
     "sample": 10},
]


def test_the_findings_of_a_run_put_the_guard_first() -> None:
    found = findings_of(
        linkcheck=LINKCHECK, reports=REPORTS, decided=DECIDED,
        spellings={"added": [], "waiting": [["CC BY-NC-SA 4.0", 7], ["einmal", 1]]},
        source_errors={"data-gv-at": "Der Harvest endete mit Fehler"}, run_error=None, open_prs=["410"],
        folder="docs/harvest/laeufe/2026-11-25",
    )
    keys = [f.key for f in found]
    assert keys[0] == "SCHUTZ host spa.example.org"
    assert {"MUSTER amt.example.org/daten/{x}", "WARNZEICHEN W1 govdata", "WARNZEICHEN W6 govdata",
            "STAPEL govdata 7", "LIZENZ CC BY-NC-SA 4.0", "QUELLE data-gv-at", "PR 410"} <= set(keys)
    assert "LIZENZ einmal" not in keys


def test_a_failed_link_check_is_a_finding() -> None:
    found = findings_of(linkcheck=None, reports={}, decided=[], spellings=None, source_errors={}, run_error=None,
                        open_prs=[], folder="f", linkcheck_error="Die Linkpruefung ist gescheitert.")
    assert [f.key for f in found] == ["LINKPRUEFUNG"]


def test_the_files_of_a_run_are_cleaned_and_hide_contact_details() -> None:
    files = run_files(
        day=DAY, folder="docs/harvest/laeufe/2026-11-25", trial=True, linkcheck=LINKCHECK, reports=REPORTS,
        decided=DECIDED, spellings={"added": [{"license_ref": "cc-by-4.0", "statement": "CC BY 4.0", "rule": "S2"}],
                                    "waiting": [["CC BY-NC-SA 4.0", 7]]},
        source_errors={}, run_error=None,
        published=(1, [("Bodenkarte", "https://amt.example.org/b?token=geheim", "govdata/Amt/cc-by-4.0",
                        "approvals/2026-11-24-govdata.yaml")]),
        classify={"govdata": "Ergebnis: ok 90\nFingerabdruck " + "b" * 64},
    )
    assert set(files) == {"README.md", "linkpruefung.md", "warnzeichen.md", "lizenzangaben.md", "govdata-classify.md",
                          "fehler.log"}
    readme = files["README.md"]
    assert "Probelauf" in readme and "bleibt pending" in readme and "Seit dem letzten Lauf" in readme
    assert "geheim" not in readme and "b" * 64 not in files["govdata-classify.md"]
    assert "govdata.m (Titel und Link nicht gezeigt: Kontaktangabe)" in files["warnzeichen.md"]
    assert "**geschützt** host `spa.example.org`" in files["linkpruefung.md"]
    assert files["fehler.log"].startswith("keine")


def test_the_pr_text_of_an_approved_run_names_how_to_take_it_back() -> None:
    decided = [dict(DECIDED[0], decision="approved", would_approve=True, reasons=[])]
    files = run_files(
        day=DAY, folder="f", trial=False, linkcheck=None, reports=REPORTS, decided=decided, spellings=None,
        source_errors={}, run_error="Bericht: gescheitert", published=(0, []), classify={},
    )
    assert "revoked_on: <Tag>" in files["README.md"] and "Gescheitert" in files["README.md"]


def test_a_pause_is_a_note_in_the_files_of_the_run_and_no_finding_and_no_error() -> None:
    files = run_files(
        day=DAY, folder="f", trial=False, linkcheck=None, reports=REPORTS, decided=[], spellings=None,
        source_errors={}, run_error=None, published=(0, []), classify={},
        source_pauses={"govdata": "govdata: Lauf 4 (inkrementell) interrupted (Seiten je Lauf erreicht)"},
    )
    assert "**govdata:** Hinweis, planmäßige Pause (kein Fehler): govdata: Lauf 4" in files["README.md"]
    assert "gescheitert" not in files["README.md"] and files["fehler.log"].startswith("keine")


def test_the_note_of_a_pause_is_the_report_line_of_the_source_and_never_a_log_line(tmp_path: Path) -> None:
    (tmp_path / "quellen-pause.txt").write_text("govdata\nopendata-swiss\nfsdi-stac\n", encoding="utf-8")
    (tmp_path / "harvest-govdata.txt").write_text(
        '{"level": "INFO", "message": "gateway request"}\n\n'
        "govdata: Lauf 4 (inkrementell) interrupted (Seiten je Lauf erreicht)\n  Anfragen 2\n",
        encoding="utf-8",
    )
    (tmp_path / "harvest-opendata-swiss.txt").write_text(
        "opendata-swiss: kein Lauf gestartet – die Quelle bat mit 429 um Pause\n", encoding="utf-8"
    )
    # A source that printed nothing the summary can use still gets a note, never an error.
    (tmp_path / "harvest-fsdi-stac.txt").write_text('{"level": "INFO"}\n', encoding="utf-8")
    assert _pauses(tmp_path) == {
        "govdata": "govdata: Lauf 4 (inkrementell) interrupted (Seiten je Lauf erreicht)",
        "opendata-swiss": "opendata-swiss: kein Lauf gestartet – die Quelle bat mit 429 um Pause",
        "fsdi-stac": "der nächste Lauf setzt fort",
    }
    assert _pauses(tmp_path / "nowhere") == {}


def test_the_message_of_a_failed_step_is_one_line_with_the_reason_and_cleaned_in_the_repository(tmp_path: Path) -> None:
    reason = "report failed: spellings.yaml: not valid YAML: an anchor is not allowed (line 8)"
    (tmp_path / "lauf-fehler.txt").write_text(
        f"\ufeffLizenzen: Der Bericht von govdata ist gescheitert. Grund: {reason}\r\n  in /home/otto/earthx\r\n",
        encoding="utf-8",
    )
    text = _text(tmp_path / "lauf-fehler.txt")
    assert text is not None and "\n" not in text and reason in text and len(text) <= 500
    files = run_files(
        day=DAY, folder="f", trial=False, linkcheck=None, reports={}, decided=[], spellings=None, source_errors={},
        run_error=text, published=(0, []), classify={},
    )
    # fehler.log and the text of the pull request name the line; a path on Otto's computer does not get in.
    for name in ("fehler.log", "README.md"):
        assert "an anchor is not allowed (line 8)" in files[name] and "/home/otto" not in files[name], name
    assert _text(tmp_path / "missing.txt") is None
    (tmp_path / "long.txt").write_text("x " * 600, encoding="utf-8")
    assert len(_text(tmp_path / "long.txt") or "") == 500

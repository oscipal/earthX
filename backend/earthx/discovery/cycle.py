"""The steps of a harvest run that ``scripts/harvest-cycle.ps1`` hands to the container (M5-67;
docs/plans/m5/m5-67-harvest-automatisch.md §3, §6, §8, §9; adr/0033 §8.5).

    python -m earthx.discovery.cycle sources
    python -m earthx.discovery.cycle decide --run /run --approvals /approvals [--trial] <file>...
    python -m earthx.discovery.cycle summary --run /run --harvest /harvest --approvals /approvals --day <day> [--trial]

- ``sources``: the enabled sources, one id a line, by precedence among duplicates (FSDI first).
- ``decide``: approval by fixed rules (Otto, 24.11.2026): each new approval file gets the link check of its sample and
  ``approved`` with ``decided_by: rules`` where the rules of ``backend/catalog/approval_rules.yaml`` hold, else it
  stays ``pending``. Licences are never graded here. In the trial run (the first, F7 = 1) every file stays pending and
  the run files say what the rules would have done.
- ``summary``: the files of the run under ``docs/harvest/laeufe/<day>/`` and the part of ``docs/harvest/befunde.md``
  the runs keep, from the numbers the steps left in the run's own folder outside the repository; the text of the pull
  request and the line for the window. Everything that goes into the repository passes :func:`clean` first: no AOI
  (a run has none), no hash, no signed address, no mail address, no value of the environment.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
import yaml

from earthx.catalog.approvals import APPROVALS_DIR, is_file_name, load_approvals
from earthx.catalog.datasets import CATALOG_DIR
from earthx.catalog.entry_files import EntryFileError, read_yaml
from earthx.catalog.registry import ConfigError
from earthx.catalog.sources import read_sources
from earthx.discovery.report import dump_approval
from earthx.logging import configure_logging

__all__ = [
    "APPROVAL_RULES_FILE",
    "SKIPPED_TEXT",
    "ApprovalRules",
    "Finding",
    "candidate_lines",
    "clean",
    "decide",
    "merge_findings",
    "read_approval_rules",
]

APPROVAL_RULES_FILE = CATALOG_DIR / "approval_rules.yaml"
AUTO_START = "<!-- auto:start -->"
AUTO_END = "<!-- auto:end -->"
DONE_HEADING = "## Erledigt"

# --- Cleaning ---------------------------------------------------------------------------------------------------------

_SECRET_PARAM = re.compile(
    r"([?&])((?:x-amz-|x-goog-)[\w-]*|signature|sig|token|key|apikey|api_key|access_token|expires|credential)=[^&\s#>)]*",
    re.IGNORECASE,
)
_HASH = re.compile(r"\b[0-9a-f]{64}\b")
# Only from the start of a word: else a long word without "@" is tried from each of its letters (quadratic time).
_MAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_ENV = re.compile(r"\b(PG\w+|POSTGRES_\w+|EARTHX_\w+|GH_TOKEN|GITHUB_TOKEN)=\S+")
# A path on Otto's computer names his account: C:\Users\<name>\..., /home/<name>/..., /Users/<name>/...
_LOCAL_PATH = re.compile(r"(?i)\b[a-z]:\\(?:users|dokumente und einstellungen|documents and settings)\\[^\s'\"`<>]+|"
                         r"(?<![\w.])/(?:home|Users)/[^\s'\"`<>]+")


def clean(text: str) -> str:
    """Text for the public repository: signed query parameters, SHA-256 hashes, mail addresses, assignments of the
    environment and paths on Otto's computer are taken out."""
    text = _SECRET_PARAM.sub(lambda m: f"{m[1]}{m[2]}=[entfernt]", text)
    text = _HASH.sub("[Hash]", text)
    text = _MAIL.sub("[Mail]", text)
    text = _LOCAL_PATH.sub("[Pfad]", text)
    return _ENV.sub(lambda m: f"{m[1]}=[entfernt]", text)


def finding_key(key: str) -> str:
    """A key the list of findings can read back: cleaned, on one line, without ``*`` and at most 100 characters."""
    return " ".join(clean(key).replace("*", " ").split())[:100]


# --- Approval by rules ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ApprovalRules:
    max_entries: int
    max_share_of_published: float
    min_cap: int
    max_failed_share: float


def read_approval_rules(path: Path = APPROVAL_RULES_FILE) -> ApprovalRules:
    data = read_yaml(path)
    keys = {"max_entries", "max_share_of_published", "min_cap", "max_failed_share"}
    if not isinstance(data, dict) or set(data) != keys:
        raise EntryFileError(f"{path.name}: holds exactly {', '.join(sorted(keys))}")
    for key in ("max_entries", "min_cap"):
        if isinstance(data[key], bool) or not isinstance(data[key], int) or data[key] < 1:
            raise EntryFileError(f"{path.name}: {key} is a whole number above 0")
    for key in ("max_share_of_published", "max_failed_share"):
        value = data[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= 1:
            raise EntryFileError(f"{path.name}: {key} is a share above 0 and at most 1")
    return ApprovalRules(data["max_entries"], float(data["max_share_of_published"]), data["min_cap"],
                         float(data["max_failed_share"]))


def decide(
    document: Mapping[str, Any], *, published: int, finds: int, failed: int, rules: ApprovalRules
) -> list[str]:
    """Why the stack of ``document`` waits for Otto, in German; empty where the rules approve it (plan §6)."""
    reasons = []
    entries = int(document["entries"])
    left = entries - len(document.get("excluded_entries") or ())
    cap = max(rules.min_cap, int(rules.max_share_of_published * published))
    if left <= 0:
        reasons.append("nach den Warnzeichen bleibt kein Eintrag")
    if entries > rules.max_entries:
        reasons.append(f"{entries} Einträge, mehr als {rules.max_entries}")
    elif entries > cap:
        reasons.append(f"{entries} Einträge, mehr als {cap} ({rules.max_share_of_published:.0%} der {published} sichtbaren)")
    if finds and failed > rules.max_failed_share * finds:
        reasons.append(f"{failed} von {finds} Funden nicht ableitbar")
    return reasons


def _checks(conn: psycopg.Connection, sample: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """The link check of each entry of the sample, for the link the file names; ``not_checked`` where there is none."""
    ids = [str(item["dataset_id"]) for item in sample]
    with conn.cursor() as cur:
        cur.execute(
            "SELECT dataset_id, url, outcome, reason, status, final_host, guarded FROM public.earthx_link_check"
            " WHERE dataset_id = ANY(%s)",
            (ids,),
        )
        rows = {row[0]: row[1:] for row in cur.fetchall()}
    found = {}
    for item in sample:
        row = rows.get(str(item["dataset_id"]))
        if row is None or row[0] != item.get("source_url"):
            found[str(item["dataset_id"])] = {"outcome": "unchecked", "reason": "not_checked"}
            continue
        _, outcome, reason, status, final_host, guarded = row
        note: dict[str, Any] = {"outcome": outcome, "reason": reason}
        if guarded:
            note = {"outcome": "unchecked", "reason": "guarded"}
        if status is not None:
            note["status"] = status
        if final_host is not None:
            note["final_host"] = final_host
        found[str(item["dataset_id"])] = note
    return found


def _published(conn: psycopg.Connection, source_id: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM public.earthx_listed_entry WHERE source_id = %s AND state = 'published'", (source_id,)
        )
        return int(cur.fetchone()[0])


def decide_files(
    conn: psycopg.Connection,
    paths: Sequence[Path],
    *,
    reports: Mapping[str, Mapping[str, Any]],
    rules: ApprovalRules,
    day: date,
    trial: bool,
) -> list[dict[str, Any]]:
    """Fill in the sample's link check and decide each file by the rules; returns what was decided, per file."""
    decided = []
    for path in paths:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if document.get("decision") != "pending":
            continue
        report = reports.get(document["source_id"], {})
        checks = _checks(conn, document.get("sample") or [])
        for item in document.get("sample") or []:
            item["check"] = checks[str(item["dataset_id"])]
            item["ok"] = item["check"]["outcome"] == "passed"
        reasons = decide(
            document,
            published=_published(conn, document["source_id"]),
            finds=int(report.get("finds", 0)),
            failed=int(report.get("failed", 0)),
            rules=rules,
        )
        approved = not reasons and not trial
        if approved:
            document.update(decision="approved", decided_on=day, decided_by="rules")
        else:
            for item in document.get("sample") or []:
                item["ok"] = None
        path.write_text(dump_approval(document), encoding="utf-8")
        decided.append(
            {
                "file": path.name,
                "source_id": document["source_id"],
                "batch_id": document["batch_id"],
                "entries": document["entries"],
                "excluded": len(document.get("excluded_entries") or ()),
                "decision": document["decision"],
                "would_approve": not reasons,
                "reasons": reasons,
                "sample_passed": sum(1 for c in checks.values() if c["outcome"] == "passed"),
                "sample": len(checks),
            }
        )
    if paths:
        load_approvals(paths[0].parent)  # every file written must still load
    return decided


# --- The list of findings ---------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Finding:
    """One open finding of the runs: a key that stays the same from run to run, and its text of this run."""

    key: str
    text: str
    #: Lines under the finding, each one point (the patterns of a guarded host).
    items: tuple[str, ...] = ()


_LINE = re.compile(r"- \[ \] \*\*(?P<key>[^*]+)\*\* · seit (?P<since>\d{4}-\d{2}-\d{2}) · zuletzt \d{4}-\d{2}-\d{2} · ")


def merge_findings(document: str, findings: Sequence[Finding], day: date) -> str:
    """``befunde.md`` with the part of the runs replaced: each open finding with the day it was first seen, those of the
    last run that no longer occur ticked under "Erledigt". The parts by hand stay as they are."""
    if AUTO_START not in document or AUTO_END not in document or DONE_HEADING not in document:
        raise ValueError("befunde.md lacks the markers of the runs or the section Erledigt")
    head, rest = document.split(AUTO_START, 1)
    old, tail = rest.split(AUTO_END, 1)
    previous = {m["key"]: (m["since"], line) for line in old.splitlines() if (m := _LINE.match(line))}
    keyed = {finding_key(f.key): f for f in findings}
    current = set(keyed)
    lines = [
        f"- [ ] **{key}** · seit {previous.get(key, (day.isoformat(), ''))[0]} · zuletzt {day.isoformat()} · "
        + " ".join(clean(f.text).split())
        + "".join(f"\n  - {' '.join(clean(item).split())}" for item in f.items)
        for key, f in keyed.items()
    ]
    body = "\n".join(lines) if lines else f"Keine offenen Befunde aus dem Lauf vom {day.isoformat()}."
    done = [
        f"- [x] **{key}** · {since} bis {day.isoformat()} · im Lauf vom {day.isoformat()} nicht mehr aufgetreten"
        for key, (since, _) in previous.items()
        if key not in current
    ]
    tail = tail.rstrip("\n") + ("\n" + "\n".join(done) if done else "") + "\n"
    return f"{head}{AUTO_START}\n{body}\n{AUTO_END}{tail}"


def _examples(items: Sequence[Mapping[str, Any]], limit: int = 3) -> str:
    shown = []
    for item in items[:limit]:
        title = item.get("title") or item.get("dataset_id")
        link = item.get("link") or item.get("url") or ""
        shown.append(f"„{str(title)[:80]}“" + (f" <{link}>" if link else ""))
    return "; ".join(shown)


#: The patterns of a guarded host shown in the list of findings; the others are in ``linkpruefung.md``.
GUARD_PATTERNS_SHOWN = 5


def _counts(group: Mapping[str, Any]) -> str:
    return f"{group['failed']} durchgefallen, {group['transient']} ohne Antwort, {group['passed']} bestanden"


def guard_findings(groups: Sequence[Mapping[str, Any]]) -> list[Finding]:
    """One finding per host with a guarded result (plan §4c), its guarded patterns as points with their numbers, the
    largest first, so that ``befunde.md`` stays readable (Otto, 25.11.2026)."""
    hosts = {g["key"]: g for g in groups if g["kind"] == "host"}
    patterns: dict[str, list[Mapping[str, Any]]] = {}
    for group in groups:
        if group["kind"] == "pattern" and group["guarded"]:
            patterns.setdefault(re.split(r"[/?#]", group["key"], maxsplit=1)[0], []).append(group)
    guarded = [key for key, group in hosts.items() if group["guarded"]]
    found = []
    for host in guarded + sorted(set(patterns) - set(guarded)):
        group = hosts.get(host)
        if group is not None and group["guarded"]:
            text = f"Host: {_counts(group)}; nichts verborgen, nichts freigegeben, liegt eher an der Prüfung."
        else:
            text = "Host nicht geschützt; in den Mustern unten nichts verborgen, nichts freigegeben."
        own = sorted(patterns.get(host, []), key=lambda g: -(g["failed"] + g["transient"] + g["passed"]))
        items = [f"`{g['key']}`: {_counts(g)}" for g in own[:GUARD_PATTERNS_SHOWN]]
        if len(own) > GUARD_PATTERNS_SHOWN:
            items.append(f"und {len(own) - GUARD_PATTERNS_SHOWN} weitere Muster, siehe `linkpruefung.md`")
        found.append(Finding(f"SCHUTZ {host}", text, tuple(items)))
    return found


def findings_of(
    *,
    linkcheck: Mapping[str, Any] | None,
    reports: Mapping[str, Mapping[str, Any]],
    decided: Sequence[Mapping[str, Any]],
    spellings: Mapping[str, Any] | None,
    source_errors: Mapping[str, str],
    run_error: str | None,
    open_prs: Sequence[str],
    folder: str,
    linkcheck_error: str | None = None,
    propose: Mapping[str, Any] | None = None,
    propose_error: str | None = None,
) -> list[Finding]:
    """The findings of this run, the guarded hosts with their patterns first (plan §4c)."""
    found: list[Finding] = []
    if run_error:
        found.append(Finding("LAUF", f"Lauf gescheitert: {run_error}. Siehe `{folder}/fehler.log`."))
    if linkcheck_error:
        found.append(Finding("LINKPRUEFUNG", f"{linkcheck_error} Nichts verborgen, nichts Neues sichtbar."))
    if propose_error:
        found.append(Finding("KANDIDATEN", f"{propose_error} In diesem Lauf keine Kandidaten des vollen Wegs."))
    for source_id, count in sorted(((propose or {}).get("sources") or {}).items()) if not propose_error else ():
        if count.get("error"):
            found.append(Finding(f"KANDIDATEN {source_id}", f"Kandidaten gescheitert ({count['error']})."))
    if linkcheck:
        examples = linkcheck.get("examples") or {}
        found += guard_findings(linkcheck.get("groups") or [])
        for form in linkcheck.get("forms") or []:
            found.append(
                Finding(
                    f"UNGEPRUEFT {form['link']}",
                    f"{form['count']} Links ohne sichere Prüfung, ihre Einträge bleiben unsichtbar."
                    if form["reason"] == "no_safe_check"
                    else f"{form['count']} Links: Prüfung über die Schnittstelle, wartet auf Ottos Bestätigung der"
                    " Adressform (`form_confirmed_on` in `linkcheck.yaml`); bis dahin unsichtbar.",
                )
            )
        for group in linkcheck.get("groups") or []:
            failed = group["failed"] + group.get("gone", 0)
            if group["kind"] == "pattern" and not group["guarded"] and failed >= 5:
                found.append(
                    Finding(
                        f"MUSTER {group['key']}",
                        f"{failed} durchgefallen, {group['unchecked']} nicht prüfbar, {group['passed']}"
                        f" bestanden. Beispiele: {_examples(examples.get(group['key'], []))}",
                    )
                )
    for source_id, numbers in sorted(reports.items()):
        for code, flagged in sorted((numbers.get("flagged") or {}).items()):
            found.append(
                Finding(
                    f"WARNZEICHEN {code} {source_id}",
                    f"{flagged['count']} Einträge warten. Beispiele: {_examples(flagged.get('examples') or [])}",
                )
            )
    for item in decided:
        if not item["would_approve"]:
            found.append(
                Finding(
                    f"STAPEL {item['source_id']} {item['batch_id']}",
                    f"bleibt pending: {'; '.join(item['reasons'])}. Freigabedatei `{item['file']}`.",
                )
            )
    for statement, count in ((spellings or {}).get("waiting") or [])[:10]:
        if count >= 2:
            found.append(Finding(f"LIZENZ {statement[:60]}", f"{count} Funde warten auf eine Einstufung von Otto."))
    for source_id, message in sorted(source_errors.items()):
        found.append(Finding(f"QUELLE {source_id}", f"Harvest gescheitert: {message} {REPORT_SKIPPED}"))
    for pr in open_prs:
        found.append(Finding(f"PR {pr}", "PR eines früheren Laufs ist noch offen (nicht gemergt)."))
    return found


# --- The files of the run ---------------------------------------------------------------------------------------------


def _published_since(conn: psycopg.Connection, files: Sequence[str], since: date | None, seed: str) -> tuple[int, list]:
    """Entries published by rules since ``since``: their number and ten of them, drawn with ``seed``."""
    if not files or since is None:
        return 0, []
    names = [f"approvals/{name}" for name in files]
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM public.earthx_listed_entry WHERE approval_file = ANY(%s) AND state = 'published'"
            " AND published_at::date >= %s",
            (names, since),
        )
        count = int(cur.fetchone()[0])
        cur.execute(
            "SELECT content->>'title', content->'earthx:listing'->>'source_url', license_rule, approval_file"
            " FROM public.earthx_listed_entry WHERE approval_file = ANY(%s) AND state = 'published'"
            " AND published_at::date >= %s ORDER BY md5(dataset_id || %s) LIMIT 10",
            (names, since, seed),
        )
        return count, cur.fetchall()


def _rule_files(approvals: Path) -> list[str]:
    return sorted(
        path.name
        for path in approvals.glob("*.yaml")
        if (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("decided_by") == "rules"
    )


#: Why a find became no candidate, in German (``discovery.propose``).
#: What the files of the run add to a source whose harvest failed: its report does not run (plan M5-67 §3 step 5).
REPORT_SKIPPED = "Bericht übersprungen: ohne Ernte entfällt er in diesem Lauf."

SKIPPED_TEXT = {
    "no_format": "kein lesbares Format",
    "no_takeover": "nicht ablösbar",
    "full_entry": "schon voller Eintrag",
    "licence_changed": "Lizenz seit dem Bericht geändert",
    "tier_catalog": "Lizenzstufe catalog",
    "budget": "über dem Verify-Budget",
    "no_items": "keine Items",
    "account": "Konto",
    "verify_failed": "Verify gescheitert",
    "limit": "über der Grenze 20",
    "file_unreadable": "Kandidatendatei nicht lesbar",
}


def candidate_lines(propose: Mapping[str, Any] | None) -> list[str]:
    """The section on the candidates of the full way (M5-20 plan §14.1.6): per source the numbers, then the new and
    changed candidates; empty where the step did not run."""
    if not propose:
        return []
    lines = ["", "## Kandidaten des vollen Wegs", ""]
    if propose.get("trial"):
        lines += ["Probelauf: Kandidaten geschrieben, nichts entschieden.", ""]
    written = []
    for source_id, count in sorted((propose.get("sources") or {}).items()):
        if count.get("error"):
            lines.append(f"- **{source_id}:** gescheitert ({count['error']})")
            continue
        skipped = ", ".join(f"{SKIPPED_TEXT.get(k, k)} {n}" for k, n in sorted((count.get("skipped") or {}).items()))
        lines.append(
            f"- **{source_id}:** neu {count['new']}, geändert {count['changed']}, unverändert {count['unchanged']},"
            f" Zustand fortgeschrieben {count['state_updated']}; übersprungen: {skipped or '–'}"
        )
        written += [(source_id, item) for item in count.get("written") or ()]
    if written:
        lines += ["", "| Quelle | Vorschlag ID | Titel | Format | Lizenz | Stufe | Freigabe |", "|---|---|---|---|---|---|---|"]
        for source_id, item in written:
            # One line, no table cell break, and no "@name" that would notify someone in the pull request.
            title = " ".join(str(item.get("title") or "").split()).replace("|", "/").replace("@", "(at)")[:80]
            decision = "nach Regeln" if item.get("decision") == "cleared" else "Probelauf, offen"
            lines.append(
                f"| {source_id} | `{item['proposed_id']}` | {title} | {item.get('format') or '–'}"
                f" | {item.get('license') or '–'} | {item.get('tier')} | {decision} |"
            )
        lines += ["", "Dateien unter `backend/catalog/candidates/<Quelle>/`; herausnehmen über `blocked.yaml`."]
    return lines


def run_files(
    *,
    day: date,
    folder: str,
    trial: bool,
    linkcheck: Mapping[str, Any] | None,
    reports: Mapping[str, Mapping[str, Any]],
    decided: Sequence[Mapping[str, Any]],
    spellings: Mapping[str, Any] | None,
    source_errors: Mapping[str, str],
    run_error: str | None,
    published: tuple[int, list],
    classify: Mapping[str, str],
    source_pauses: Mapping[str, str] | None = None,
    propose: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """The files of the run by name, in German, cleaned."""
    files: dict[str, str] = {}
    lines = [f"# Harvest-Lauf {day.isoformat()}" + (" (Probelauf)" if trial else ""), ""]
    if trial:
        lines += ["Probelauf (F7 = 1): nichts verborgen, nichts freigegeben; die Zahlen zeigen, was die Regeln täten.", ""]
    if run_error:
        lines += [f"**Gescheitert:** {run_error} (`fehler.log`).", ""]
    lines += ["## Quellen", ""]
    for source_id, numbers in sorted(reports.items()):
        stack = numbers.get("stack")
        lines.append(
            f"- **{source_id}:** Funde {numbers['finds']}, nicht ableitbar {numbers['failed']}; Ergebnis "
            + ", ".join(f"{k} {v}" for k, v in sorted(numbers["verdicts"].items()))
            + "; warten "
            + (", ".join(f"{k} {v}" for k, v in sorted(numbers["waiting"].items())) or "–")
            + ("; kein Stapel" if stack is None else f"; Stapel {stack['batch_id']} mit {stack['entries']} Einträgen")
        )
    for source_id, message in sorted(source_errors.items()):
        lines.append(f"- **{source_id}:** Harvest gescheitert: {message} {REPORT_SKIPPED}")
    for source_id, message in sorted((source_pauses or {}).items()):
        lines.append(f"- **{source_id}:** Hinweis, planmäßige Pause (kein Fehler): {message}")
    lines += ["", "## Freigabe nach Regeln", ""]
    for item in decided:
        verdict = "freigegeben" if item["decision"] == "approved" else "bleibt pending"
        why = "Regeln erfüllt" if item["would_approve"] else "; ".join(item["reasons"])
        lines.append(
            f"- `{item['file']}`: {verdict} ({why}); {item['entries']} Einträge, davon {item['excluded']} mit"
            f" Warnzeichen draußen; Stichprobe {item['sample_passed']} von {item['sample']} Links bestanden."
            + (" Rücknahme: `revoked_on: <Tag>` in dieser Datei." if item["decision"] == "approved" else "")
        )
    if not decided:
        lines.append("- kein neuer Stapel")
    count, sample = published
    lines += ["", "## Seit dem letzten Lauf automatisch veröffentlicht", "", f"{count} Einträge. Zum Nachsehen:", ""]
    lines += [f"- {title} — <{link}> — `{rule}` (`{approval}`)" for title, link, rule, approval in sample] or ["- keine"]
    if linkcheck:
        lines += [
            "",
            "## Linkprüfung",
            "",
            f"Fällig {linkcheck['due']}, geprüft {linkcheck['checked']}: "
            + ", ".join(f"{k} {v}" for k, v in sorted(linkcheck["outcomes"].items()))
            + f"; verborgen {linkcheck['applied']['hidden']}, zurück {linkcheck['applied']['restored']}"
            + (" (Probelauf: würde)" if linkcheck.get("dry_run") else "")
            + ". Einzelheiten in `linkpruefung.md`.",
        ]
    lines += candidate_lines(propose)
    lines += ["", f"Offene Befunde: `docs/harvest/befunde.md`. Dateien dieses Laufs: `{folder}/`."]
    files["README.md"] = "\n".join(lines) + "\n"
    if linkcheck:
        link = ["# Linkprüfung", "", "## Fällig je Host (Links, Stunden bei seinem Abstand)", ""]
        link += [f"- {host}: {count} Links, rund {hours} h" for host, count, hours in linkcheck["due_by_host"]]
        link += ["", "## Gründe", ""] + [f"- {k}: {v}" for k, v in sorted(linkcheck["reasons"].items())]
        link += ["", "## Hosts und Muster mit Fehlschlägen (geschützte zuerst)", ""]
        for group in linkcheck["groups"]:
            link.append(
                f"- {'**geschützt** ' if group['guarded'] else ''}{group['kind']} `{group['key']}`: bestanden"
                f" {group['passed']}, durchgefallen {group['failed']}, ohne Antwort {group['transient']},"
                f" weg (404/410) {group.get('gone', 0)}, nicht prüfbar {group['unchecked']}"
            )
            for example in (linkcheck.get("examples") or {}).get(group["key"], []) if group["kind"] == "pattern" else []:
                link.append(f"  - {example['dataset_id']} <{example['url']}> `{example['reason']}`")
        files["linkpruefung.md"] = "\n".join(link) + "\n"
    flags = ["# Warnzeichen", ""]
    for source_id, numbers in sorted(reports.items()):
        for code, flagged in sorted((numbers.get("flagged") or {}).items()):
            flags.append(f"## {source_id} {code}: {flagged['count']}")
            flags.append("")
            for item in flagged.get("examples") or []:
                shown = item["title"] or f"{item['dataset_id']} (Titel und Link nicht gezeigt: Kontaktangabe)"
                flags.append(f"- {shown}" + (f" — <{item['link']}>" if item["link"] else "") + f" — `{item['why']}`")
            flags.append("")
    files["warnzeichen.md"] = "\n".join(flags) + ("\nkeine\n" if len(flags) == 2 else "")
    licences = ["# Lizenzangaben", "", "## Automatisch zugeordnet (nie eine Einstufung)", ""]
    licences += [f"- {a['rule']} `{a['license_ref']}`: {a['statement'][:200]}" for a in (spellings or {}).get("added", [])]
    licences += ["", "## Wartend (häufigste)", ""]
    licences += [f"- {count}: {statement[:200]}" for statement, count in (spellings or {}).get("waiting", [])]
    files["lizenzangaben.md"] = "\n".join(licences) + "\n"
    for source_id, text in sorted(classify.items()):
        excerpt = [line[:300] for line in text.splitlines()[:600]]
        files[f"{source_id}-classify.md"] = f"# Classify-Auszug {source_id}\n\n```\n" + "\n".join(excerpt) + "\n```\n"
    errors = ([run_error] if run_error else []) + [f"{source_id}: {message}" for source_id, message in sorted(source_errors.items())]
    files["fehler.log"] = "\n".join(errors or ["keine"]) + "\n"
    return {name: clean(text) for name, text in files.items()}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _text(path: Path) -> str | None:
    """A short message a step of the script left (UTF-8, perhaps with a byte order mark), or ``None``. One line, long
    enough for the step and the line that says why it failed."""
    if not path.exists():
        return None
    return " ".join(path.read_text(encoding="utf-8-sig").split())[:500] or None


def _pauses(run: Path) -> dict[str, str]:
    """The sources whose harvest paused on purpose (``quellen-pause.txt``: one source id a line, M5-67 fix 1), each with
    the line of what its harvest printed (``harvest-<source>.txt``) that starts with the source's id: the report line
    (``<id>: Lauf 4 (inkrementell) interrupted (...)``) or the note of a rest. Log lines of the gateway (JSON) are skipped."""
    listed = run / "quellen-pause.txt"
    if not listed.exists():
        return {}
    found = {}
    for source_id in listed.read_text(encoding="utf-8-sig").split():
        printed = run / f"harvest-{source_id}.txt"
        lines = printed.read_text(encoding="utf-8-sig").splitlines() if printed.exists() else []
        first = next((line for line in lines if line.startswith(f"{source_id}:")), "")
        found[source_id] = " ".join(first.split())[:300] or "der nächste Lauf setzt fort"
    return found


def _previous_run(harvest: Path, folder_name: str) -> date | None:
    days = sorted(p.name[:10] for p in (harvest / "laeufe").glob("????-??-??*") if p.name != folder_name)
    return date.fromisoformat(days[-1]) if days else None


def _folder(harvest: Path, day: date) -> Path:
    base = harvest / "laeufe" / day.isoformat()
    number = 1
    folder = base
    while folder.exists() and any(folder.iterdir()):
        number += 1
        folder = base.with_name(f"{day.isoformat()}-{number}")
    return folder


def summary(conn: psycopg.Connection, run: Path, harvest: Path, approvals: Path, day: date, trial: bool) -> str:
    """Write the files of the run and the findings; returns the line for the window."""
    reports = {path.stem.removeprefix("report-"): _load(path) for path in sorted(run.glob("report-*.json"))}
    linkcheck = _load(run / "linkcheck.json")
    decided = _load(run / "decide.json") or []
    spellings = _load(run / "spellings.json")
    errors_file = run / "quellen-fehler.txt"
    source_errors = {}
    if errors_file.exists():
        for line in errors_file.read_text(encoding="utf-8").splitlines():
            source_id, _, message = line.partition(":")
            if source_id.strip():
                source_errors[source_id.strip()] = message.strip()[:200]
    source_pauses = _pauses(run)
    run_error = _text(run / "lauf-fehler.txt")
    linkcheck_error = _text(run / "linkpruefung-fehler.txt")
    propose = _load(run / "propose.json")
    propose_error = _text(run / "kandidaten-fehler.txt")
    open_prs = (run / "offene-prs.txt").read_text(encoding="utf-8").split() if (run / "offene-prs.txt").exists() else []
    classify = {path.stem.removeprefix("classify-"): path.read_text(encoding="utf-8") for path in sorted(run.glob("classify-*.txt"))}
    folder = _folder(harvest, day)
    relative = f"docs/harvest/laeufe/{folder.name}"
    published = _published_since(conn, _rule_files(approvals), _previous_run(harvest, folder.name), day.isoformat())
    files = run_files(
        day=day, folder=relative, trial=trial, linkcheck=linkcheck, reports=reports, decided=decided,
        spellings=spellings, source_errors=source_errors, run_error=run_error, published=published, classify=classify,
        source_pauses=source_pauses, propose=propose,
    )
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
    findings = findings_of(
        linkcheck=linkcheck, reports=reports, decided=decided, spellings=spellings, source_errors=source_errors,
        run_error=run_error, open_prs=open_prs, folder=relative, linkcheck_error=linkcheck_error, propose=propose,
        propose_error=propose_error,
    )
    befunde = harvest / "befunde.md"
    befunde.write_text(merge_findings(befunde.read_text(encoding="utf-8"), findings, day), encoding="utf-8")
    (run / "pr-body.md").write_text(
        files["README.md"] + "\n---\n_Geschrieben von `scripts/harvest-cycle.ps1` (M5-67)._\n", encoding="utf-8"
    )
    approved = sum(1 for item in decided if item["decision"] == "approved")
    hidden = (linkcheck or {}).get("applied", {}).get("hidden", 0)
    candidates = sum(len(c.get("written") or ()) for c in ((propose or {}).get("sources") or {}).values())
    line = (
        f"{len(reports)} Quellen, {approved} von {len(decided)} Stapeln freigegeben, {hidden} Einträge verborgen,"
        f" {candidates} Kandidaten des vollen Wegs,"
        f" {len(findings)} offene Befunde aus den Läufen"
        + (f", {len(source_pauses)} Quellen mit planmäßiger Pause" if source_pauses else "")
        + (" (Probelauf)" if trial else "")
    )
    (run / "ergebnis.txt").write_text(line + "\n", encoding="utf-8")
    return line


# --- Command line -----------------------------------------------------------------------------------------------------


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m earthx.discovery.cycle", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("sources", help="the enabled sources by precedence")
    decide_parser = commands.add_parser("decide", help="approve the new approval files by rules")
    decide_parser.add_argument("--run", type=Path, required=True)
    decide_parser.add_argument("--approvals", type=Path, default=APPROVALS_DIR)
    decide_parser.add_argument("--trial", action="store_true")
    decide_parser.add_argument("--day", type=date.fromisoformat, default=None)
    decide_parser.add_argument("files", nargs="*")
    summary_parser = commands.add_parser("summary", help="write the files of the run and the findings")
    summary_parser.add_argument("--run", type=Path, required=True)
    summary_parser.add_argument("--harvest", type=Path, required=True)
    summary_parser.add_argument("--approvals", type=Path, default=APPROVALS_DIR)
    summary_parser.add_argument("--day", type=date.fromisoformat, required=True)
    summary_parser.add_argument("--trial", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    configure_logging()
    try:
        if args.command == "sources":
            enabled = [s for s in read_sources().values() if s.enabled]
            print("\n".join(s.source_id for s in sorted(enabled, key=lambda s: (s.dedupe_rank, s.source_id))))
            return 0
        with psycopg.connect(autocommit=True) as conn:
            if args.command == "decide":
                if not all(is_file_name(name) for name in args.files):
                    print("cycle failed: decide takes names of approval files", file=sys.stderr)
                    return 1
                reports = {p.stem.removeprefix("report-"): _load(p) for p in sorted(args.run.glob("report-*.json"))}
                decided = decide_files(
                    conn,
                    [args.approvals / name for name in args.files],
                    reports=reports,
                    rules=read_approval_rules(),
                    day=args.day or date.today(),
                    trial=args.trial,
                )
                (args.run / "decide.json").write_text(json.dumps(decided, ensure_ascii=False), encoding="utf-8")
                for item in decided:
                    print(f"{item['file']}: {item['decision']}" + (f" ({'; '.join(item['reasons'])})" if item["reasons"] else ""))
                return 0
            print(summary(conn, args.run, args.harvest, args.approvals, args.day, args.trial))
            return 0
    except (EntryFileError, ConfigError, ValueError) as error:
        print(f"cycle failed: {error}", file=sys.stderr)
        return 1
    except OSError as error:
        # Only the kind and the file name: a path in the container, never one of Otto's computer.
        print(f"cycle failed: a file cannot be read or written ({type(error).__name__}: {Path(str(error.filename)).name})",
              file=sys.stderr)
        return 1
    except psycopg.Error as error:
        print(f"cycle failed: database error {type(error).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

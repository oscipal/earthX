"""The approval files of the runs (adr/0033 §8.3; M5-20 plan §12): read strictly, checked before anything is published."""

from __future__ import annotations

from pathlib import Path

import pytest

from earthx.catalog.approvals import APPROVALS_DIR, load_approvals
from earthx.catalog.entry_files import EntryFileError
from earthx.catalog.sources import read_sources

FILE = """\
source_id: govdata
batch_id: 3
fingerprint: {fingerprint}
created_on: 2026-11-19
entries: 1
decision: {decision}
decided_on: {decided_on}
excluded_rules: []
revoked_on: {revoked_on}
sample:
- dataset_id: govdata.x
  why: all
  title: Bodenkarte
  source_url: https://amt.example.org/daten/x
  license_rule: govdata/Amt/cc-by-4.0
  ok: {ok}
"""


def _write(tmp_path: Path, name: str = "2026-11-19-govdata.yaml", **values: str) -> Path:
    fields = {"fingerprint": "a" * 64, "decision": "pending", "decided_on": "null", "revoked_on": "null", "ok": "null"}
    fields.update(values)
    (tmp_path / name).write_text(FILE.format(**fields), encoding="utf-8")
    return tmp_path


def test_every_shipped_approval_loads_and_is_consistent() -> None:
    sources = read_sources()
    for approval, name, sha in load_approvals(APPROVALS_DIR):
        assert approval.source_id in sources, name
        assert approval.decision in ("pending", "approved", "rejected"), name
        assert len(sha) == 64, name
        if approval.decision == "approved":
            assert approval.decided_on is not None, name
            assert approval.sample and all(check.ok is not None for check in approval.sample), name
        assert name == f"approvals/{approval.created_on.isoformat()}-{approval.source_id}.yaml", name


def test_a_pending_file_loads(tmp_path: Path) -> None:
    ((approval, name, sha),) = load_approvals(_write(tmp_path))
    assert (approval.decision, name, len(sha)) == ("pending", "approvals/2026-11-19-govdata.yaml", 64)


def test_an_approved_file_with_its_sample_checked_loads(tmp_path: Path) -> None:
    ((approval, _, _),) = load_approvals(_write(tmp_path, decision="approved", decided_on="2026-11-19", ok="false"))
    assert approval.decision == "approved" and approval.sample[0].ok is False


def test_the_report_beside_it_is_passed_over(tmp_path: Path) -> None:
    _write(tmp_path)
    (tmp_path / "2026-11-19-govdata.md").write_text("# Bericht\n", encoding="utf-8")
    assert len(load_approvals(tmp_path)) == 1


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"decision": "approved", "decided_on": "2026-11-19"}, "every entry of its sample checked"),
        ({"decision": "maybe", "decided_on": "2026-11-19"}, "pending, approved or rejected"),
        ({"decision": "approved", "ok": "true"}, "decided_on"),
        ({"decided_on": "2026-11-19"}, "decided_on"),
        ({"fingerprint": "XYZ"}, "fingerprint"),
        ({"revoked_on": "2026-11-19"}, "only an approved file can be revoked"),
        ({"decision": "approved", "decided_on": "2999-01-01", "ok": "true"}, "future"),
    ],
)
def test_a_wrong_file(tmp_path: Path, values: dict[str, str], message: str) -> None:
    with pytest.raises(EntryFileError, match=message):
        load_approvals(_write(tmp_path, **values))


def test_a_file_of_another_name(tmp_path: Path) -> None:
    with pytest.raises(EntryFileError, match="only <day>-<source_id>.yaml"):
        load_approvals(_write(tmp_path, name="freigabe.yaml"))


def test_an_unknown_field(tmp_path: Path) -> None:
    _write(tmp_path)
    path = tmp_path / "2026-11-19-govdata.yaml"
    path.write_text(path.read_text(encoding="utf-8") + "note: x\n", encoding="utf-8")
    with pytest.raises(EntryFileError):
        load_approvals(tmp_path)


def _with(tmp_path: Path, extra: str, *, check: str = "", **values: str) -> Path:
    """A file with fields of M5-67 added: ``extra`` at the top level, ``check`` under the entry of the sample."""
    _write(tmp_path, **values)
    path = tmp_path / "2026-11-19-govdata.yaml"
    text = path.read_text(encoding="utf-8")
    if check:
        text = text.rstrip("\n") + "\n  check: " + check + "\n"
    path.write_text(text + extra, encoding="utf-8")
    return tmp_path


DECIDED = {"decision": "approved", "decided_on": "2026-11-19", "ok": "true"}


def test_a_file_decided_by_the_rules_with_the_link_check_loads(tmp_path: Path) -> None:
    directory = _with(
        tmp_path,
        "decided_by: rules\nexcluded_entries: [govdata.y]\n",
        check="{outcome: passed, reason: ok, status: 200, final_host: amt.example.org, licence_seen: false}",
        **DECIDED,
    )
    ((approval, _, _),) = load_approvals(directory)
    assert approval.decided_by == "rules" and approval.excluded_entries == ("govdata.y",)
    note = approval.sample[0].check
    assert note is not None and (note.outcome, note.reason, note.final_host) == ("passed", "ok", "amt.example.org")


def test_an_older_file_without_the_new_fields_still_loads(tmp_path: Path) -> None:
    ((approval, _, _),) = load_approvals(_write(tmp_path, **DECIDED))
    assert (approval.decided_by, approval.excluded_entries, approval.sample[0].check) == (None, (), None)


@pytest.mark.parametrize(
    ("extra", "check", "values", "message"),
    [
        ("decided_by: rules\n", "", DECIDED, "link check of every entry"),
        ("decided_by: Otto Muster\n", "", DECIDED, "decided_by is rules or otto"),
        ("decided_by: otto\n", "", {}, "a pending file has none"),
        ("", "{outcome: passed, reason: no_title}", DECIDED, "passed with reason ok"),
        ("", "{outcome: maybe, reason: ok}", DECIDED, "passed with reason ok"),
        ("", "{outcome: failed, reason: 'Seite <b>weg</b>'}", DECIDED, "reason code"),
        ("excluded_entries: [govdata.y, govdata.y]\n", "", DECIDED, "each once"),
        ("excluded_entries: ['../etc/passwd']\n", "", DECIDED, "dataset ids"),
    ],
)
def test_wrong_fields_of_m5_67(
    tmp_path: Path, extra: str, check: str, values: dict[str, str], message: str
) -> None:
    with pytest.raises(EntryFileError, match=message):
        load_approvals(_with(tmp_path, extra, check=check, **values))

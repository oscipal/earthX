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

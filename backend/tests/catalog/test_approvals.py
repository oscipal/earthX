"""The approval files of the runs (adr/0033 §8.3; M5-20 plan §12): read strictly, checked before anything is published."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from earthx.catalog.approvals import APPROVALS_DIR, file_number, file_stem, load_approvals, next_file_stem
from earthx.catalog.entry_files import EntryFileError
from earthx.catalog.sources import read_sources
from tests.approval_checks import assert_approvals_are_consistent

FILE = """\
source_id: {source_id}
batch_id: {batch_id}
fingerprint: {fingerprint}
created_on: {created_on}
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
    fields = {
        "source_id": "govdata",
        "created_on": "2026-11-19",
        "batch_id": "3",
        "fingerprint": "a" * 64,
        "decision": "pending",
        "decided_on": "null",
        "revoked_on": "null",
        "ok": "null",
    }
    fields.update(values)
    (tmp_path / name).write_text(FILE.format(**fields), encoding="utf-8")
    return tmp_path


def test_every_shipped_approval_loads_and_is_consistent() -> None:
    assert_approvals_are_consistent(APPROVALS_DIR, read_sources())


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
    with pytest.raises(EntryFileError, match=r"only <day>-<source_id>\[-<n>\].yaml"):
        load_approvals(_write(tmp_path, name="freigabe.yaml"))


def test_an_unknown_field(tmp_path: Path) -> None:
    _write(tmp_path)
    path = tmp_path / "2026-11-19-govdata.yaml"
    path.write_text(path.read_text(encoding="utf-8") + "note: x\n", encoding="utf-8")
    with pytest.raises(EntryFileError):
        load_approvals(tmp_path)


DAY = date(2026, 11, 19)


def test_the_name_of_a_file_is_made_and_read_by_one_rule() -> None:
    assert file_stem(DAY, "govdata") == "2026-11-19-govdata"
    assert file_stem(DAY, "govdata", 2) == "2026-11-19-govdata-2"
    assert file_stem(DAY, "govdata", 12) == "2026-11-19-govdata-12"
    with pytest.raises(ValueError, match="from 1"):
        file_stem(DAY, "govdata", 0)
    assert file_number("2026-11-19-govdata", DAY, "govdata") == 1
    assert file_number("2026-11-19-govdata-2", DAY, "govdata") == 2
    assert file_number("2026-11-19-govdata-12", DAY, "govdata") == 12
    # Not the name of a file of this source on this day, or not a number the rule makes (the first has none).
    for stem, source in (
        ("2026-11-19-govdata-1", "govdata"),
        ("2026-11-19-govdata-02", "govdata"),
        ("2026-11-19-govdata-0", "govdata"),
        ("2026-11-19-govdata-x", "govdata"),
        ("2026-11-19-govdata-2-2", "govdata"),
        ("2026-11-20-govdata", "govdata"),
        ("2026-11-19-fsdi-stac", "govdata"),
        ("2026-11-19-govdata", "fsdi-stac"),
    ):
        assert file_number(stem, DAY, source) is None, stem
    # A source whose id ends in a number: its first file is no second file of the source before it.
    assert file_number("2026-11-19-feed-2", DAY, "feed-2") == 1


def test_the_next_name_is_one_above_the_highest_of_that_source_and_day(tmp_path: Path) -> None:
    assert next_file_stem(tmp_path / "missing", DAY, "govdata") == "2026-11-19-govdata"
    assert next_file_stem(tmp_path, DAY, "govdata") == "2026-11-19-govdata"
    for name, expected in (
        ("2026-11-19-govdata.yaml", "2026-11-19-govdata-2"),
        ("2026-11-19-govdata-2.yaml", "2026-11-19-govdata-3"),
        # A file deleted from the middle: the next one still goes after the last, never into the gap.
        ("2026-11-19-govdata-5.yaml", "2026-11-19-govdata-6"),
    ):
        (tmp_path / name).write_text("", encoding="utf-8")
        assert next_file_stem(tmp_path, DAY, "govdata") == expected
    # Other days, other sources and the reports beside the files do not count.
    (tmp_path / "2026-11-18-govdata-9.yaml").write_text("", encoding="utf-8")
    (tmp_path / "2026-11-19-fsdi-stac-8.yaml").write_text("", encoding="utf-8")
    (tmp_path / "2026-11-19-govdata-7.md").write_text("", encoding="utf-8")
    assert next_file_stem(tmp_path, DAY, "govdata") == "2026-11-19-govdata-6"
    assert next_file_stem(tmp_path, DAY, "opendata-swiss") == "2026-11-19-opendata-swiss"


def test_several_files_of_one_source_on_one_day_load_in_the_order_they_were_written(tmp_path: Path) -> None:
    # The directory lists `-2` before the file without a number ("-" sorts before "."); the loader does not.
    _write(tmp_path, name="2026-11-19-govdata-3.yaml", batch_id="9", fingerprint="c" * 64)
    _write(tmp_path, name="2026-11-19-govdata-2.yaml", batch_id="7", fingerprint="b" * 64)
    _write(tmp_path, name="2026-11-19-govdata.yaml", batch_id="3")
    loaded = load_approvals(tmp_path)
    assert [name for _, name, _ in loaded] == [
        "approvals/2026-11-19-govdata.yaml",
        "approvals/2026-11-19-govdata-2.yaml",
        "approvals/2026-11-19-govdata-3.yaml",
    ]
    assert [approval.batch_id for approval, _, _ in loaded] == [3, 7, 9]


@pytest.mark.parametrize(
    "name",
    [
        "2026-11-19-govdata-1.yaml",  # the first file has no number
        "2026-11-19-govdata-02.yaml",
        "2026-11-19-govdata-x.yaml",
        "2026-11-19-govdata-2-2.yaml",
        "2026-11-20-govdata.yaml",  # another day than created_on
        "2026-11-19-fsdi-stac.yaml",  # another source than source_id
    ],
)
def test_a_name_that_is_not_the_one_of_the_content(tmp_path: Path, name: str) -> None:
    with pytest.raises(EntryFileError, match=r"the name is 2026-11-19-govdata\.yaml .* 2026-11-19-govdata-2\.yaml"):
        load_approvals(_write(tmp_path, name=name))


@pytest.mark.parametrize(("first", "second"), [("7", "3"), ("5", "5")])
def test_a_later_file_of_the_day_holds_a_newer_stack(tmp_path: Path, first: str, second: str) -> None:
    _write(tmp_path, name="2026-11-19-govdata.yaml", batch_id=first)
    _write(tmp_path, name="2026-11-19-govdata-2.yaml", batch_id=second, fingerprint="b" * 64)
    with pytest.raises(EntryFileError, match=r"2026-11-19-govdata-2\.yaml: its stack .* not newer"):
        load_approvals(tmp_path)


def test_files_of_other_days_and_sources_do_not_order_each_other(tmp_path: Path) -> None:
    _write(tmp_path, name="2026-11-18-govdata.yaml", batch_id="9", created_on="2026-11-18")
    _write(tmp_path, name="2026-11-19-govdata.yaml", batch_id="3")
    _write(tmp_path, name="2026-11-19-fsdi-stac.yaml", batch_id="1", source_id="fsdi-stac")
    assert len(load_approvals(tmp_path)) == 3


def test_a_source_id_of_the_longest_length_still_has_later_files(tmp_path: Path) -> None:
    # sources.py allows ids of 63 characters; the number of a later file must not push its name out of the shape.
    long_id = "a" + "b" * 62
    for number, batch in ((1, "3"), (2, "4"), (12, "5")):
        name = f"{file_stem(DAY, long_id, number)}.yaml"
        _write(tmp_path, name=name, source_id=long_id, batch_id=batch, fingerprint="abcdef"[number % 6] * 64)
    assert [name for _, name, _ in load_approvals(tmp_path)] == [
        f"approvals/{file_stem(DAY, long_id, n)}.yaml" for n in (1, 2, 12)
    ]


def test_a_source_that_ends_in_a_number_beside_the_source_without_it(tmp_path: Path) -> None:
    # `feed` has a second file and `feed-2` its first on one day: the names meet, the files stay apart.
    _write(tmp_path, name="2026-11-19-feed.yaml", source_id="feed", batch_id="3")
    _write(tmp_path, name="2026-11-19-feed-2.yaml", source_id="feed", batch_id="5", fingerprint="b" * 64)
    _write(tmp_path, name="2026-11-19-feed-2-2.yaml", source_id="feed-2", batch_id="6", fingerprint="c" * 64)
    found = [(approval.source_id, name) for approval, name, _ in load_approvals(tmp_path)]
    assert found == [
        ("feed", "approvals/2026-11-19-feed.yaml"),
        ("feed", "approvals/2026-11-19-feed-2.yaml"),
        ("feed-2", "approvals/2026-11-19-feed-2-2.yaml"),
    ]
    # The writer reads names only: for `feed` the file of `feed-2` counts as a second one, which leaves a gap and no clash.
    assert next_file_stem(tmp_path, DAY, "feed") == "2026-11-19-feed-3"


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

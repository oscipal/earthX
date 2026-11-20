"""The grants built from the publishers of the harvested finds (M5-20 plan §13f; Otto 20.11.2026: K1-K5 for all)."""

from __future__ import annotations

import shutil
from datetime import date, timedelta
from pathlib import Path

import pytest

from earthx.catalog.entry_files import EntryFileError
from earthx.catalog.licences import LICENSES_DIR, Grant, load_licences
from earthx.catalog.sources import read_sources
from earthx.discovery import grants as grants_module
from earthx.discovery.grants import GrantToAll, build_grants, dump_grants, read_grant_to_all, read_grants

SOURCES = read_sources()
CATALOGUE = load_licences(SOURCES)
TO_ALL = GrantToAll(("cc-by-4.0", "dl-de-by-2.0"), date(2026, 11, 20))
DAY = date(2026, 11, 20)


class TestTheShippedFile:
    def test_it_grants_k1_to_k5_but_not_official_works_or_k6(self) -> None:
        refs = set(read_grant_to_all(CATALOGUE.terms).licenses)
        open_ones = {ref for ref, term in CATALOGUE.terms.items() if term.license.distribution}
        assert refs == open_ones - {"de-official-work"}
        assert {"nb-gdikom-b", "admin-ch-disclaimer", "dcat-de-other-closed"}.isdisjoint(refs)

    def test_nothing_is_granted_before_otto_runs_the_command(self) -> None:
        assert dict(CATALOGUE.grants) == {}


class TestReadGrantToAll:
    def _read(self, tmp_path: Path, text: str) -> GrantToAll:
        path = tmp_path / "grant-to-all.yaml"
        path.write_text(text, encoding="utf-8")
        return read_grant_to_all(CATALOGUE.terms, path)

    def test_a_licence_outside_terms_yaml_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(EntryFileError, match="not in terms.yaml: cc-by-9.0"):
            self._read(tmp_path, "licenses: [cc-by-4.0, cc-by-9.0]\napproved_on: 2026-11-20\n")

    @pytest.mark.parametrize("licenses", ["[]", "[cc-by-4.0, cc-by-4.0]"])
    def test_no_licence_or_one_twice_is_refused(self, tmp_path: Path, licenses: str) -> None:
        with pytest.raises(EntryFileError, match="each once"):
            self._read(tmp_path, f"licenses: {licenses}\napproved_on: 2026-11-20\n")

    def test_a_day_in_the_future_is_refused(self, tmp_path: Path) -> None:
        later = (date.today() + timedelta(days=1)).isoformat()
        with pytest.raises(EntryFileError, match="future"):
            self._read(tmp_path, f"licenses: [cc-by-4.0]\napproved_on: {later}\n")

    @pytest.mark.parametrize("text", ["- cc-by-4.0\n", "licenses: [cc-by-4.0]\n", "licenses: [cc-by-4.0]\napproved_on: x\n"])
    def test_a_file_of_another_shape_is_refused(self, tmp_path: Path, text: str) -> None:
        with pytest.raises(EntryFileError):
            self._read(tmp_path, text)


class TestBuildGrants:
    def test_every_publisher_gets_every_licence_sorted_by_name(self) -> None:
        lines = build_grants(["Stadt B", "Amt A"], TO_ALL, (), DAY)
        assert [(g.publisher, g.licenses, g.approved_on) for g in lines] == [
            ("Amt A", TO_ALL.licenses, DAY),
            ("Stadt B", TO_ALL.licenses, DAY),
        ]

    def test_a_second_run_keeps_unchanged_lines_and_their_day(self) -> None:
        before = (Grant("Amt A", ("dl-de-by-2.0", "cc-by-4.0"), date(2026, 11, 19)),)
        lines = build_grants(["Amt A", "Amt C"], TO_ALL, before, DAY)
        assert lines[0] is before[0] and lines[1].approved_on == DAY

    def test_a_changed_licence_list_gives_the_line_the_new_day(self) -> None:
        before = (Grant("Amt A", ("cc-by-4.0",), date(2026, 11, 19)),)
        (line,) = build_grants(["Amt A"], TO_ALL, before, DAY)
        assert (line.licenses, line.approved_on) == (TO_ALL.licenses, DAY)

    def test_a_publisher_gone_from_the_database_keeps_its_line(self) -> None:
        # A line written by hand, or for a publisher whose finds are gone, is not dropped by a run.
        before = (Grant("Altes Amt", ("cc-by-4.0",), date(2026, 11, 19)),)
        assert build_grants([], TO_ALL, before, DAY) == before


class TestDumpGrants:
    def test_the_written_file_loads_as_grants_of_the_source(self, tmp_path: Path) -> None:
        # Quotes, a colon, a hash and umlauts in a name must come back exactly: the grant compares it verbatim.
        names = ['Amt "Nord": Daten # 1', "Bundesanstalt für Wasserbau", "- Liste", "null"]
        lines = build_grants(names, TO_ALL, (), DAY)
        directory = tmp_path / "licenses"
        shutil.copytree(LICENSES_DIR, directory)
        path = directory / "grants" / "govdata.yaml"
        path.write_text(dump_grants(lines), encoding="utf-8")
        catalogue = load_licences(SOURCES, directory)
        assert set(catalogue.grants["govdata"]) == set(names)
        assert read_grants(path) == lines

    def test_no_publisher_gives_an_empty_list(self, tmp_path: Path) -> None:
        path = tmp_path / "govdata.yaml"
        path.write_text(dump_grants(()), encoding="utf-8")
        assert read_grants(path) == ()

    def test_a_missing_file_has_no_lines_and_a_foreign_one_is_refused(self, tmp_path: Path) -> None:
        assert read_grants(tmp_path / "none.yaml") == ()
        path = tmp_path / "govdata.yaml"
        path.write_text("publisher: Amt\n", encoding="utf-8")
        with pytest.raises(EntryFileError, match="are a list"):
            read_grants(path)


class TestMain:
    def test_an_unknown_source_stops_before_the_database(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert grants_module.main(["no-such-source"]) == 1
        assert "no source no-such-source" in capsys.readouterr().err

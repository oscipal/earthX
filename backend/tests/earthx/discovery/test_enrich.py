"""Enrich: spatial extent in steps and the period (M5-20 plan §6, §13b; F1 = 1, F2 = 1)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from earthx.catalog.entry_files import EntryFileError
from earthx.discovery.enrich import (
    PLACE_NAMES_FILE,
    load_place_directory,
    place_codes,
    publisher_code,
    read_place_directory,
    spatial_extent,
    time_span,
)

DIRECTORY = load_place_directory()


@pytest.mark.parametrize(
    ("text", "codes"),
    [
        # Otto's examples of 19.11.2026 (M2).
        ("Canton de Fribourg (FR)", ("CH-FR",)),
        ("Kanton Schwyz (SZ)", ("CH-SZ",)),
        ("GE", ("CH-GE",)),
        ("CH", ("CH",)),
        ("Switzerland", ("CH",)),
        ("Kanton Bern / Canton de Berne", ("CH-BE",)),
        ("Schweiz (mit grenznahem Ausland)", ("CH",)),
        ("Aargau und angrenzende Gebiete", ("CH-AG",)),
        ("République et canton de Genève", ("CH-GE",)),
        ("Basel-Stadt, Basel-Landschaft", ("CH-BL", "CH-BS")),
        ("Vaduz", ("LI-11",)),
        ("Zuerich", None),
        # A name that is also a municipality's needs its designation; municipalities are not in the directory yet.
        ("Bern", None),
        ("Zürich", None),
        ("Stadt Bern", None),
        ("Winterthur", None),
        ("Biel/Bienne", None),
        ("Grossraum Basel", None),
        # One part that is no place spoils the whole text.
        ("Aargau, Nirgendwo", None),
        ("Kantone", "*"),
        ("Politische Gemeinden", "*"),
        ("Sonstige Raumgliederungen", "*"),
        ("Spatial", ""),
        ("Landeskarte 1:500'000", ""),
        # GeoNames: matched by the table only, which is empty until the ids are shown (F10).
        ("https://sws.geonames.org/2658434/", None),
    ],
)
def test_place_texts(text: str, codes: object) -> None:
    assert place_codes(text, DIRECTORY, "CH") == codes


def test_an_abbreviation_in_a_list_is_no_place() -> None:
    # Plan A15: only as the whole text or in parentheses; in "DE, FR, IT" FR is France as often as Fribourg.
    assert place_codes("DE, FR, IT", DIRECTORY, "CH") is None
    assert place_codes("Kanton Freiburg (FR)", DIRECTORY, "CH") == ("CH-FR",)


def test_an_abbreviation_is_a_subdivision_of_the_catalogue_first() -> None:
    # Plan A15: FR at opendata.swiss is Fribourg; without a state of the catalogue it is France.
    assert place_codes("FR", DIRECTORY, "CH") == ("CH-FR",)
    assert place_codes("FR", DIRECTORY, None) == ("FR",)
    assert place_codes("BY", DIRECTORY, "DE") == ("DE-BY",)
    assert place_codes("ZZ", DIRECTORY, "CH") is None


@pytest.mark.parametrize(
    ("publisher", "code"),
    [
        ("Landesamt für Vermessung und Geobasisinformation Sachsen-Anhalt", "DE-ST"),
        ("Statistisches Amt des Kantons Zürich", "CH-ZH"),
        ("Kanton Basel-Stadt", "CH-BS"),
        ("Stadt Zürich", None),
        # Two places: none.
        ("Statistisches Amt für Hamburg und Schleswig-Holstein", None),
        ("Bundesamt für Statistik", None),
        ("", None),
    ],
)
def test_publishers(publisher: str, code: str | None) -> None:
    assert publisher_code(publisher, DIRECTORY) == code


@pytest.mark.parametrize(
    ("found", "country", "basis", "codes"),
    [
        # Review M5-20 PR 1: a place counts only in the state of the catalogue.
        ({"publisher": "Landratsamt Sächsische Schweiz-Osterzgebirge"}, "DE", "catalog", ("DE",)),
        ({"publisher": "Gemeinde Schellenberg"}, "DE", "catalog", ("DE",)),
        ({"spatial_text": "Vienne"}, "CH", "catalog", ("CH",)),
        ({"spatial_text": "Vaduz"}, "LI", "place", ("LI", "LI-11")),
        # Only whole states: regions without a footprint (plan A19).
        ({"spatial_text": "Schweiz"}, "CH", "catalog", ("CH",)),
        ({"spatial_text": "Schweiz, Liechtenstein"}, "CH", "catalog", ("CH", "LI")),
    ],
)
def test_places_outside_the_catalogue_and_whole_states(
    found: dict[str, str], country: str, basis: str, codes: tuple[str, ...]
) -> None:
    extent = spatial_extent(found, country=country)
    assert (extent.basis, extent.codes, extent.has_footprint) == (basis, codes, False if basis == "catalog" else True)


class TestSteps:
    def test_the_geometry_of_the_source_comes_first(self) -> None:
        extent = spatial_extent({"bbox": [8, 47, 9, 48], "spatial_text": "Aargau"}, country="CH")
        assert (extent.basis, extent.bbox, extent.has_footprint) == ("source", (8.0, 47.0, 9.0, 48.0), True)

    def test_a_place_text_gives_the_place_and_its_state(self) -> None:
        extent = spatial_extent({"spatial_text": "Kanton Bern", "publisher": "Kanton Zug"}, country="CH")
        assert (extent.basis, extent.codes, extent.has_footprint) == ("place", ("CH", "CH-BE"), True)

    def test_a_text_without_a_place_falls_to_the_publisher(self) -> None:
        extent = spatial_extent({"spatial_text": "Winterthur", "publisher": "Kanton Zug"}, country="CH")
        assert (extent.basis, extent.codes, extent.has_footprint) == ("publisher", ("CH", "CH-ZG"), False)
        assert extent.unresolved == "Winterthur"

    def test_then_the_state_of_the_catalogue(self) -> None:
        extent = spatial_extent({"publisher": "Bundesamt für Statistik"}, country="CH")
        assert (extent.basis, extent.codes, extent.has_footprint) == ("catalog", ("CH",), False)

    def test_a_whole_country_text_is_the_state_of_the_catalogue(self) -> None:
        assert spatial_extent({"spatial_text": "Gemeinden"}, country="CH").basis == "catalog"

    def test_nothing_in_a_catalogue_of_the_world(self) -> None:
        assert spatial_extent({"title": "Kanton Bern"}, country=None).basis == "none"

    def test_a_place_in_the_title_is_never_read(self) -> None:
        # Otto, 19.11.2026: "Ort: Merkmal" is no extent.
        assert spatial_extent({"title": "Kanton Bern: Bevölkerung"}, country="CH").basis == "catalog"


@pytest.mark.parametrize(
    ("temporal", "span"),
    [
        (("2019", "2023-12"), (datetime(2019, 1, 1, tzinfo=UTC), datetime(2023, 12, 31, 23, 59, 59, tzinfo=UTC))),
        (("2020-02-29", None), (datetime(2020, 2, 29, tzinfo=UTC), None)),
        ((None, "2020-02-29"), (None, datetime(2020, 2, 29, 23, 59, 59, tzinfo=UTC))),
        (("2020-05-01T10:00:00Z", "2020-05-01T12:00:00+02:00"), (datetime(2020, 5, 1, 10, tzinfo=UTC),) * 2),
        (("2020-05-01T10:00:00", None), (datetime(2020, 5, 1, 10, tzinfo=UTC), None)),
        (("2021", "2019"), None),
        # "9999-12-31" is an open end in DCAT and INSPIRE (review M5-20 PR 1).
        (("2019", "9999-12-31"), (datetime(2019, 1, 1, tzinfo=UTC), None)),
        (("2019", "9999"), (datetime(2019, 1, 1, tzinfo=UTC), None)),
        (("2019", "9999-12"), (datetime(2019, 1, 1, tzinfo=UTC), None)),
        (("2019", "9999-12-31T23:59:59Z"), (datetime(2019, 1, 1, tzinfo=UTC), None)),
        (("0000", None), None),
        (("2021-02-30", None), None),
        (("seit 2010", "heute"), None),
        (None, None),
        (("2019",), None),
    ],
)
def test_time_span(temporal: object, span: object) -> None:
    assert time_span(temporal) == span


class TestTheDirectoryFile:
    def _regions(self) -> dict[str, str]:
        return {"CH": "state", "CH-BE": "subdivision"}

    def _write(self, tmp_path: Path, text: str) -> Path:
        path = tmp_path / "place_names.yaml"
        path.write_text(text, encoding="utf-8")
        return path

    BASE = (
        "places: {CH: [Schweiz], CH-BE: [Bern]}\nambiguous: [Bern]\ndesignations: [Kanton]\nwhole_country: [Kantone]\n"
        "approximate: {before: [Raum], after: [und Umgebung]}\nnot_places: [Spatial]\ngeonames: {}\n"
    )

    def test_the_shipped_file_loads(self) -> None:
        assert read_place_directory(PLACE_NAMES_FILE, DIRECTORY.levels).plain

    def test_a_code_that_regions_json_lacks(self, tmp_path: Path) -> None:
        with pytest.raises(EntryFileError, match="regions.json lacks"):
            read_place_directory(self._write(tmp_path, self.BASE.replace("CH-BE:", "CH-XX:")), self._regions())

    def test_a_name_under_two_codes(self, tmp_path: Path) -> None:
        with pytest.raises(EntryFileError, match="two codes"):
            read_place_directory(self._write(tmp_path, self.BASE.replace("[Schweiz]", "[Bern]")), self._regions())

    def test_an_ambiguous_name_that_names_no_place(self, tmp_path: Path) -> None:
        with pytest.raises(EntryFileError, match="ambiguous names no place"):
            path = self._write(tmp_path, self.BASE.replace("ambiguous: [Bern]", "ambiguous: [X]"))
            read_place_directory(path, self._regions())

    def test_a_geonames_id_that_is_no_number(self, tmp_path: Path) -> None:
        with pytest.raises(EntryFileError, match="geonames"):
            path = self._write(tmp_path, self.BASE.replace("geonames: {}", "geonames: {x: CH}"))
            read_place_directory(path, self._regions())

    def test_a_geonames_id_matches_through_the_table(self, tmp_path: Path) -> None:
        directory = read_place_directory(
            self._write(tmp_path, self.BASE.replace("geonames: {}", "geonames: {'2658434': CH}")), self._regions()
        )
        assert place_codes("http://sws.geonames.org/2658434/", directory, "CH") == ("CH",)

    def test_a_missing_key(self, tmp_path: Path) -> None:
        with pytest.raises(EntryFileError, match="holds exactly"):
            read_place_directory(self._write(tmp_path, self.BASE.replace("geonames: {}\n", "")), self._regions())

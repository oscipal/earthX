"""Enrich: spatial extent in steps and the period (M5-20 plan §6, §13b; F1 = 1, F2 = 1)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from earthx.catalog.entry_files import EntryFileError
from earthx.catalog.listed import load_regions
from earthx.catalog.municipalities import Municipality
from earthx.discovery.enrich import (
    PLACE_NAMES_FILE,
    geonames_ids,
    load_place_directory,
    place_codes,
    publisher_code,
    read_place_directory,
    spatial_extent,
    time_span,
)

# The directory of regions alone; the municipalities of the image are tested apart (TestTheShippedMunicipalities).
DIRECTORY = read_place_directory(PLACE_NAMES_FILE, {region.code: region.level for region in load_regions()})


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
    extent = spatial_extent(found, country=country, directory=DIRECTORY)
    assert (extent.basis, extent.codes, extent.has_footprint) == (basis, codes, False if basis == "catalog" else True)


class TestSteps:
    def test_the_geometry_of_the_source_comes_first(self) -> None:
        extent = spatial_extent({"bbox": [8, 47, 9, 48], "spatial_text": "Aargau"}, country="CH", directory=DIRECTORY)
        assert (extent.basis, extent.bbox, extent.has_footprint) == ("source", (8.0, 47.0, 9.0, 48.0), True)

    def test_a_place_text_gives_the_place_and_its_state(self) -> None:
        extent = spatial_extent({"spatial_text": "Kanton Bern", "publisher": "Kanton Zug"}, country="CH", directory=DIRECTORY)
        assert (extent.basis, extent.codes, extent.has_footprint) == ("place", ("CH", "CH-BE"), True)

    def test_a_text_without_a_place_falls_to_the_publisher(self) -> None:
        extent = spatial_extent({"spatial_text": "Winterthur", "publisher": "Kanton Zug"}, country="CH", directory=DIRECTORY)
        assert (extent.basis, extent.codes, extent.has_footprint) == ("publisher", ("CH", "CH-ZG"), False)
        assert extent.unresolved == "Winterthur"

    def test_then_the_state_of_the_catalogue(self) -> None:
        extent = spatial_extent({"publisher": "Bundesamt für Statistik"}, country="CH", directory=DIRECTORY)
        assert (extent.basis, extent.codes, extent.has_footprint) == ("catalog", ("CH",), False)

    def test_a_whole_country_text_is_the_state_of_the_catalogue(self) -> None:
        assert spatial_extent({"spatial_text": "Gemeinden"}, country="CH", directory=DIRECTORY).basis == "catalog"

    def test_nothing_in_a_catalogue_of_the_world(self) -> None:
        assert spatial_extent({"title": "Kanton Bern"}, country=None, directory=DIRECTORY).basis == "none"

    def test_a_place_in_the_title_is_never_read(self) -> None:
        # Otto, 19.11.2026: "Ort: Merkmal" is no extent.
        assert spatial_extent({"title": "Kanton Bern: Bevölkerung"}, country="CH", directory=DIRECTORY).basis == "catalog"


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
        "places: {CH: [Schweiz], CH-BE: [Bern]}\nambiguous: [Bern]\ndesignations: [Kanton]\n"
        "municipal_designations: [Stadt]\nwhole_country: [Kantone]\nwhole_country_prefixes: []\nbeyond: [Welt]\n"
        "beyond_prefixes: []\napproximate: {before: [Raum], after: [und Umgebung]}\nnot_places: [Spatial]\n"
        "not_place_prefixes: []\nnot_place_patterns: []\nalpha3: {CHE: CH}\ngeonames: {}\n"
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


def _square(lon: float, lat: float) -> dict[str, object]:
    return {"type": "Polygon", "coordinates": [[[lon, lat], [lon + 0.05, lat], [lon + 0.05, lat + 0.05], [lon, lat + 0.05], [lon, lat]]]}


MUNICIPALITIES = (
    Municipality("CH-BE-0351", "Bern", "CH-BE", _square(7.4, 46.9)),
    Municipality("CH-BE-0371", "Biel/Bienne", "CH-BE", _square(7.2, 47.1)),
    Municipality("CH-AG-4021", "Buchs (AG)", "CH-AG", _square(8.0, 47.4)),
    Municipality("CH-SG-3271", "Buchs (SG)", "CH-SG", _square(9.4, 47.1)),
    Municipality("CH-ZH-0261", "Zürich", "CH-ZH", _square(8.5, 47.3)),
    Municipality("CH-ZH-0120", "Wald (ZH)", "CH-ZH", _square(8.9, 47.2)),
    Municipality("CH-AR-3001", "Wald", "CH-AR", _square(9.5, 47.4)),
    Municipality("CH-AG-4001", "Aargau", "CH-AG", _square(8.0, 47.3)),
    Municipality("CH-ZG-1711", "Zug", "CH-ZG", _square(8.5, 47.15)),
    Municipality("CH-SZ-1372", "Schwyz", "CH-SZ", _square(8.65, 47.0)),
    Municipality("CH-LU-1061", "Luzern", "CH-LU", _square(8.3, 47.05)),
    Municipality("CH-BS-2701", "Basel", "CH-BS", _square(7.58, 47.55)),
)


class TestMunicipalities:
    """F9 = 1 (Otto, 19.11.2026): municipalities of swissBOUNDARIES3D for place texts; never a region of their own."""

    directory = read_place_directory(PLACE_NAMES_FILE, DIRECTORY.levels, MUNICIPALITIES)

    @pytest.mark.parametrize(
        ("text", "codes"),
        [
            # Otto's examples (M2): towns and cities; a bare name that is also a canton's is the municipality now.
            ("Stadt Bern", ("CH-BE-0351",)),
            ("Bern", ("CH-BE-0351",)),
            ("Kanton Bern", ("CH-BE",)),
            ("Biel/Bienne", ("CH-BE-0371",)),
            ("Bienne", ("CH-BE-0371",)),
            ("Buchs (AG)", ("CH-AG-4021",)),
            # Two municipalities of one name without their canton: none.
            ("Buchs", None),
            ("Zürich", ("CH-ZH-0261",)),
            ("Grossraum Zürich", ("CH-ZH-0261",)),
            ("Wald", ("CH-AR-3001",)),
            # A region's name stays the region's; the municipality only after its designation.
            ("Aargau", ("CH-AG",)),
            ("Gemeinde Aargau", ("CH-AG-4001",)),
        ],
    )
    def test_place_texts(self, text: str, codes: object) -> None:
        assert place_codes(text, self.directory, "CH") == codes

    def test_a_municipality_gives_its_outline_and_the_regions_of_its_canton(self) -> None:
        extent = spatial_extent({"spatial_text": "Stadt Bern"}, country="CH", directory=self.directory)
        assert (extent.basis, extent.codes, extent.places) == ("place", ("CH", "CH-BE"), ("CH-BE-0351",))

    @pytest.mark.parametrize(
        ("publisher", "codes"),
        [
            ("Stadt Zürich", ("CH", "CH-ZH")),
            # A municipality in a publisher's name only after its designation: "Wald" here is a forest.
            ("Amt für Wald und Wild", ("CH",)),
            ("Bern", ("CH",)),
        ],
    )
    def test_publishers(self, publisher: str, codes: tuple[str, ...]) -> None:
        extent = spatial_extent({"publisher": publisher}, country="CH", directory=self.directory)
        assert extent.codes == codes


def test_geonames_ids() -> None:
    assert geonames_ids("https://sws.geonames.org/2658434/ und http://sws.geonames.org/7285161") == ["2658434", "7285161"]



@pytest.mark.parametrize(
    ("text", "codes"),
    [
        # Otto's findings of 20.11.2026 from -Classify.
        ("Jura (JU)", ("CH-JU",)),
        ("Bern (Kanton)", ("CH-BE",)),
        ("http://publications.europa.eu/resource/authority/country/CH", ("CH",)),
        ("http://publications.europa.eu/resource/authority/country/CHE", ("CH",)),
        ("http://publications.europa.eu/resource/authority/country/DEU", ("DE",)),
        ("http://publications.europa.eu/resource/authority/country/XYZ", None),
        ("Sprachgebiete", "*"),
        ("Statistische Städte", "*"),
        ("Gemeinden (Politik)", "*"),
        ("Städtische/Ländliche Gebiete", "*"),
        ("NUTS 0 Staaten", "*"),
        ("Urban Audit Kernstädte (Schweiz-Perimeter)", "*"),
        ("Fachhochschulen", "*"),
        ("Landeskarte 1:25 000", ""),
        ("swissTLMRegio", ""),
        ("swissALTIRegio", ""),
        ("SWISSIMAGE 10 cm", ""),
        ("Orthofoto 2019", ""),
        ("Topografisches Landschaftsmodell TLM", ""),
        ("GeoMol15-Basismodell", ""),
        ("Seen im Kanton Luzern", ("CH-LU",)),
        ("Europa", "!"),
        ("Welt", "!"),
        ("International", "!"),
        ("Grenzüberschreitender Urban Audit Perimeter", "!"),
    ],
)
def test_place_texts_of_the_classification(text: str, codes: object) -> None:
    assert place_codes(text, DIRECTORY, "CH") == codes


def test_a_text_beyond_any_state_has_no_region_and_no_fallback() -> None:
    # Plan A25: "Europa" does not fall to the state of the catalogue.
    extent = spatial_extent({"spatial_text": "Europa", "publisher": "Kanton Zug"}, country="CH", directory=DIRECTORY)
    assert (extent.basis, extent.codes, extent.has_footprint) == ("none", (), False)


class TestCoresAndCities:
    directory = read_place_directory(PLACE_NAMES_FILE, DIRECTORY.levels, MUNICIPALITIES)

    @pytest.mark.parametrize(
        ("text", "codes"),
        [
            ("Agglomeration Bern", ("CH-BE-0351",)),
            ("Basel (Stadtplan 1987 - 1992)", ("CH-BS-2701",)),
            ("Luzern (LU)", ("CH-LU",)),
            ("Luzern", ("CH-LU-1061",)),
        ],
    )
    def test_cores(self, text: str, codes: tuple[str, ...]) -> None:
        assert place_codes(text, self.directory, "CH") == codes

    @pytest.mark.parametrize(
        ("text", "publisher", "places", "choice"),
        [
            ("Zug", "Kanton Zug", ("CH-ZG",), "zug: Kanton"),
            ("Schwyz", "Amt für Geoinformation Kanton Schwyz", ("CH-SZ",), "schwyz: Kanton"),
            ("Zug", "Stadt Zug", ("CH-ZG-1711",), "zug: Stadt"),
            ("Zug", "Bundesamt für Statistik", ("CH-ZG-1711",), "zug: Stadt"),
            # Not a bare name: the city as named, no choice.
            ("Stadt Zug", "Kanton Zug", ("CH-ZG-1711",), None),
        ],
    )
    def test_a_bare_name_of_city_and_canton_follows_the_publisher(
        self, text: str, publisher: str, places: tuple[str, ...], choice: str | None
    ) -> None:
        # Otto, 20.11.2026: an office of the canton means the canton, else the city.
        extent = spatial_extent({"spatial_text": text, "publisher": publisher}, country="CH", directory=self.directory)
        assert (extent.places, extent.choice) == (places, choice)
        assert extent.codes == ("CH", places[0][:5])



class TestTheShippedMunicipalities:
    """Otto's municipalities.json (swissBOUNDARIES3D 2026-01, pushed 20.11.2026): Otto's examples of M2."""

    directory = load_place_directory()

    @pytest.mark.parametrize("text", ["Stadt Bern", "Winterthur", "Emmen", "Biel/Bienne", "Riehen"])
    def test_towns_of_the_classification(self, text: str) -> None:
        codes = place_codes(text, self.directory, "CH")
        assert isinstance(codes, tuple) and len(codes) == 1 and codes[0].count("-") == 2



@pytest.mark.parametrize(
    ("text", "codes"),
    [
        # Otto's second -Classify run (20.11.2026).
        ("DHM25", ""),
        ("swissBATHY3D", ""),
        ("Siegfriedkarte", ""),
        ("Carte nationale 1:500'000", ""),
        ("Carte g\u00e9ologique g\u00e9n\u00e9rale 1:200@squot;000", ""),
        ("Luftfahrtkarte 1:350'000", ""),
        ("Strassenkarte 1:200'000", ""),
        ("Skitourenkarte 1:50'000", ""),
        ("Satellitenbilder (swisstopo)", ""),
        ("Hektaren", ""),
        ("Letzteiszeitliches Maximum", ""),
        ("N767fa14707fb4a3385294cd8110e494b", ""),
        ("Grand Genève", ("CH-GE",)),
        ("Raum mit städtischem Charakter", "*"),
        ("Stadt/Land-Typologie 2012", "*"),
        ("Arbeitsmarktregionen", "*"),
        ("Pädagogische Hochschulen", "*"),
        ("Welt: Regionen", "!"),
        ("Bern &amp; Jura", None),
        # GeoNames (F10 = 1, Otto 20.11.2026): Kanton Zug (ADM1 and ADM2).
        ("https://sws.geonames.org/2657907", ("CH-ZG",)),
        ("https://sws.geonames.org/6458807/", ("CH-ZG",)),
    ],
)
def test_place_texts_of_the_second_classification(text: str, codes: object) -> None:
    assert place_codes(text, DIRECTORY, "CH") == codes


def test_a_geonames_id_of_a_municipality() -> None:
    # 7287644 is the municipality of Zug (ADM3): its outline, the regions of its canton.
    extent = spatial_extent({"spatial_text": "https://sws.geonames.org/7287644/"}, country="CH")
    assert (extent.basis, extent.places, extent.codes) == ("place", ("CH-ZG-1711",), ("CH", "CH-ZG"))

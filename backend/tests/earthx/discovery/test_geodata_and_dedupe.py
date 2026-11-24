"""The rule R-G on finds that are no geodata, and dedupe (M5-20 plan §7, §8, §13b; F3 = 1, F4 = 1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from earthx.catalog.entry_files import EntryFileError
from earthx.discovery.dedupe import (
    MAX_SHARED,
    Member,
    collection_tokens,
    find_keys,
    linked_collections,
    main_entries,
    namespaced,
    shared_key,
)
from earthx.discovery.enrich import Extent
from earthx.discovery.geodata import GEODATA_FILE, classify, load_geodata_rule, read_geodata_rule

RULE = load_geodata_rule()
STATISTICS_OFFICE = "Statistisches Amt für Hamburg und Schleswig-Holstein"


def _find(title: str, **changes: Any) -> dict[str, Any]:
    found: dict[str, Any] = {
        "title": title,
        "data_kind": "table",
        "category": "population",
        "publisher": "Amt",
        "keywords": [],
        "themes": [],
        "distributions": [],
    }
    found.update(changes)
    return found


def _verdict(found: dict[str, Any], extent: Extent | None = None, country: str | None = "DE") -> str:
    return classify(found, extent or Extent("catalog", codes=("DE",)), country=country, rule=RULE).outcome


class TestGeodataRule:
    def test_a_statistics_table_of_a_statistics_office_is_hidden(self) -> None:
        # Otto's measurement M3-M5: the mass without an extent at GovData, "Ort: Merkmal".
        assert _verdict(_find("Hamburg-Altona: Bevölkerung", publisher=STATISTICS_OFFICE)) == "not_geodata"

    @pytest.mark.parametrize(
        "title", ["Grundwassermessstelle Musterdorf", "Raddauerzählstellen", "POI Wintersport", "Kita-Standorte"]
    )
    def test_geo_words_never_hide_a_find_also_inside_a_compound(self, title: str) -> None:
        assert _verdict(_find(title, publisher=STATISTICS_OFFICE)) == "geodata"

    @pytest.mark.parametrize(
        "changes",
        [
            {"data_kind": "vector"},
            {"distributions": [{"href": "https://x.example/a.shp", "format": "SHP", "media_type": None}]},
            {"themes": ["inspire:el"]},
            {"category": "elevation"},
        ],
    )
    def test_any_geo_signal_keeps_a_find(self, changes: dict[str, Any]) -> None:
        assert _verdict(_find("Statistik der Wahlen", **changes)) == "geodata"

    def test_the_statistics_office_of_nrw_stands_by_name(self) -> None:
        # Otto's measurement M4: IT.NRW (2 375 tables without an extent) has no "statisti*" in its name.
        assert _verdict(_find("Köln: Einwohner", publisher="IT.NRW")) == "not_geodata"
        assert _verdict(_find("Köln: Einwohner", publisher="Information und Technik Nordrhein-Westfalen")) == "not_geodata"

    def test_a_non_geo_eu_theme_hides_a_find_without_a_geo_signal(self) -> None:
        assert _verdict(_find("Liste", themes=["eu:GOVE"])) == "not_geodata"

    def test_without_any_signal_a_find_stays(self) -> None:
        assert _verdict(_find("Kindertagesstätten")) == "undecided"

    def test_a_term_is_a_whole_word(self) -> None:
        # "Wahl" as a word, not inside "Auswahl".
        assert _verdict(_find("Auswahl der Haltestellen")) == "undecided"

    def test_a_small_extent_is_a_geo_signal_a_whole_country_box_is_not(self) -> None:
        found = _find("Statistik")
        small = Extent("source", bbox=(9.0, 53.0, 10.0, 54.0))
        country = Extent("source", bbox=(5.8, 47.2, 15.1, 55.1))
        assert _verdict(found, small) == "geodata"
        assert _verdict(found, country) == "not_geodata"
        assert _verdict(found, Extent("place", codes=("DE", "DE-HH"))) == "geodata"
        assert _verdict(found, Extent("place", codes=("DE",))) == "not_geodata"

    @pytest.mark.parametrize(
        ("title", "publisher", "extent"),
        [
            # Otto, 23.11.2026: statistics tables of the Statistisches Landesamt des Freistaates Sachsen with a CSV at
            # genonline stayed visible through the extent of the Land.
            (
                "Straßenverkehrsunfälle: Beteiligte nach Art der Beteiligung, Sachsen - Jahr",
                "Statistisches Landesamt des Freistaates Sachsen",
                Extent("place", codes=("DE", "DE-SN")),
            ),
            (
                "Tourismus: Hotellerie nach Reisegebieten (ab 2012)",
                "Statistisches Landesamt des Freistaates Sachsen",
                Extent("source", bbox=(11.8, 50.1, 15.1, 51.7)),
            ),
            ("Köln: Einwohner", "IT.NRW", Extent("place", codes=("DE", "DE-NW"))),
        ],
    )
    def test_an_extent_keeps_no_table_of_a_statistics_office(self, title: str, publisher: str, extent: Extent) -> None:
        csv = [{"href": "https://www.example.org/x.csv", "format": "CSV", "media_type": None}]
        classified = classify(_find(title, publisher=publisher, distributions=csv), extent, country="DE", rule=RULE)
        assert (classified.outcome, classified.weak_overruled) == ("not_geodata", True)

    @pytest.mark.parametrize(
        "changes",
        [
            {"distributions": [{"href": "https://x.example/a.shp", "format": "SHP", "media_type": None}]},
            {"themes": ["inspire:su"]},
            {"keywords": ["Standorte"]},
        ],
    )
    def test_strong_geo_signals_still_keep_a_find_of_a_statistics_office(self, changes: dict[str, Any]) -> None:
        found = _find("Gemeinden", publisher=STATISTICS_OFFICE, **changes)
        assert _verdict(found, Extent("place", codes=("DE", "DE-SN"))) == "geodata"

    def test_a_csv_with_an_extent_of_another_publisher_stays_geodata(self) -> None:
        csv = [{"href": "https://www.example.org/x.csv", "format": "CSV", "media_type": None}]
        found = _find("Pegelstände Elbe", publisher="Landesamt für Umwelt", distributions=csv)
        assert _verdict(found, Extent("place", codes=("DE", "DE-SN"))) == "geodata"
        # A statistics word in the title of another publisher is outweighed by the extent as before.
        assert _verdict(_find("Statistik der Pegel"), Extent("place", codes=("DE", "DE-SN"))) == "geodata"

    @pytest.mark.parametrize("title", ["PRTR_Betriebsstaetten_RLP", "Betriebsstätten nach E-PRTR", "PRTR"])
    def test_prtr_registers_are_places(self, title: str) -> None:
        # Otto, 23.11.2026: "PRTR_Betriebsstaetten_RLP" was hidden as no geodata.
        assert _verdict(_find(title, publisher=STATISTICS_OFFICE)) == "geodata"

    @pytest.mark.parametrize(
        "title",
        [
            "Steuerpflichtige und Betriebsstätten der Gewerbesteuer",
            "Gewerbesteuer: Steuerpflichtige, Betriebsstaetten nach Kreisen (ab 2010)",
            "Industriebetriebsstätte Nord",
        ],
    )
    def test_sites_without_prtr_keep_no_table_of_a_statistics_office(self, title: str) -> None:
        # Otto, 24.11.2026: "Betriebsstätte(n)" alone kept the tax statistics of Destatis.
        assert _verdict(_find(title, publisher="Statistisches Bundesamt")) == "not_geodata"

    def test_the_library_statistics_with_en_is_a_non_geo_word_the_extent_still_outweighs(self) -> None:
        # Otto, 24.11.2026: Thurgau, "Bibliothekenstatistik der Öffentlichen Bibliotheken im Kanton Thurgau". The word
        # hides it without a geo signal; the extent of a publisher that is no statistics office still keeps it (rule
        # of 23.11.2026; plan M5-67 F14), and warning sign W1 keeps it out of a stack.
        title = "Bibliothekenstatistik der Öffentlichen Bibliotheken im Kanton Thurgau (2005-2019)"
        assert _verdict(_find(title, publisher="Kanton Thurgau"), Extent("catalog", codes=("CH",)), "CH") == (
            "not_geodata"
        )
        assert _verdict(_find(title, publisher="Kanton Thurgau"), Extent("place", codes=("CH", "CH-TG")), "CH") == (
            "geodata"
        )

    @pytest.mark.parametrize("title", ["Katzen - Verteilung pro Gemeinde", "Ziegen - Verteilung pro Kanton"])
    def test_an_extent_keeps_no_find_of_a_publisher_without_geodata(self, title: str) -> None:
        # Otto, 24.11.2026: two finds of Identitas AG were kept by their extent alone.
        extent = Extent("place", codes=("CH", "CH-BE"))
        classified = classify(_find(title, publisher="Identitas AG"), extent, country="CH", rule=RULE)
        assert (classified.outcome, classified.weak_overruled) == ("not_geodata", True)
        # A strong signal still keeps it.
        shapefile = [{"href": "https://x.example/a.shp", "format": "SHP", "media_type": None}]
        assert _verdict(_find(title, publisher="Identitas AG", distributions=shapefile), extent, "CH") == "geodata"

    def test_a_word_that_only_contains_a_site_word_is_no_signal(self) -> None:
        assert _verdict(_find("Betriebsstatistik", publisher=STATISTICS_OFFICE)) == "not_geodata"

    @pytest.mark.parametrize("title", ["Historische Karten der Aare", "Karte der Wanderwege", "Plan der Stadt"])
    def test_map_and_plan_are_geo_words(self, title: str) -> None:
        assert _verdict(_find(title, publisher=STATISTICS_OFFICE)) == "geodata"

    def test_a_map_word_inside_another_word_is_no_signal(self) -> None:
        assert _verdict(_find("Eintrittskarten und Haushaltsplan")) == "not_geodata"

    @pytest.mark.parametrize(
        ("title", "keywords"),
        [("snowBedFoam: a solver for snow transport", []), ("Modell der Schneedecke", ["Software", "OpenFOAM"])],
    )
    def test_software_is_no_geodata_even_at_a_geodata_publisher(self, title: str, keywords: list[str]) -> None:
        found = _find(title, publisher="EnviDat", category="other", keywords=keywords)
        assert _verdict(found, Extent("source", bbox=(7.0, 46.0, 7.1, 46.1)), country="CH") == "not_geodata"

    def test_software_with_a_raster_stays_geodata(self) -> None:
        found = _find("Solver output", publisher="EnviDat", data_kind="raster")
        assert _verdict(found) == "geodata"

    def test_the_shipped_rule_loads(self) -> None:
        assert read_geodata_rule(GEODATA_FILE).geo_data_kinds == {"raster", "vector", "service"}

    @pytest.mark.parametrize(
        ("old", "new", "message"),
        [
            ("extent_share_below: 0.5", "extent_share_below: 2", "extent_share_below"),
            ("geo_data_kinds: [raster", "geo_data_kinds: [pixels", "data kinds"),
            ("geo_categories: [optical", "geo_categories: [nowhere", "categories"),
            ('["statisti*"', '["*statisti*"', "one end"),
            ("not_geo_eu_themes: [GOVE", "not_geo_eu_themes: [gove", "codes"),
        ],
    )
    def test_load_errors(self, tmp_path: Path, old: str, new: str, message: str) -> None:
        text = GEODATA_FILE.read_text(encoding="utf-8")
        assert old in text
        path = tmp_path / "geodata.yaml"
        path.write_text(text.replace(old, new), encoding="utf-8")
        with pytest.raises(EntryFileError, match=message):
            read_geodata_rule(path)


KNOWN = {"ch.swisstopo.swissalti3d": "data.geo.admin.ch", "ch.bafu.laerm": "data.geo.admin.ch"}


class TestKeys:
    def test_an_id_counts_only_as_a_whole_token(self) -> None:
        # Otto, 19.11.2026 (M7): ch.swisstopo.x is not ch.swisstopo.x-y.
        addresses = ["https://map.geo.admin.ch/?layers=ch.swisstopo.swissalti3d-reliefschattierung"]
        assert collection_tokens(addresses, KNOWN) == set()
        addresses = ["https://data.geo.admin.ch/browser/#/collections/ch.swisstopo.swissalti3d"]
        assert collection_tokens(addresses, KNOWN) == {"coll:data.geo.admin.ch/ch.swisstopo.swissalti3d"}

    def test_a_collection_in_a_distribution_is_no_key_without_the_switch_of_the_source(self) -> None:
        found = {"distributions": [{"href": "https://map.geo.admin.ch/?layers=ch.bafu.laerm"}]}
        assert find_keys(found, stac_host=None, known=KNOWN, collection_links=False) == ()

    def test_a_find_naming_two_collections_gets_none(self) -> None:
        found = {"source_url": "https://map.geo.admin.ch/?layers=ch.swisstopo.swissalti3d,ch.bafu.laerm"}
        assert find_keys(found, stac_host=None, known=KNOWN) == ()

    def test_a_collection_in_a_distribution_or_a_reference_is_no_key(self) -> None:
        # Otto, 23.11.2026: the GovData find "Internationale Flussgebietseinheiten nach Wasserrahmenrichtlinie" links to
        # a collection of the FSDI; that makes it no duplicate of the collection.
        known = {"ch.bafu.wasser-einzugsgebietsgliederung": "data.geo.admin.ch"}
        found = {
            "source_key": "ac63368c-5b3e-40c4-816e-4f9fa84e2f6e",
            "source_url": "https://www.govdata.de/suche/daten/internationale-flussgebietseinheiten",
            "landing_url": "https://www.govdata.de/suche/daten/internationale-flussgebietseinheiten",
            "distributions": [
                {"href": "https://data.geo.admin.ch/browser/#/collections/ch.bafu.wasser-einzugsgebietsgliederung"}
            ],
        }
        assert find_keys(found, stac_host=None, known=known) == ()
        # Where the dataset itself is at that address, or its identifier says so, it is the key.
        coll = "coll:data.geo.admin.ch/ch.bafu.wasser-einzugsgebietsgliederung"
        page = "https://data.geo.admin.ch/browser/#/collections/ch.bafu.wasser-einzugsgebietsgliederung"
        assert find_keys({**found, "landing_url": page}, stac_host=None, known=known) == (coll,)
        assert find_keys({**found, "source_url": page}, stac_host=None, known=known) == (coll,)
        named = {**found, "identifier": "ch.bafu.wasser-einzugsgebietsgliederung"}
        assert find_keys(named, stac_host=None, known=known) == (coll, "id:ch.bafu.wasser-einzugsgebietsgliederung")

    def test_the_govdata_find_with_a_linked_collection_is_no_duplicate_of_it(self) -> None:
        known = {"ch.bafu.wasser-einzugsgebietsgliederung": "data.geo.admin.ch"}
        found = {
            "source_key": "ac63368c",
            "source_url": "https://www.govdata.de/suche/daten/internationale-flussgebietseinheiten",
            "distributions": [{"href": "https://map.geo.admin.ch/?layers=ch.bafu.wasser-einzugsgebietsgliederung"}],
        }
        coll = "coll:data.geo.admin.ch/ch.bafu.wasser-einzugsgebietsgliederung"
        members = [
            Member("fsdi-stac.x", (coll,), (2, 1), "fsdi-stac"),
            Member("govdata.ac63368c", find_keys(found, stac_host=None, known=known), (2, 3), "govdata"),
        ]
        assert main_entries(members) == {}

    def test_the_page_of_a_dataset_is_no_key(self) -> None:
        found = {"landing_url": "https://amt.example.org/daten", "source_url": "https://amt.example.org/daten"}
        assert find_keys(found, stac_host=None, known=KNOWN) == ()

    def test_doi_identifier_and_stac_collection(self) -> None:
        found = {"doi": "10.5281/ABC", "identifier": "x@amt", "source_key": "ch.bafu.laerm"}
        assert find_keys(found, stac_host="data.geo.admin.ch", known=KNOWN) == (
            "coll:data.geo.admin.ch/ch.bafu.laerm",
            "doi:10.5281/abc",
            "id:x@amt",
        )

    @pytest.mark.parametrize(("value", "expected"), [("ch.swisstopo.x", True), ("sentinel-2-l2a", False), ("a.b", False)])
    def test_only_namespaced_ids_are_looked_for(self, value: str, expected: bool) -> None:
        assert namespaced(value) is expected


LINKED = {
    "ch.bakom.notruf": "data.geo.admin.ch",
    "ch.bafu.neophyten": "data.geo.admin.ch",
    "ch.bafu.wasser-einzugsgebietsgliederung": "data.geo.admin.ch",
}
NOTRUF = "coll:data.geo.admin.ch/ch.bakom.notruf"
NEOPHYTEN = "coll:data.geo.admin.ch/ch.bafu.neophyten"


def _keys(found: dict[str, Any], *, links: bool = True) -> tuple[str, ...]:
    return find_keys(found, stac_host=None, known=LINKED, collection_links=links)


class TestCollectionLinks:
    """Otto, 24.11.2026: the narrow rule for opendata.swiss; a viewer link of the FSDI names its collection."""

    @pytest.mark.parametrize("number", ["117", "144"])
    def test_the_skipped_collection_page_of_the_emergency_numbers_is_the_key(self, number: str) -> None:
        # Both finds link the same viewer page of ch.bakom.notruf, so the link "Source" skipped it as a collective page.
        page = "https://data.geo.admin.ch/browser/index.html#/collections/ch.bakom.notruf"
        found = {
            "source_key": f"notruf-{number}",
            "source_url": f"https://opendata.swiss/de/dataset/notruf-{number}",
            "landing_url": f"https://opendata.swiss/de/dataset/notruf-{number}",
            "skipped_url": page,
            "skipped_rank": 1,
            "link_candidates": [[1, page]],
        }
        assert _keys(found) == (NOTRUF,)
        assert _keys(found, links=False) == ()

    def test_the_link_candidates_and_the_distributions_count(self) -> None:
        candidates = {"link_candidates": [[1, "https://map.geo.admin.ch/?lang=de&layers=ch.bafu.neophyten&topic=bafu"]]}
        assert _keys(candidates) == (NEOPHYTEN,)
        files = {"distributions": [{"href": "https://data.geo.admin.ch/browser/#/collections/ch.bafu.neophyten/items/x"}]}
        assert _keys(files) == (NEOPHYTEN,)

    def test_a_layer_may_carry_a_parameter_and_be_listed_twice(self) -> None:
        link = "https://map.geo.admin.ch/#/map?layers=ch.bafu.neophyten@year=2020,ch.bafu.neophyten&lang=de"
        assert _keys({"distributions": [{"href": link}]}) == (NEOPHYTEN,)

    def test_an_escaped_comma_and_at_sign_are_read(self) -> None:
        link = "https://map.geo.admin.ch/?layers=ch.bafu.neophyten%40year%3D2020%2Cch.bafu.neophyten"
        assert _keys({"distributions": [{"href": link}]}) == (NEOPHYTEN,)

    @pytest.mark.parametrize(
        "link",
        [
            "https://map.geo.admin.ch/?layers=ch.bafu.neophyten,ch.bakom.notruf",
            "https://map.geo.admin.ch/?topic=ch.bafu.neophyten",
            "https://map.geo.admin.ch/?layers_visibility=ch.bafu.neophyten",
            "https://map.geo.admin.ch/?layers=ch.bafu.unknown",
            "https://data.geo.admin.ch/ch.bafu.neophyten/neophyten.zip",
            "https://data.geo.admin.ch/browser/#/collections/ch.bafu.neophyten-x",
            "https://www.example.org/?layers=ch.bafu.neophyten",
            "https://example.org/collections/ch.bafu.neophyten",
            "https://map.geo.admin.ch.example.org/?layers=ch.bafu.neophyten",
            "http://map.geo.admin.ch/?layers=ch.bafu.neophyten",
        ],
    )
    def test_any_other_link_names_no_collection(self, link: str) -> None:
        assert _keys({"distributions": [{"href": link}]}) == ()

    def test_two_collections_among_all_addresses_give_no_key(self) -> None:
        found = {
            "source_url": "https://map.geo.admin.ch/?layers=ch.bakom.notruf",
            "distributions": [{"href": "https://map.geo.admin.ch/?layers=ch.bafu.neophyten"}],
            "skipped_url": None,
        }
        assert _keys(found) == ()

    def test_the_govdata_find_of_the_water_framework_directive_gets_no_key(self) -> None:
        # Otto, 23.11.2026: it links to a collection of the FSDI and is not that collection; GovData has no switch.
        found = {
            "source_key": "ac63368c-5b3e-40c4-816e-4f9fa84e2f6e",
            "source_url": "https://www.govdata.de/suche/daten/internationale-flussgebietseinheiten",
            "distributions": [
                {"href": "https://map.geo.admin.ch/?layers=ch.bafu.wasser-einzugsgebietsgliederung"},
                {"href": "https://data.geo.admin.ch/browser/#/collections/ch.bafu.wasser-einzugsgebietsgliederung"},
            ],
            "link_candidates": [[1, "https://data.geo.admin.ch/browser/#/collections/ch.bafu.wasser-einzugsgebietsgliederung"]],
        }
        assert _keys(found, links=False) == ()

    def test_the_two_emergency_numbers_are_duplicates_of_the_collection_and_the_water_find_is_not(self) -> None:
        notruf = {"skipped_url": "https://data.geo.admin.ch/browser/#/collections/ch.bakom.notruf"}
        water = {"distributions": [{"href": "https://map.geo.admin.ch/?layers=ch.bakom.notruf"}]}
        members = [
            Member("fsdi-stac.ch.bakom.notruf", (NOTRUF,), (2, 1), "fsdi-stac"),
            Member("opendata-swiss.117", _keys(notruf), (2, 2), "opendata-swiss"),
            Member("opendata-swiss.144", _keys(notruf), (2, 2), "opendata-swiss"),
            Member("govdata.ac63368c", _keys(water, links=False), (2, 3), "govdata"),
        ]
        assert main_entries(members) == {
            "opendata-swiss.117": "fsdi-stac.ch.bakom.notruf",
            "opendata-swiss.144": "fsdi-stac.ch.bakom.notruf",
        }

    def test_linked_collections_reads_the_links_only(self) -> None:
        assert linked_collections(["https://example.org/x", "text"], LINKED) == set()


class TestGroups:
    def test_the_main_entry_is_first_by_rank_and_a_group_joins_through_shared_keys(self) -> None:
        members = [
            Member("opendata-swiss.a", ("coll:h/x",), (2, 2)),
            Member("fsdi-stac.x", ("coll:h/x", "doi:1"), (2, 1)),
            Member("govdata.b", ("doi:1",), (2, 3)),
            Member("alone", ("doi:2",), (2, 1)),
        ]
        assert main_entries(members) == {"opendata-swiss.a": "fsdi-stac.x", "govdata.b": "fsdi-stac.x"}

    def test_a_full_entry_wins(self) -> None:
        members = [Member("fsdi-stac.x", ("coll:h/x",), (2, 1)), Member("swissalti3d", ("coll:h/x",), (0,))]
        assert main_entries(members) == {"fsdi-stac.x": "swissalti3d"}

    def test_an_identifier_on_many_finds_is_a_placeholder_and_joins_nothing(self) -> None:
        # Review M5-20 PR 1: a portal that writes "1" or its own address into every package.
        members = [Member(f"s{i}.a", ("id:1",), (2, 3, i), f"s{i}") for i in range(MAX_SHARED + 1)]
        assert main_entries(members) == {}
        assert len(main_entries(members[:MAX_SHARED])) == MAX_SHARED - 1

    def test_an_identifier_twice_in_one_source_is_no_key(self) -> None:
        # Otto, 23.11.2026: "Bevölkerungsentwicklung (jahresweise)" was a duplicate of "Gäste und Übernachtungen im
        # Jahresverlauf", two GovData finds with one placeholder; the same holds for a DOI.
        members = [
            Member("govdata.cd084048", ("id:statistik",), (2, 3, 1), "govdata"),
            Member("govdata.8dc6087a", ("id:statistik",), (2, 3, 1), "govdata"),
            Member("govdata.x", ("doi:10.1/a",), (2, 3, 1), "govdata"),
            Member("govdata.y", ("doi:10.1/a",), (2, 3, 1), "govdata"),
        ]
        assert main_entries(members) == {}

    def test_the_same_identifier_in_two_sources_still_joins(self) -> None:
        members = [Member("govdata.a", ("id:x@amt",), (2, 3), "govdata"), Member("ods.a", ("id:x@amt",), (2, 2), "ods")]
        assert main_entries(members) == {"govdata.a": "ods.a"}

    def test_a_find_joins_no_main_entry_it_shares_no_key_with(self) -> None:
        # Otto, 23.11.2026: "Internationale Flussgebietseinheiten nach Wasserrahmenrichtlinie" (GovData) was a duplicate
        # of the FSDI collection ch.bafu.wasser-einzugsgebietsgliederung through a find in between.
        coll = "coll:data.geo.admin.ch/ch.bafu.wasser-einzugsgebietsgliederung"
        members = [
            Member("fsdi-stac.ch.bafu.wasser-einzugsgebietsgliederung", (coll,), (2, 1), "fsdi-stac"),
            Member("opendata-swiss.b", (coll, "id:wrrl"), (2, 2), "opendata-swiss"),
            Member("govdata.ac63368c", ("id:wrrl",), (2, 3), "govdata"),
        ]
        assert main_entries(members) == {"opendata-swiss.b": "fsdi-stac.ch.bafu.wasser-einzugsgebietsgliederung"}

    def test_collection_ids_named_by_several_finds_of_one_source_still_join(self) -> None:
        coll = "coll:h/ch.bafu.x"
        members = [
            Member("fsdi-stac.x", (coll,), (2, 1), "fsdi-stac"),
            Member("ods.a", (coll,), (2, 2), "ods"),
            Member("ods.b", (coll,), (2, 2), "ods"),
        ]
        assert main_entries(members) == {"ods.a": "fsdi-stac.x", "ods.b": "fsdi-stac.x"}

    def test_the_report_names_the_shared_key(self) -> None:
        assert shared_key(["doi:1", "id:a"], ["id:a", "coll:h/x"]) == "id:a"
        assert shared_key(["id:a"], []) is None

    def test_no_keys_no_group(self) -> None:
        assert main_entries([Member("a", (), (2,)), Member("b", (), (2,))]) == {}


@pytest.mark.parametrize(
    ("title", "publisher", "outcome"),
    [
        # Otto, 20.11.2026, from the borderline samples of --classify.
        ("Strukturdaten Kristall X", "Materials Cloud", "not_geodata"),
        ("Messreihe 42", "PSI Data Catalog", "not_geodata"),
        ("Bestand 2023", "Deutsche Bibliotheksstatistik", "not_geodata"),
        ("Fälle 2022", "Bundeskriminalamt", "not_geodata"),
        ("Verfahren 2021", "Bundesamt für Justiz", "not_geodata"),
        ("Staatsarchiv Hamburg: Bestände", "Behörde für Kultur und Medien", "not_geodata"),
        ("Polizeiliche Kriminalstatistik 2023", "Amt", "not_geodata"),
        ("Organigramm der Verwaltung", "Amt", "not_geodata"),
        ("Fernsehprogramm", "Amt", "not_geodata"),
        ("Jahresabschluss 2022 – Anhang", "Amt", "not_geodata"),
        ("Müllabfuhrtermine 2024", "Amt", "not_geodata"),
        # Geo signals that never hide, even beside a non-geo word.
        ("Denkmalliste Statistik", "Amt", "geodata"),
        ("Straßenverzeichnis", "Statistisches Amt", "geodata"),
        ("Strassenverzeichnis", "Statistisches Amt", "geodata"),
        ("Ortschaftenverzeichnis", "Statistisches Amt", "geodata"),
        ("Jahresniederschlag Statistik", "Amt", "geodata"),
        ("Verkehrszählung 2023", "Statistisches Amt", "geodata"),
        # EnviDat stays geodata.
        ("Statistics of snow", "EnviDat", "geodata"),
    ],
)
def test_the_lists_of_otto_s_samples(title: str, publisher: str, outcome: str) -> None:
    assert _verdict(_find(title, publisher=publisher)) == outcome



@pytest.mark.parametrize(
    ("title", "publisher", "outcome"),
    [
        # Otto, 20.11.2026, second run.
        ("Rinder - Altersstruktur", "Identitas AG", "not_geodata"),
        ("Entwurf eines Landesgesetzes zur Änderung des Sparkassengesetzes", "Staatskanzlei", "not_geodata"),
        ("Entwurf einer Landesverordnung über die Aktenführung", "Staatskanzlei", "not_geodata"),
        ("gemeldete Corona Fälle - Kreisdaten", "Land", "not_geodata"),
        ("D01 Vornamen eines Geburtsjahres Elsdorf", "Kommune", "not_geodata"),
        ("GZR-Daten zur Schwarzarbeit 2022", "–", "not_geodata"),
        ("Landsgemeinde vom 01. Mai 2016", "Kanton Glarus", "not_geodata"),
        ("Geschäfte im Kantonsrat St.Gallen", "Kanton St. Gallen", "not_geodata"),
        ("Digitalisierte Handschriften der Kantonsbibliothek", "Kanton Thurgau", "not_geodata"),
        ("Ordnungsbussen nach Bussentyp", "Kanton Thurgau", "not_geodata"),
        ("Statistik der Bussen", "Bundesjustizamt", "not_geodata"),
        # Geo signals that never hide.
        ("Bebauungsplan Nr. 103 Statistik", "Amt", "geodata"),
        ("Flaechennutzungsplan VG Schweich", "Amt", "geodata"),
        ("Flächennutzungsplan Statistik", "Amt", "geodata"),
        ("Naturschutzgebiet (NSG) Elbniederung", "Statistisches Amt", "geodata"),
        ("ÖPNV - Netzpläne der Buslinien", "Statistisches Amt", "geodata"),
        ("Findlinge im Stadtgebiet", "Statistisches Amt", "geodata"),
        ("AIS-Daten zur Schiffsabgasmessung", "Statistisches Amt", "geodata"),
        ("Beurteilungspegel Bahnlärm Tag", "Statistisches Amt", "geodata"),
        ("Hydrometrie Thurgau - Wasserstand", "Statistisches Amt", "geodata"),
        ("Luftqualitätsmessungen Ostluft", "Statistisches Amt", "geodata"),
        # "Alarm" is no noise.
        ("Alarmierungen der Feuerwehr Statistik", "Amt", "not_geodata"),
    ],
)
def test_the_lists_of_otto_s_second_samples(title: str, publisher: str, outcome: str) -> None:
    assert _verdict(_find(title, publisher=publisher)) == outcome

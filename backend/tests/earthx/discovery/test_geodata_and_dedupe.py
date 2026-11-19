"""The rule R-G on finds that are no geodata, and dedupe (M5-20 plan §7, §8, §13b; F3 = 1, F4 = 1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from earthx.catalog.entry_files import EntryFileError
from earthx.discovery.dedupe import MAX_SHARED, Member, collection_tokens, find_keys, main_entries, namespaced
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

    def test_a_find_naming_two_collections_gets_none(self) -> None:
        found = {"source_url": "https://map.geo.admin.ch/?layers=ch.swisstopo.swissalti3d,ch.bafu.laerm"}
        assert find_keys(found, stac_host=None, known=KNOWN) == ()

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
        members = [Member(f"govdata.{i}", ("id:1",), (2, 3, i)) for i in range(MAX_SHARED + 1)]
        assert main_entries(members) == {}
        assert len(main_entries(members[:MAX_SHARED])) == MAX_SHARED - 1

    def test_no_keys_no_group(self) -> None:
        assert main_entries([Member("a", (), (2,)), Member("b", (), (2,))]) == {}

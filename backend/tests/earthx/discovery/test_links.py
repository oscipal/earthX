"""The link "Source" of a harvested find (Otto, 17.11.2026; M5-19 plan §6, F1 = 1)."""

from __future__ import annotations

import pytest

from earthx.discovery.links import (
    MAX_LINK_CHARS,
    LinkIndex,
    LinkRank,
    address_key,
    api_pattern,
    checked_link,
    choose_link,
    first_link,
    is_collection_page,
    link_candidates,
    link_problem,
)

VIEWER = LinkRank.VIEWER_OR_DOWNLOAD_PAGE
DATASET = LinkRank.DATASET_PAGE
CATALOGUE = LinkRank.CATALOGUE_PAGE


@pytest.mark.parametrize(
    "url",
    [
        "https://data.example.org/download/dem",
        "https://data.example.org/?dataset=dem",
        "https://data.example.org/#/collections/dem",
        "https://data.example.org:443/de/dem",
        "https://viewer.example.org/map?layers=dem&lang=de",
    ],
)
def test_a_page_passes(url: str) -> None:
    assert checked_link(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "https://data.example.org",
        "https://data.example.org/",
        "https://data.example.org/de",
        "https://data.example.org/fr/",
        "https://data.example.org/en-gb/",
        "https://data.example.org/#/",
        "https://data.example.org//",
        "https://data.example.org/?",
        "https://data.example.org?lang=de",
        "https://data.example.org/index.html",
        "https://data.example.org/de/index.html",
        "https://data.example.org/fr/home.php?locale=fr",
    ],
)
def test_the_start_page_never_passes(url: str) -> None:
    assert checked_link(url) is None


@pytest.mark.parametrize(
    "url",
    [
        "http://data.example.org/dem",
        "javascript:alert(1)",
        "ftp://data.example.org/dem",
        "https://user:secret@data.example.org/dem",
        "https://192.0.2.10/dem",
        "https://[2001:db8::1]/dem",
        "https://localhost/dem",
        "https://data.example.org:8443/dem",
        "https://data.example.org/a b",
        "https://data.example.org/dem\n",
        "https://data.example.org/dem\x00",
        "https://data.example.org/dem\ud800",
        "https://data.example.org/" + "a" * MAX_LINK_CHARS,
        "",
        None,
        42,
        ["https://data.example.org/dem"],
    ],
)
def test_an_untrusted_link_never_passes(url: object) -> None:
    assert checked_link(url) is None


def test_the_best_rank_wins_whatever_the_order() -> None:
    chosen = choose_link(
        [
            (CATALOGUE, "https://catalogue.example.org/dataset/dem"),
            (DATASET, "https://provider.example.org/data/dem"),
            (VIEWER, "https://viewer.example.org/map/dem"),
        ]
    )
    assert chosen == ("https://viewer.example.org/map/dem", VIEWER)


def test_an_invalid_better_link_gives_way_to_the_next_rank() -> None:
    chosen = choose_link(
        [
            (VIEWER, "http://viewer.example.org/dem"),
            (DATASET, "https://provider.example.org/"),
            (CATALOGUE, "https://catalogue.example.org/dataset/dem"),
        ]
    )
    assert chosen == ("https://catalogue.example.org/dataset/dem", CATALOGUE)


def test_within_a_rank_the_first_valid_one_wins() -> None:
    chosen = choose_link([(VIEWER, "https://a.example.org/x/1"), (VIEWER, "https://b.example.org/x/2")])
    assert chosen == ("https://a.example.org/x/1", VIEWER)


def test_no_valid_link_is_none() -> None:
    assert choose_link([(VIEWER, "http://a.example.org/1"), (CATALOGUE, None)]) is None
    assert choose_link([]) is None


@pytest.mark.parametrize(
    ("url", "problem"),
    [
        ("https://example.org/data/1", None),
        ("http://example.org/data/1", "http"),
        ("ftp://example.org/data/1", "scheme"),
        ("", "empty"),
        (None, "empty"),
        ("https://example.org/", "start_page"),
        ("https://example.org/de/", "start_page"),
        ("https://192.0.2.1/data", "host"),
        ("https://example.org:8443/data", "port"),
        ("https://example.org/da ta", "control"),
        ("https://example.org/" + "x" * 3000, "long"),
        ("https://user@example.org/data", "invalid"),
    ],
)
def test_why_a_link_may_not_be_the_link_source(url: object, problem: str | None) -> None:
    assert link_problem(url) == problem
    assert (checked_link(url) is None) == (problem is not None)


# --- Collective pages (Otto, 21.11.2026) ---------------------------------------------------------------------------

#: The pages the finding of 21.11.2026 named (opendata.swiss): the start page of an office, and a theme page many
#: finds name.
OFFICE = "https://www.sz.ch/agi"
THEME = "https://oereb.bs.ch/theme/oereb_proj"
CATALOGUE_PAGE = "https://catalogue.example.org/dataset/dem"


@pytest.mark.parametrize(
    "url",
    [
        OFFICE,
        "https://www.sz.ch/agi/",
        "https://WWW.sz.ch/agi",
        "https://geo.example.ch/geodaten",
        "https://geo.example.ch/geodaten?lang=de",
        "https://geo.example.ch/geodaten#",
        "https://geo.example.ch/geodaten#/",
        "https://geo.example.ch/",
        "https://geo.example.ch",
        "https://geo.example.ch/de",
        "https://geo.example.ch/?lang=fr",
        # A leading language is no part of the path (Otto, 21.11.2026).
        "https://www.sz.ch/de/agi",
        "https://www.sz.ch/DE/agi/",
        "https://www.sz.ch/fr/agi",
        "https://www.sz.ch/it/agi",
        "https://www.sz.ch/en/agi",
        "https://www.sz.ch/rm/agi",
        "https://www.sz.ch/de/agi?lang=de",
    ],
)
def test_the_host_and_at_most_one_part_of_the_path_is_a_collective_page(url: str) -> None:
    assert is_collection_page(url)
    assert choose_link([(DATASET, url)]) is None


@pytest.mark.parametrize(
    "url",
    [
        THEME,
        "https://data.example.org/download/dem",
        "https://data.example.org/de/dem/x",
        "https://data.example.org/de/de/dem",
        "https://data.example.org/agi/de",
        # Only the five languages of the rule count, and only in front.
        "https://data.example.org/es/dem",
        "https://data.example.org/deutsch/dem",
        # Query and fragment belong to the address and make it specific.
        "https://geo.example.ch/geodaten?filter=dem",
        "https://geo.example.ch/?dataset=dem",
        "https://geo.example.ch/geodaten?lang=de&filter=dem",
        "https://geo.example.ch/#/produkt/dem",
        "https://geo.example.ch/geodaten#/produkt/dem",
        "https://www.sz.ch/de/agi?filter=dem",
        "https://www.sz.ch/de/agi#/produkt/dem",
    ],
)
def test_a_specific_address_is_no_collective_page_by_its_form(url: str) -> None:
    assert not is_collection_page(url)
    assert choose_link([(DATASET, url)]) == (url, DATASET)


@pytest.mark.parametrize(
    "url", [None, 42, "", "not an address", "http://geo.example.ch/geodaten", ["https://a.example.org"]]
)
def test_what_is_no_address_is_no_collective_page(url: object) -> None:
    assert not is_collection_page(url)


def test_a_collective_page_gives_way_to_the_next_rank() -> None:
    candidates = [(VIEWER, OFFICE), (DATASET, "https://provider.example.org/data/dem"), (CATALOGUE, CATALOGUE_PAGE)]
    assert choose_link(candidates) == ("https://provider.example.org/data/dem", DATASET)
    assert choose_link(candidates[:1] + candidates[2:]) == (CATALOGUE_PAGE, CATALOGUE)
    # Without the rule the better rank would have won; the extractors compare the two.
    assert first_link(candidates) == (OFFICE, VIEWER)


def test_within_a_rank_a_collective_page_gives_way_to_the_next_one() -> None:
    chosen = choose_link([(VIEWER, OFFICE), (VIEWER, "https://b.example.org/x/2")])
    assert chosen == ("https://b.example.org/x/2", VIEWER)


def test_the_page_in_the_catalogue_is_never_skipped() -> None:
    page = "https://catalogue.example.org/dem"
    assert choose_link([(CATALOGUE, page)], shared=frozenset({page})) == (page, CATALOGUE)
    assert choose_link([(CATALOGUE, "https://catalogue.example.org/dem")]) is not None
    assert choose_link([(CATALOGUE, "https://catalogue.example.org/browser")]) is not None


def test_the_addresses_a_source_shares_are_skipped() -> None:
    candidates = [(DATASET, THEME), (CATALOGUE, CATALOGUE_PAGE)]
    assert choose_link(candidates) == (THEME, DATASET)
    assert choose_link(candidates, shared=frozenset({address_key(THEME)})) == (CATALOGUE_PAGE, CATALOGUE)
    # The same page written another way is the same page.
    assert choose_link([(DATASET, THEME + "/")], shared=frozenset({address_key(THEME)})) is None


def test_the_addresses_of_the_same_page_agree() -> None:
    assert address_key("https://Oereb.BS.ch/theme/oereb_proj/") == address_key(THEME)
    assert address_key("https://oereb.bs.ch:443/theme/oereb_proj") == address_key(THEME)
    # Query and fragment tell two pages apart.
    assert address_key(THEME + "?a=1") != address_key(THEME + "?a=2")
    assert address_key(THEME + "#/a") != address_key(THEME + "#/b")
    assert address_key("not an address") == "not an address"


def _index(**finds: list[tuple[LinkRank, object]]) -> LinkIndex:
    index = LinkIndex()
    for key, candidates in finds.items():
        index.set(key, link_candidates(candidates))
    return index


def test_an_address_two_finds_would_choose_is_shared() -> None:
    page = "https://www.stadtluzern.example/geodaten/portal"
    index = _index(
        geotope=[(DATASET, page), (CATALOGUE, "https://c.example.org/dataset/geotope")],
        alters=[(DATASET, page), (CATALOGUE, "https://c.example.org/dataset/alters")],
        other=[(DATASET, "https://provider.example.org/data/other")],
    )
    assert index.shared() == {address_key(page)}
    assert index.link_of("geotope", index.shared()) is None
    assert index.link_of("other", index.shared()) == "https://provider.example.org/data/other"


def test_one_find_alone_shares_nothing() -> None:
    index = _index(a=[(VIEWER, "https://v.example.org/map/1"), (DATASET, "https://p.example.org/data/1")])
    assert index.shared() == frozenset()
    assert index.link_of("a", index.shared()) == "https://v.example.org/map/1"


def test_the_same_address_twice_in_one_find_is_one_find() -> None:
    page = "https://p.example.org/data/1"
    assert _index(a=[(VIEWER, page), (DATASET, page)]).shared() == frozenset()


def test_the_next_choice_of_a_find_can_be_shared_too() -> None:
    # a and b choose x, so x is skipped; both go on to y, which c chooses as well: y is shared, and all three end at
    # the catalogue, not at a page that three finds name.
    x, y = "https://p.example.org/data/x", "https://p.example.org/data/y"
    index = _index(a=[(VIEWER, x), (DATASET, y)], b=[(VIEWER, x), (DATASET, y)], c=[(DATASET, y)])
    assert index.shared() == {address_key(x), address_key(y)}
    assert [index.link_of(key, index.shared()) for key in "abc"] == [None, None, None]


def test_finds_that_choose_different_pages_do_not_share() -> None:
    x, y = "https://p.example.org/data/x", "https://p.example.org/data/y"
    index = _index(a=[(VIEWER, x), (DATASET, y)], b=[(VIEWER, y)])
    assert index.shared() == frozenset()
    assert index.link_of("a", index.shared()) == x


def test_the_page_a_find_falls_to_counts_for_the_others() -> None:
    # a and b choose x, so x goes; a falls to y, where c is: three finds on one page is what the rule is against.
    x, y = "https://p.example.org/data/x", "https://p.example.org/data/y"
    index = _index(a=[(VIEWER, x), (DATASET, y)], b=[(VIEWER, x)], c=[(VIEWER, y)])
    assert index.shared() == {address_key(x), address_key(y)}
    assert [index.link_of(key, index.shared()) for key in "abc"] == [None, None, None]


def test_a_page_is_shared_by_its_address_not_by_its_spelling() -> None:
    index = _index(a=[(DATASET, THEME)], b=[(DATASET, "https://oereb.bs.ch/theme/OEREB_PROJ")])
    assert index.shared() == frozenset()  # the path differs in case: a different page
    index = _index(a=[(DATASET, THEME)], b=[(DATASET, "https://OEREB.bs.ch/theme/oereb_proj/")])
    assert index.shared() == {address_key(THEME)}


def test_a_query_or_fragment_makes_two_finds_unique() -> None:
    index = _index(a=[(DATASET, THEME + "?filter=a")], b=[(DATASET, THEME + "?filter=b")], c=[(DATASET, THEME + "#/c")])
    assert index.shared() == frozenset()


def test_the_candidates_are_what_may_be_a_link_by_rank_one_and_two() -> None:
    assert link_candidates(
        [
            (VIEWER, "http://v.example.org/map/1"),
            (VIEWER, "https://v.example.org/map/2"),
            (DATASET, OFFICE),
            (DATASET, None),
            (DATASET, "https://p.example.org/data/1"),
            (CATALOGUE, CATALOGUE_PAGE),
        ]
    ) == ((1, "https://v.example.org/map/2"), (2, "https://p.example.org/data/1"))
    assert link_candidates([(CATALOGUE, CATALOGUE_PAGE)]) == ()


def test_a_find_without_candidates_is_not_in_the_index() -> None:
    index = _index(a=[(DATASET, OFFICE), (CATALOGUE, CATALOGUE_PAGE)], b=[(CATALOGUE, CATALOGUE_PAGE)])
    assert len(index) == 0 and "a" not in index


def test_a_find_that_changes_or_goes_leaves_the_shared_pages() -> None:
    page = "https://p.example.org/data/x"
    index = _index(a=[(DATASET, page)], b=[(DATASET, page)])
    assert index.shared() == {address_key(page)}
    index.set("b", [(DATASET, "https://p.example.org/data/b")])
    assert index.shared() == frozenset()
    index.set("b", [(DATASET, page)])
    index.discard("a")
    index.discard("unknown")
    assert index.shared() == frozenset() and len(index) == 1


def test_the_candidates_read_back_from_json_work_the_same() -> None:
    # The index is filled from the JSON lists of earthx_record_state: lists of lists.
    page = "https://p.example.org/data/x"
    index = LinkIndex()
    index.set("a", [[2, page]])
    index.set("b", [[2, page], [2, "https://p.example.org/data/b"]])
    assert index.shared() == {address_key(page)}


def test_the_stale_finds_are_those_whose_stored_link_is_not_the_one_they_choose() -> None:
    x, y = "https://p.example.org/data/x", "https://p.example.org/data/y"
    index = LinkIndex()
    index.set("alone", [(2, x)], stored=x)
    index.set("twin1", [(2, y)], stored=y)
    index.set("twin2", [(2, y)], stored=y)
    index.set("fine", [(2, "https://p.example.org/data/z")], stored="https://p.example.org/data/z")
    # `freed` was derived with the catalogue page, but its page is free; the twins share y and still hold it.
    index.set("freed", [(2, "https://p.example.org/data/w")], stored=None)
    assert index.stale(index.shared()) == ["freed", "twin1", "twin2"]
    assert LinkIndex().stale(frozenset()) == []


def test_a_find_without_a_free_link_is_stale_once_one_is_free() -> None:
    page = "https://p.example.org/data/x"
    index = LinkIndex()
    index.set("a", [(2, page)], invalid=True)
    assert index.stale(frozenset({address_key(page)})) == []
    assert index.stale(frozenset()) == ["a"]


@pytest.mark.parametrize(
    ("url", "pattern"),
    [
        ("https://open.bydata.de/api/hub/repo/datasets/x", "piveau /api/hub/"),
        ("https://ckan.example.org/api/3/action/package_show?id=x", "CKAN /api/action/"),
        ("https://gis.example.org/arcgis/rest/services/x/MapServer", "ArcGIS /rest/services"),
        ("https://geo.example.org/geonetwork/srv/api/records/1", "GeoNetwork /srv/api"),
        ("https://geo.example.org/geoserver/ows?x=1", "OGC-Pfad (wms, wfs, wcs, wmts, csw, ows)"),
        ("https://data.example.org/sparql?query=x", "SPARQL"),
        ("https://data.example.org/oai?verb=GetRecord", "OAI-PMH"),
        ("https://data.example.org/api/v1/datasets/x", "Pfadteil /api"),
        ("https://data.example.org/rest/x", "Pfadteil /rest"),
        ("https://data.example.org/x?format=json", "Format-Parameter json/xml/rdf"),
    ],
)
def test_api_patterns_are_named(url: str, pattern: str) -> None:
    assert api_pattern(url) == pattern


@pytest.mark.parametrize(
    "url", ["https://open.bydata.de/datasets/x", "https://data.example.org/apidoc/x", "https://x.org/restaurants", None]
)
def test_pages_and_other_values_match_no_api_pattern(url: object) -> None:
    assert api_pattern(url) is None

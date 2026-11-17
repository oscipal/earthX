"""The link "Source" of a harvested find (Otto, 17.11.2026; M5-19 plan §6, F1 = 1)."""

from __future__ import annotations

import pytest

from earthx.discovery.links import MAX_LINK_CHARS, LinkRank, checked_link, choose_link

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
            (DATASET, "https://provider.example.org/dem"),
            (VIEWER, "https://viewer.example.org/dem"),
        ]
    )
    assert chosen == ("https://viewer.example.org/dem", VIEWER)


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
    chosen = choose_link([(VIEWER, "https://a.example.org/1"), (VIEWER, "https://b.example.org/2")])
    assert chosen == ("https://a.example.org/1", VIEWER)


def test_no_valid_link_is_none() -> None:
    assert choose_link([(VIEWER, "http://a.example.org/1"), (CATALOGUE, None)]) is None
    assert choose_link([]) is None

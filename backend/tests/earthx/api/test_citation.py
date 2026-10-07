"""``citation.bib`` of the crop (adr/0014 §10.2, M4-14)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from earthx.api.citation import citation_bib
from earthx.catalog.datasets import REGISTRY, SENTINEL_2_L2A

DAY = date(2026, 10, 7)


def _bib(config, day: date = DAY) -> str:
    return citation_bib(config, downloaded=day).decode("utf-8")


def test_the_entry_is_the_documented_misc_shape() -> None:
    assert _bib(SENTINEL_2_L2A) == (
        "@misc{sentinel-2-c1-l2a,\n"
        "  title   = {Sentinel-2 L2A},\n"
        "  doi     = {10.5270/S2_-742ikth},\n"
        "  url     = {https://doi.org/10.5270/S2_-742ikth},\n"
        f"  note    = {{{SENTINEL_2_L2A.license.attribution_modified.format(year=2026)}}},\n"
        "  urldate = {2026-10-07}\n"
        "}\n"
    )


@pytest.mark.parametrize("config", list(REGISTRY), ids=lambda config: config.dataset_id)
def test_every_dataset_gets_one_entry_with_its_own_key(config) -> None:
    bib = _bib(config)
    assert bib.startswith(f"@misc{{{config.dataset_id},\n")
    assert bib.count("@misc") == 1
    assert bib.endswith("}\n")
    assert "urldate = {2026-10-07}" in bib


@pytest.mark.parametrize("config", list(REGISTRY), ids=lambda config: config.dataset_id)
def test_the_doi_field_is_the_name_never_the_url(config) -> None:
    bib = _bib(config)
    if config.doi:
        assert "doi" in bib
        assert "{https://doi.org/" not in bib.split("url", 1)[0]
    else:
        assert "doi " not in bib


def test_without_a_doi_the_persistent_citation_stands_as_note() -> None:
    config = replace(SENTINEL_2_L2A, doi=None, citation="Publisher (2026): Dataset, version 1.")
    bib = _bib(config)
    assert "doi " not in bib
    assert "url " not in bib
    assert "Publisher (2026): Dataset, version 1." in bib
    assert "Sentinel data 2026. Publisher (2026)" in bib


def test_without_doi_and_citation_the_entry_still_has_title_and_date() -> None:
    config = replace(SENTINEL_2_L2A, doi=None, citation=None)
    bib = _bib(config)
    assert "title" in bib
    assert "urldate" in bib


def test_the_year_of_the_attribution_is_the_year_of_the_download() -> None:
    assert "2031" in _bib(SENTINEL_2_L2A, date(2031, 1, 2))


def test_characters_bibtex_acts_on_are_escaped_so_braces_stay_balanced() -> None:
    config = replace(SENTINEL_2_L2A, title="Tom & {Jerry} 100% #1 a_b $5 \\x ^ ~", doi=None, citation=None)
    title = next(line for line in _bib(config).splitlines() if line.lstrip().startswith("title"))
    assert title.strip() == r"title   = {Tom \& \{Jerry\} 100\% \#1 a\_b \$5 \textbackslash{}x \textasciicircum{} \textasciitilde{}},"


def test_line_breaks_in_a_value_do_not_break_the_entry() -> None:
    config = replace(SENTINEL_2_L2A, doi=None, citation="two\nlines,\n\n  and  gaps")
    assert "two lines, and gaps" in _bib(config)


def test_a_dataset_id_that_is_no_bibtex_key_is_made_one() -> None:
    config = replace(SENTINEL_2_L2A, dataset_id="odd id,{x}")
    assert _bib(config).startswith("@misc{odd_id__x_,\n")


def test_the_file_is_utf_8_bytes() -> None:
    config = replace(SENTINEL_2_L2A, title="Überflug ∩ Karte")
    assert "Überflug ∩ Karte".encode("utf-8") in citation_bib(config, downloaded=DAY)

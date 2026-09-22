"""The mapping onto a STAC Collection.

Two things matter: the result is a valid STAC Collection, and it carries all eight
``earthx:`` fields of architekturplan.md 5.1 even where they are still empty.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pystac
import pytest

from earthx.catalog.collection import (
    SCIENTIFIC_EXTENSION,
    STAC_VERSION,
    _stac_license,
    to_stac_collection,
)
from earthx.catalog.datasets import SENTINEL_2_L2A

EARTHX_FIELDS = (
    "earthx:data_class",
    "earthx:capabilities",
    "earthx:license_flags",
    "earthx:access",
    "earthx:distributions",
    "earthx:health",
    "earthx:default_render",
    "earthx:viewer",
    "earthx:source",
)


@pytest.fixture
def collection() -> dict:
    return to_stac_collection(SENTINEL_2_L2A)


@pytest.mark.parametrize("field", EARTHX_FIELDS)
def test_every_earthx_field_of_5_1_is_present(collection: dict, field: str) -> None:
    assert field in collection


def test_the_coverage_fields_stay_out_of_the_collection(collection: dict) -> None:
    """adr/0004 §5: the registry entry decides the coverage path, not the collection.

    Emitting them here would add a ninth earthx: field to architekturplan.md 5.1 —
    a change to the architecture rather than a consequence of M1-04.
    """
    assert "earthx:coverage" not in collection
    assert not [key for key in collection if key.startswith("earthx:") and "coverage" in key]


def test_the_result_is_a_valid_stac_collection(collection: dict) -> None:
    """Read back by pystac, so the shape is checked against the spec, not against us."""
    parsed = pystac.Collection.from_dict(collection)
    assert parsed.id == "sentinel-2-c1-l2a"
    assert parsed.extent.spatial.bboxes == [list(SENTINEL_2_L2A.spatial_extent.bbox)]


def test_the_licence_value_is_the_one_stac_1_0_uses(collection: dict) -> None:
    """``proprietary`` is what STAC 1.0 and Earth Search itself write (adr/0003 §11.2).

    STAC 1.1 renamed the value to ``other`` and pystac normalises it on the way in,
    which is why this reads the dictionary rather than the parsed object. Which of
    the two we emit follows from the stac-fastapi version M1-07 pins.
    """
    assert collection["stac_version"] == "1.0.0"
    assert collection["license"] == "proprietary"



def test_source_carries_what_adr_0005_branches_on(collection: dict) -> None:
    source = collection["earthx:source"]
    assert source["adapter"] == "earth-search-v1"
    assert source["source_collection_id"] == "sentinel-2-c1-l2a"


def test_an_open_temporal_extent_stays_open(collection: dict) -> None:
    """M1 reads nothing from the source, so both ends are null rather than guessed."""
    assert collection["extent"]["temporal"]["interval"] == [[None, None]]


def test_check_dates_are_written_as_plain_dates(collection: dict) -> None:
    assert collection["earthx:access"]["token_free_checked_at"] == "2026-09-18"
    assert collection["earthx:health"]["last_checked_ok"] == "2026-09-18"


def test_the_terms_travel_with_the_collection(collection: dict) -> None:
    """Whoever reads our catalogue gets the source's terms with it, not just a flag."""
    flags = collection["earthx:license_flags"]
    assert flags["terms_url"] == SENTINEL_2_L2A.license.terms.url
    assert set(flags["terms_notice"]) == {"en"}


def test_the_terms_notice_is_copied_not_shared(collection: dict) -> None:
    collection["earthx:license_flags"]["terms_notice"]["en"] = "overwritten"
    assert SENTINEL_2_L2A.license.terms.notice["en"] != "overwritten"


def test_the_standard_visualisation_travels_in_the_field_names_of_the_render_extension(
    collection: dict,
) -> None:
    """adr/0006 §5: the values must be publishable as `renders` without a translation."""
    render = collection["earthx:default_render"]
    assert set(render) == {"title", "assets", "rescale", "colormap_name", "expression", "resampling"}
    assert render["assets"] == ["visual"]


def test_a_dataset_without_a_doi_declares_no_scientific_extension(collection: dict) -> None:
    assert collection["stac_extensions"] == []
    assert "sci:doi" not in collection


def test_the_licence_link_points_at_the_primary_source(collection: dict) -> None:
    licence_links = [link for link in collection["links"] if link["rel"] == "license"]
    assert [link["href"] for link in licence_links] == [SENTINEL_2_L2A.license.url]


class TestNoSharedState:
    """Two calls must not hand out the same mutable object."""

    def test_the_result_is_rebuilt_every_time(self) -> None:
        first = to_stac_collection(SENTINEL_2_L2A)
        second = to_stac_collection(SENTINEL_2_L2A)
        assert first == second
        first["earthx:distributions"].append({"mirror": "made up"})
        assert second["earthx:distributions"] == []

    def test_changing_the_result_does_not_reach_the_entry(self, valid_config) -> None:
        collection = to_stac_collection(valid_config)
        collection["earthx:default_render"]["assets"].append("nir")
        assert "nir" not in valid_config.default_render.assets

    def test_changing_the_bbox_does_not_reach_the_entry(self, valid_config) -> None:
        collection = to_stac_collection(valid_config)
        collection["extent"]["spatial"]["bbox"][0][0] = 0.0
        assert valid_config.spatial_extent.bbox[0] == -10.0


class TestAnEntryWithEverythingSet:
    """The Sentinel-2 entry leaves several fields open; this one fills them all in."""

    @pytest.fixture
    def full(self, valid_config) -> dict:
        return to_stac_collection(valid_config)

    def test_an_spdx_licence_is_written_as_it_stands(self, full: dict) -> None:
        """No "proprietary" or "other" where an identifier exists, in either STAC version."""
        assert full["license"] == "CC-BY-4.0"

    def test_a_doi_brings_in_the_scientific_extension(self, full: dict) -> None:
        assert full["stac_extensions"] == [SCIENTIFIC_EXTENSION]
        assert full["sci:doi"] == "10.5555/test"
        assert full["sci:citation"].startswith("Test publisher")

    def test_both_ends_of_the_temporal_extent_survive(self, full: dict) -> None:
        """An end written as midnight would quietly cut the last day off."""
        assert full["extent"]["temporal"]["interval"] == [
            ["2020-01-01T00:00:00Z", "2024-12-31T23:59:59Z"]
        ]

    def test_the_standard_visualisation_is_carried_over(self, full: dict) -> None:
        render = full["earthx:default_render"]
        assert render["assets"] == ["red", "green", "blue"]
        assert render["rescale"] == [[0.0, 3000.0]] * 3
        assert render["colormap_name"] is None
        assert render["resampling"] == "nearest"

    def test_the_result_survives_a_round_trip_through_json(self, full: dict) -> None:
        """04b hands this to pgstac, where a stray date or Enum would only show up late."""
        assert json.loads(json.dumps(full)) == full


class TestLicenceSpellingFollowsTheStacVersion:
    """STAC 1.1 dropped "proprietary" for "other"; the two must not drift apart."""

    def test_stac_1_0_says_proprietary(self, valid_config) -> None:
        license_info = replace(valid_config.license, spdx_id=None)
        assert _stac_license(license_info, "1.0.0") == "proprietary"

    def test_stac_1_1_says_other(self, valid_config) -> None:
        license_info = replace(valid_config.license, spdx_id=None)
        assert _stac_license(license_info, "1.1.0") == "other"

    def test_an_spdx_identifier_wins_in_both(self, valid_config) -> None:
        for version in ("1.0.0", "1.1.0"):
            assert _stac_license(valid_config.license, version) == "CC-BY-4.0"

    def test_what_we_emit_today_matches_the_version_we_declare(self, collection: dict) -> None:
        assert collection["stac_version"] == STAC_VERSION
        assert collection["license"] == _stac_license(SENTINEL_2_L2A.license, STAC_VERSION)

"""The mapping onto a STAC Collection.

Two things matter: the result is a valid STAC Collection, and it carries all eight
``earthx:`` fields of architekturplan.md 5.1 even where they are still empty.
"""

from __future__ import annotations

import pystac
import pytest

from earthx.catalog.collection import to_stac_collection
from earthx.catalog.datasets import SENTINEL_2_L2A

EARTHX_FIELDS = (
    "earthx:data_class",
    "earthx:capabilities",
    "earthx:license_flags",
    "earthx:access",
    "earthx:distributions",
    "earthx:health",
    "earthx:default_render",
    "earthx:source",
)


@pytest.fixture
def collection() -> dict:
    return to_stac_collection(SENTINEL_2_L2A)


@pytest.mark.parametrize("field", EARTHX_FIELDS)
def test_every_earthx_field_of_5_1_is_present(collection: dict, field: str) -> None:
    assert field in collection


def test_the_three_coverage_fields_of_adr_0004_are_present(collection: dict) -> None:
    coverage = collection["earthx:coverage"]
    assert coverage["provider"] == "upstream-aggregation"
    assert coverage["typical_footprint_km"] == 110.0
    assert coverage["max_geotile_level"] == 8


def test_the_result_is_a_valid_stac_collection(collection: dict) -> None:
    """Read back by pystac, so the shape is checked against the spec, not against us."""
    parsed = pystac.Collection.from_dict(collection)
    assert parsed.id == "sentinel-2-l2a"
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


def test_dates_are_written_as_utc_instants(collection: dict) -> None:
    assert collection["earthx:access"]["token_free_checked_at"] == "2026-09-18"
    assert collection["earthx:health"]["last_checked_ok"] == "2026-09-18"


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

    def test_changing_the_result_does_not_reach_the_entry(self) -> None:
        collection = to_stac_collection(SENTINEL_2_L2A)
        collection["earthx:default_render"]["bands"].append("nir")
        assert "nir" not in SENTINEL_2_L2A.default_render.bands

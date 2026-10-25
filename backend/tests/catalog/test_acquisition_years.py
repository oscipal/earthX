"""The years a scene was acquired in, which the attribution names (NM4-01).

The year of "Contains modified Copernicus Sentinel data [Year]" is read as the year of acquisition and
comes from the items, never from the clock. Everything here is synthetic.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from earthx.access.download import attribution_names_year, attribution_text, attribution_years
from earthx.catalog.datasets import REGISTRY
from earthx.catalog.registry import AcquisitionYearMissing, AcquisitionYears, acquisition_years

S2 = REGISTRY.get("sentinel-2-c1-l2a")
DEM = REGISTRY.get("cop-dem-glo-30")


def item(**properties: object) -> dict[str, object]:
    return {"id": "x", "properties": properties}


class TestAcquisitionYears:
    def test_a_scene_of_2025_is_2025(self) -> None:
        assert str(acquisition_years([item(datetime="2025-07-29T10:15:00Z")])) == "2025"

    def test_scenes_of_2024_and_2025_are_the_span(self) -> None:
        years = acquisition_years([item(datetime="2025-01-02T10:00:00Z"), item(datetime="2024-12-30T10:00:00Z")])
        assert (years.first, years.last) == (2024, 2025)
        assert str(years) == "2024\N{EN DASH}2025"

    def test_a_period_is_read_from_its_start_and_its_end(self) -> None:
        years = acquisition_years([item(start_datetime="2010-06-01T00:00:00Z", end_datetime="2015-01-01T00:00:00Z")])
        assert str(years) == "2010\N{EN DASH}2015"

    def test_the_year_is_the_utc_year_of_an_instant_with_an_offset(self) -> None:
        assert str(acquisition_years([item(datetime="2024-12-31T23:30:00-02:00")])) == "2025"
        assert str(acquisition_years([item(datetime="2025-01-01T00:30:00+02:00")])) == "2024"

    def test_an_instant_without_an_offset_is_read_as_utc(self) -> None:
        assert str(acquisition_years([item(datetime="2025-01-01T00:00:00")])) == "2025"

    def test_a_datetime_object_counts_as_well(self) -> None:
        assert str(acquisition_years([item(datetime=datetime(2025, 3, 1, tzinfo=UTC))])) == "2025"

    @pytest.mark.parametrize(
        "bad",
        [
            item(),
            item(datetime=None),
            item(datetime="yesterday"),
            item(datetime=20250729),
            item(datetime="2025-07-29T10:15:00Z", end_datetime="never"),
            {"id": "x"},
            {"id": "x", "properties": "not a mapping"},
        ],
        ids=["no property", "null", "no instant", "a number", "one bad of several", "no properties", "properties of text"],
    )
    def test_an_item_without_a_usable_date_is_refused_never_given_the_clock(self, bad: dict[str, object]) -> None:
        with pytest.raises(AcquisitionYearMissing):
            acquisition_years([item(datetime="2025-07-29T10:15:00Z"), bad])

    def test_no_items_are_no_years(self) -> None:
        with pytest.raises(AcquisitionYearMissing):
            acquisition_years([])

    def test_the_first_year_is_not_after_the_last(self) -> None:
        with pytest.raises(ValueError, match="first"):
            AcquisitionYears(2026, 2025)


class TestTheAttributionOfADataset:
    def test_the_year_of_the_scenes_goes_into_the_registrys_template(self) -> None:
        years = attribution_years(S2, [item(datetime="2025-07-29T10:15:00Z")])
        assert attribution_text(S2, years=years) == "Contains modified Copernicus Sentinel data 2025"

    def test_several_years_are_written_as_a_span(self) -> None:
        text = attribution_text(S2, years=AcquisitionYears(2024, 2025))
        assert text == "Contains modified Copernicus Sentinel data 2024\N{EN DASH}2025"

    def test_a_scene_without_a_date_is_refused_where_the_text_names_a_year(self) -> None:
        with pytest.raises(AcquisitionYearMissing):
            attribution_years(S2, [item()])

    def test_the_text_does_not_ask_the_clock_when_the_caller_gives_no_years(self) -> None:
        with pytest.raises(ValueError, match="years"):
            attribution_text(S2, years=None)

    def test_the_dem_has_a_fixed_wording_and_needs_neither_years_nor_dates(self) -> None:
        assert not attribution_names_year(DEM)
        assert attribution_names_year(S2)
        assert attribution_years(DEM, [item()]) is None
        text = attribution_text(DEM, years=None)
        assert text is not None and "2010-2014" in text and "2014-2018" in text
        # Given years, the fixed wording stays what the licence says (Art. 6 of the DEM licence).
        assert attribution_text(DEM, years=AcquisitionYears(2025, 2025)) == text

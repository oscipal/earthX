"""The MeteoSwiss units against a synthetic item list and synthetic files (M5-11 plan §5.10, M5-58 plan §11).

The list and every file are made here (`tests/earthx/readers/mini_netcdf.py` writes the files); a fake host answers
them behind a real :class:`~earthx.gateway.Gateway`. Nothing reaches a network. The decisions per unit and the writing
of items are the core's, tested against pgstac in `tests/integration/test_materialize_meteoswiss.py`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest

from earthx.adapters import UnsupportedSource, UpstreamShapeError
from earthx.catalog.registry import DatasetConfig, ItemState, SpatialExtent
from earthx.catalog.source_units import BuiltUnit, SourceUnit, UnitListing
from earthx.discovery import meteoswiss_grid
from earthx.discovery.materialize import MATERIALIZE_SPECS
from earthx.readers.reference_store import parse_references
from tests.catalog.entries import METEOSWISS_DAILY_1KM, METEOSWISS_DAILY_PRECIP_1KM
from tests.earthx.discovery.mini_archive import (
    ARCHIVE,
    HOST,
    LIST_PATH,
    Archive,
    annual_file,
    day_name,
    entry,
    materialized_items,
    month_name,
    name,
    netcdf_file,
)
from tests.earthx.readers import mini_netcdf

TEMPERATURE = entry(METEOSWISS_DAILY_1KM)
PRECIPITATION = entry(METEOSWISS_DAILY_PRECIP_1KM)
DAY = date(2026, 11, 16)


def listing(archive: Archive, config: DatasetConfig, known: Mapping[str, str | None] | None = None) -> UnitListing:
    async def go() -> UnitListing:
        async with archive.gateway() as gateway:
            return await meteoswiss_grid.list_units(config, gateway=gateway, known_groups=known or {})

    return asyncio.run(go())


def build(archive: Archive, config: DatasetConfig, units: Sequence[SourceUnit]) -> tuple[BuiltUnit, ...]:
    async def go() -> tuple[BuiltUnit, ...]:
        async with archive.gateway() as gateway:
            return await meteoswiss_grid.build_units(config, gateway=gateway, units=units)

    return asyncio.run(go())


def items(archive: Archive, config: DatasetConfig) -> dict[str, dict[str, Any]]:
    return {item["id"][-8:]: item for item in asyncio.run(materialized_items(archive, config))}


@pytest.fixture
def archive(tmp_path: Path) -> Archive:
    return Archive(
        {
            name("TabsD", "ch01r", 2023): annual_file(tmp_path, 2023),
            name("TabsD", "ch01r", 2024): annual_file(tmp_path, 2024),
            # A quantity that misses its second day.
            name("TminD", "ch01r", 2024): annual_file(tmp_path, 2024, days=[0, 2]),
            # Another grid, a quantity the entry does not name: passed over without a request.
            name("TabsD", "ch02r", 2024): b"x",
            name("TabsM", "ch01r", 2024): b"x",
        },
        items={
            "month": {
                month_name("TabsD", "ch01r", 2026, 10): netcdf_file(tmp_path, date(2026, 10, 1), [0, 1]),
                month_name("TabsM", "ch01r", 2026, 10): b"x",
            },
            "day": {
                day_name("TabsD", "ch01r", DAY): netcdf_file(tmp_path, DAY, [0]),
                day_name("RprelimD", "ch01h", DAY): netcdf_file(tmp_path, DAY, [0]),
            },
            # Monthly values and records only: no group.
            "records": {"ogd-surface-derived-grid-last.tabsm_ch01r.swiss.lv95_20261001000000_20261031000000.nc": b"x"},
        },
        expires={"day": "2027-01-16T00:00:00Z", "month": "2027-12-01T00:00:00Z"},
    )


class TestListing:
    def test_every_source_item_with_files_of_the_entry_is_a_group_with_its_files_and_their_state(self, archive: Archive) -> None:
        found = listing(archive, TEMPERATURE)
        assert set(found.groups) == {meteoswiss_grid.LIST_GROUP, ARCHIVE, "month", "day"}
        assert found.unchanged_groups == frozenset()
        states = {unit.key: (unit.group, unit.state) for unit in found.units}
        assert states == {
            name("TabsD", "ch01r", 2023): (ARCHIVE, ItemState.FINAL),
            name("TabsD", "ch01r", 2024): (ARCHIVE, ItemState.FINAL),
            name("TminD", "ch01r", 2024): (ARCHIVE, ItemState.FINAL),
            month_name("TabsD", "ch01r", 2026, 10): ("month", ItemState.FINAL),
            day_name("TabsD", "ch01r", DAY): ("day", ItemState.PROVISIONAL),
        }

    def test_a_file_names_its_checksum_and_update_from_the_list_and_the_expiry_of_its_item(self, archive: Archive) -> None:
        unit = next(unit for unit in listing(archive, TEMPERATURE).units if unit.group == "day")
        assert unit.validators.checksum and unit.validators.last_modified == "2025-02-12T08:00:00Z"
        assert unit.validators.etag is None
        assert unit.expires == "2027-01-16T00:00:00Z"
        assert unit.href == f"https://{HOST}/files/{day_name('TabsD', 'ch01r', DAY)}"

    def test_the_list_is_one_request_and_no_file_is_read(self, archive: Archive) -> None:
        listing(archive, TEMPERATURE)
        assert [request.url.path for request in archive.seen] == [LIST_PATH]
        assert archive.seen[0].url.params["limit"] == "100"

    def test_the_provisional_precipitation_is_the_band_rhiresd_on_its_own_grid(self, archive: Archive) -> None:
        found = listing(archive, PRECIPITATION)
        assert [unit.key for unit in found.units] == [day_name("RprelimD", "ch01h", DAY)]
        assert found.units[0].state is ItemState.PROVISIONAL
        file = meteoswiss_grid.parse_name(PRECIPITATION, found.units[0].key)
        assert file is not None and (file.asset_key, file.product) == ("RhiresD", "RprelimD")

    def test_rprelimd_outside_a_day_item_is_no_file_of_the_entry(self) -> None:
        archived = "ogd-surface-derived-grid-archive.rprelimd_ch01h.swiss.lv95_20250101000000_20251231235959.nc"
        assert meteoswiss_grid.parse_name(PRECIPITATION, archived) is None
        assert meteoswiss_grid.parse_name(TEMPERATURE, day_name("RprelimD", "ch01h", DAY)) is None

    def test_the_same_list_is_unchanged_after_one_request(self, archive: Archive) -> None:
        first = listing(archive, TEMPERATURE)
        archive.seen.clear()
        again = listing(archive, TEMPERATURE, known=first.groups)
        assert again.units == () and again.unchanged_groups == frozenset(first.groups)
        assert len(archive.seen) == 1

    def test_a_new_day_item_lists_only_its_files(self, archive: Archive, tmp_path: Path) -> None:
        first = listing(archive, TEMPERATURE)
        later = date(2026, 11, 17)
        archive.items["day-2"] = {day_name("TabsD", "ch01r", later): netcdf_file(tmp_path, later, [0])}
        again = listing(archive, TEMPERATURE, known=first.groups)
        assert again.unchanged_groups == {ARCHIVE, "month", "day"}
        assert [unit.key for unit in again.units] == [day_name("TabsD", "ch01r", later)]

    def test_a_group_without_validator_is_listed_again_although_the_list_is_the_same(self, archive: Archive) -> None:
        """M5-58 F10: the group of a file the source did not serve keeps no validator, so the next run asks for it."""
        first = listing(archive, TEMPERATURE)
        again = listing(archive, TEMPERATURE, known={**first.groups, "day": None})
        assert again.unchanged_groups == {ARCHIVE, "month"}
        assert [unit.key for unit in again.units] == [day_name("TabsD", "ch01r", DAY)]

    def test_another_selection_lists_every_file_again(self, archive: Archive) -> None:
        first = listing(archive, TEMPERATURE)
        fewer = replace(TEMPERATURE, band_units={"TabsD": "°C"}, band_descriptions={"TabsD": "Daily mean"})
        again = listing(archive, fewer, known=first.groups)
        assert again.unchanged_groups == frozenset() and len(again.units) == 4

    def test_archive_years_before_the_entry_starts_are_left_out(self, archive: Archive) -> None:
        config = replace(TEMPERATURE, temporal_extent=replace(TEMPERATURE.temporal_extent, start=TEMPERATURE.temporal_extent.start.replace(year=2024)))
        keys = {unit.key for unit in listing(archive, config).units if unit.group == ARCHIVE}
        assert keys == {name("TabsD", "ch01r", 2024), name("TminD", "ch01r", 2024)}

    def test_a_file_that_is_no_year_or_lies_on_another_host_is_passed_over(self, archive: Archive) -> None:
        archive.files[name("TabsD", "ch01r", 2022, end="0630235959")] = b"x"
        archive.hrefs[name("TminD", "ch01r", 2024)] = "https://elsewhere.example.invalid/tmind.nc"
        keys = {unit.key for unit in listing(archive, TEMPERATURE).units}
        assert name("TminD", "ch01r", 2024) not in keys and not any("2022" in key for key in keys)
        assert all(request.headers["host"] == HOST for request in archive.seen)

    def test_the_pages_of_the_list_are_followed(self, archive: Archive, tmp_path: Path) -> None:
        later = date(2026, 11, 18)
        archive.pages.append(
            [archive.feature("page-2", {day_name("TabsD", "ch01r", later): netcdf_file(tmp_path, later, [0])})]
        )
        found = listing(archive, TEMPERATURE)
        assert "page-2" in found.groups and len(archive.seen) == 2


class TestListingRefused:
    def test_two_files_of_one_quantity_and_year(self, archive: Archive, tmp_path: Path) -> None:
        other = name("TabsD", "ch01r", 2023, end="0101000000").replace("_20230101000000.nc", "_20240101000000.nc")
        archive.files[other] = annual_file(tmp_path, 2023)
        with pytest.raises(UpstreamShapeError, match="two files of TabsD for 2023"):
            listing(archive, TEMPERATURE)

    def test_two_files_of_one_quantity_in_a_day_item(self, archive: Archive, tmp_path: Path) -> None:
        archive.items["day"]["ogd-surface-derived-grid.tabsd_ch01r.swiss.lv95_20261116000000_20261116235959.nc"] = b"x"
        with pytest.raises(UpstreamShapeError, match="two files of TabsD"):
            listing(archive, TEMPERATURE)

    def test_a_list_without_a_file_of_the_entry(self, tmp_path: Path) -> None:
        with pytest.raises(UpstreamShapeError, match="no file of TabsD"):
            listing(Archive({name("RhiresD", "ch01h", 2024): annual_file(tmp_path, 2024)}), TEMPERATURE)

    def test_an_answer_that_is_no_item_collection(self, archive: Archive) -> None:
        archive.handler = lambda request: httpx.Response(200, json={"type": "Feature"})  # type: ignore[method-assign]
        with pytest.raises(UpstreamShapeError, match="no STAC item collection"):
            listing(archive, TEMPERATURE)

    def test_a_list_without_end(self, archive: Archive) -> None:
        archive.pages.extend([[]] * meteoswiss_grid._MAX_PAGES)
        with pytest.raises(UpstreamShapeError, match="over 20 pages"):
            listing(archive, TEMPERATURE)

    def test_a_quantity_meteoswiss_has_no_daily_grid_of(self, archive: Archive) -> None:
        config = replace(
            TEMPERATURE,
            band_units={"TabsD": "°C", "TabsM": "°C"},
            band_descriptions={"TabsD": "Daily mean air temperature, 2 m", "TabsM": "Monthly mean air temperature, 2 m"},
        )
        with pytest.raises(UnsupportedSource, match="TabsM"):
            listing(archive, config)
        assert archive.seen == []

    def test_quantities_of_two_grids_in_one_entry(self, archive: Archive) -> None:
        config = replace(
            TEMPERATURE,
            band_units={"TabsD": "°C", "RhiresD": "mm"},
            band_descriptions={"TabsD": "Daily mean air temperature, 2 m", "RhiresD": "Daily precipitation sum"},
        )
        with pytest.raises(UnsupportedSource, match="different grids"):
            listing(archive, config)


class TestBuilt:
    def test_one_item_per_day_with_an_asset_per_quantity_that_has_it(self, archive: Archive) -> None:
        by_day = items(archive, TEMPERATURE)
        assert sorted(by_day) == [
            "20230101", "20230102", "20230103", "20240101", "20240102", "20240103", "20261001", "20261002", "20261116"
        ]
        assert set(by_day["20240101"]["assets"]) == {"TabsD", "TminD"}
        # A day the file of TminD does not carry is no asset, not a failure (M5-11 plan §10.9).
        assert set(by_day["20240102"]["assets"]) == {"TabsD"}

    def test_only_the_listed_files_of_the_entry_are_read(self, archive: Archive) -> None:
        items(archive, TEMPERATURE)
        assert archive.files_read() == {
            name("TabsD", "ch01r", 2023),
            name("TabsD", "ch01r", 2024),
            name("TminD", "ch01r", 2024),
            month_name("TabsD", "ch01r", 2026, 10),
            day_name("TabsD", "ch01r", DAY),
        }

    def test_a_temperature_day_lasts_from_midnight_to_midnight_utc_provisional_or_not(self, archive: Archive) -> None:
        by_day = items(archive, TEMPERATURE)
        for day, stamp in (("20230101", "2023-01-01"), ("20261116", "2026-11-16")):
            properties = by_day[day]["properties"]
            assert properties["datetime"] == properties["start_datetime"] == f"{stamp}T00:00:00Z"
            assert properties["end_datetime"] == f"{stamp}T23:59:59Z"

    def test_a_provisional_precipitation_day_lasts_from_six_to_six_utc_as_rhiresd(self, archive: Archive) -> None:
        item = items(archive, PRECIPITATION)["20261116"]
        assert item["id"] == "meteoswiss-daily-precip-1km-20261116"
        assert item["properties"]["start_datetime"] == "2026-11-16T06:00:00Z"
        assert item["properties"]["end_datetime"] == "2026-11-17T05:59:59Z"
        asset = item["assets"]["RhiresD"]
        assert asset["earthx:source_product"] == "RprelimD" and asset["raster:bands"][0]["unit"] == "mm"
        assert item["properties"]["earthx:state"] == "provisional"

    def test_an_asset_carries_references_the_readers_take_its_update_and_expiry(self, archive: Archive) -> None:
        item = items(archive, TEMPERATURE)["20261116"]
        asset = item["assets"]["TabsD"]
        assert asset["href"] == f"https://{HOST}/files/{day_name('TabsD', 'ch01r', DAY)}"
        assert asset["type"] == "application/x-netcdf"
        assert asset["raster:bands"] == [{"data_type": "float32", "nodata": "nan", "unit": "°C"}]
        refs = parse_references(asset["earthx:refs"], asset["href"])
        assert refs.time_offset == 0 and len(refs.chunk_refs) == 1
        assert asset["earthx:refs"]["etag"] == mini_netcdf.Source(archive.items["day"][day_name("TabsD", "ch01r", DAY)]).etag
        assert asset["updated"] == "2025-02-12T08:00:00Z" and asset["expires"] == "2027-01-16T00:00:00Z"
        assert "earthx:source_product" not in asset
        assert item["properties"]["expires"] == "2027-01-16T00:00:00Z"

    def test_an_archive_day_has_no_expiry_and_is_final(self, archive: Archive) -> None:
        item = items(archive, TEMPERATURE)["20230101"]
        assert "expires" not in item["assets"]["TabsD"] and "expires" not in item["properties"]
        assert item["properties"]["earthx:state"] == "final"

    def test_every_item_lies_on_the_grid_of_the_files(self, archive: Archive) -> None:
        by_day = items(archive, TEMPERATURE)
        assert len({str(item["geometry"]) for item in by_day.values()}) == 1
        properties = by_day["20230101"]["properties"]
        assert properties["proj:code"] == "EPSG:2056" and properties["gsd"] == mini_netcdf.CELL
        west, south, east, north = by_day["20230101"]["bbox"]
        assert 7.4 < west < east < 8.0 and 46.3 < south < north < 46.8

    def test_a_listed_file_that_is_not_served_is_built_as_missing(self, archive: Archive) -> None:
        """M5-58 F10 = 1: no failure of the run; the core takes it as not listed and asks again next run."""
        units = listing(archive, TEMPERATURE).units
        archive.gone.add(day_name("TabsD", "ch01r", DAY))
        built = {made.key: made for made in build(archive, TEMPERATURE, units)}
        lost = built[day_name("TabsD", "ch01r", DAY)]
        assert lost.missing and lost.contributions == ()
        assert not any(made.missing for key, made in built.items() if key != lost.key)

    def test_the_dispatch_of_discovery_reaches_it(self) -> None:
        units = MATERIALIZE_SPECS[TEMPERATURE.source.adapter].units
        assert units is not None
        assert (units.list_units, units.build) == (meteoswiss_grid.list_units, meteoswiss_grid.build_units)


class TestBuildRefused:
    def refuse(self, archive: Archive, config: DatasetConfig = TEMPERATURE) -> None:
        build(archive, config, listing(archive, config).units)

    def test_a_time_step_off_midnight(self, archive: Archive, tmp_path: Path) -> None:
        archive.files[name("TabsD", "ch01r", 2023)] = annual_file(tmp_path, 2023, days=[0.25, 1.25])  # type: ignore[list-item]
        with pytest.raises(UpstreamShapeError, match="annual file of TabsD from 20230101.*midnight"):
            self.refuse(archive)

    def test_a_day_of_another_year_in_an_annual_file(self, archive: Archive, tmp_path: Path) -> None:
        archive.files[name("TabsD", "ch01r", 2023)] = annual_file(tmp_path, 2023, days=[364, 365])
        with pytest.raises(UpstreamShapeError, match="another year"):
            self.refuse(archive)

    def test_two_months_in_a_month_file(self, archive: Archive, tmp_path: Path) -> None:
        archive.items["month"][month_name("TabsD", "ch01r", 2026, 10)] = netcdf_file(tmp_path, date(2026, 10, 31), [0, 1])
        with pytest.raises(UpstreamShapeError, match="monthly file of TabsD.*more than one month"):
            self.refuse(archive)

    def test_two_days_in_a_day_file(self, archive: Archive, tmp_path: Path) -> None:
        archive.items["day"][day_name("TabsD", "ch01r", DAY)] = netcdf_file(tmp_path, DAY, [0, 1])
        with pytest.raises(UpstreamShapeError, match="daily file of TabsD.*more than one day"):
            self.refuse(archive)

    def test_a_file_on_another_grid(self, archive: Archive, tmp_path: Path) -> None:
        data = mini_netcdf.values(steps=3, rows=mini_netcdf.ROWS + 1)
        path = mini_netcdf.build(tmp_path / "other.nc", data, chunks=(1, mini_netcdf.ROWS + 1, mini_netcdf.COLUMNS), time_units="days since 2024-01-01 00:00:00")
        archive.files[name("TminD", "ch01r", 2024)] = path.read_bytes()
        with pytest.raises(UpstreamShapeError, match="another grid"):
            self.refuse(archive)

    def test_a_layout_the_readers_would_not_read_names_quantity_and_date_not_the_address(
        self, archive: Archive, tmp_path: Path
    ) -> None:
        archive.files[name("TabsD", "ch01r", 2024)] = annual_file(tmp_path, 2024, fletcher32=True)
        with pytest.raises(UpstreamShapeError, match="TabsD from 20240101") as raised:
            self.refuse(archive)
        assert HOST not in str(raised.value) and "ogd-" not in str(raised.value)

    def test_a_grid_beyond_the_entrys_extent(self, archive: Archive) -> None:
        config = replace(TEMPERATURE, spatial_extent=SpatialExtent((5.4, 45.2, 7.5, 48.2)))
        with pytest.raises(UnsupportedSource, match="beyond spatial_extent"):
            self.refuse(archive, config)

    def test_a_unit_that_is_no_file_of_the_entry(self, archive: Archive) -> None:
        unit = listing(archive, TEMPERATURE).units[0]
        with pytest.raises(UpstreamShapeError, match="no file of the entry"):
            build(archive, TEMPERATURE, [replace(unit, key="something-else.nc")])

"""The MeteoSwiss materializer against a synthetic archive item and synthetic annual files (M5-11 plan §5.10).

The archive item and every file are made here (`tests/earthx/readers/mini_netcdf.py` writes the files); a fake host
answers them behind a real :class:`~earthx.gateway.Gateway`. Nothing reaches a network.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from earthx.adapters import MaterializeOutcome, UnsupportedSource, UpstreamShapeError, materialize_items
from earthx.catalog.registry import DatasetConfig, SpatialExtent
from earthx.discovery import meteoswiss_grid
from earthx.discovery.materialize import MATERIALIZE_SPECS
from earthx.readers.reference_store import parse_references
from tests.catalog.entries import METEOSWISS_DAILY_1KM, METEOSWISS_DAILY_PRECIP_1KM
from tests.earthx.discovery.mini_archive import HOST, ITEM_ETAG, TODAY, Archive, annual_file, entry, name
from tests.earthx.readers import mini_netcdf


def run(archive: Archive, config: DatasetConfig, known_version: str | None = None) -> MaterializeOutcome:
    async def go() -> MaterializeOutcome:
        async with archive.gateway() as gateway:
            return await meteoswiss_grid.materialize_items(
                config, gateway=gateway, known_version=known_version, today=TODAY
            )

    return asyncio.run(go())


@pytest.fixture
def archive(tmp_path: Path) -> Archive:
    return Archive(
        {
            name("TabsD", "ch01r", 2023): annual_file(tmp_path, 2023),
            name("TabsD", "ch01r", 2024): annual_file(tmp_path, 2024),
            # A quantity that starts later, and misses its second day.
            name("TminD", "ch01r", 2024): annual_file(tmp_path, 2024, days=[0, 2]),
            # The current year of the run: not completed, withheld.
            name("TabsD", "ch01r", 2025): annual_file(tmp_path, 2025),
            # Not the archive, another grid, a quantity the entry does not name: passed over without a request.
            "ogd-surface-derived-grid-last.tabsd_ch01r.swiss.lv95_20250101000000_20250531000000.nc": b"x",
            "ogd-surface-derived-grid-archive.rprelimd_ch01h.swiss.lv95_20260101000000_20260131000000.nc": b"x",
            name("TabsD", "ch02r", 2024): b"x",
            name("TabsM", "ch01r", 2024): b"x",
        }
    )


class TestLoaded:
    def test_one_item_per_day_with_an_asset_per_quantity_that_has_it(self, archive: Archive) -> None:
        outcome = run(archive, entry(METEOSWISS_DAILY_1KM))
        assert outcome.status == "loaded"
        ids = [item["id"] for item in outcome.items]
        assert ids == [f"meteoswiss-daily-1km-{year}010{day}" for year in (2023, 2024) for day in (1, 2, 3)]
        by_id = {item["id"]: item for item in outcome.items}
        assert set(by_id["meteoswiss-daily-1km-20230101"]["assets"]) == {"TabsD"}
        assert set(by_id["meteoswiss-daily-1km-20240101"]["assets"]) == {"TabsD", "TminD"}
        # A day the file of TminD does not carry is no asset, not a failure (plan §10.9).
        assert set(by_id["meteoswiss-daily-1km-20240102"]["assets"]) == {"TabsD"}
        assert (outcome.listed, outcome.in_bucket, outcome.missing, outcome.withheld, outcome.unknown) == (3, 3, 0, 1, 0)

    def test_only_the_chosen_annual_files_are_read(self, archive: Archive) -> None:
        run(archive, entry(METEOSWISS_DAILY_1KM))
        assert archive.files_read() == {
            name("TabsD", "ch01r", 2023),
            name("TabsD", "ch01r", 2024),
            name("TminD", "ch01r", 2024),
        }

    def test_a_temperature_day_lasts_from_midnight_to_midnight_utc(self, archive: Archive) -> None:
        item = run(archive, entry(METEOSWISS_DAILY_1KM)).items[0]
        assert item["properties"]["datetime"] == "2023-01-01T00:00:00Z"
        assert item["properties"]["start_datetime"] == "2023-01-01T00:00:00Z"
        assert item["properties"]["end_datetime"] == "2023-01-01T23:59:59Z"

    def test_a_precipitation_day_lasts_from_six_to_six_utc(self, tmp_path: Path) -> None:
        files = {name("RhiresD", "ch01h", 2024): annual_file(tmp_path, 2024)}
        item = run(Archive(files), entry(METEOSWISS_DAILY_PRECIP_1KM)).items[0]
        assert item["id"] == "meteoswiss-daily-precip-1km-20240101"
        assert item["properties"]["start_datetime"] == "2024-01-01T06:00:00Z"
        assert item["properties"]["end_datetime"] == "2024-01-02T05:59:59Z"
        assert item["properties"]["datetime"] == "2024-01-01T06:00:00Z"
        assert item["assets"]["RhiresD"]["raster:bands"][0]["unit"] == "mm"

    def test_an_asset_carries_references_the_readers_take_and_its_type_and_unit(self, archive: Archive) -> None:
        item = run(archive, entry(METEOSWISS_DAILY_1KM)).items[1]
        asset = item["assets"]["TabsD"]
        assert asset["href"] == f"https://{HOST}/files/{name('TabsD', 'ch01r', 2023)}"
        assert asset["type"] == "application/x-netcdf"
        assert asset["raster:bands"] == [{"data_type": "float32", "nodata": "nan", "unit": "°C"}]
        refs = parse_references(asset["earthx:refs"], asset["href"])
        assert refs.time_offset == 0 and len(refs.chunk_refs) == 1
        assert asset["earthx:refs"]["etag"] == mini_netcdf.Source(archive.files[name("TabsD", "ch01r", 2023)]).etag

    def test_the_item_says_when_its_files_were_updated_and_where_its_grid_lies(self, archive: Archive) -> None:
        items = run(archive, entry(METEOSWISS_DAILY_1KM)).items
        properties = items[0]["properties"]
        assert properties["updated"] == "2025-02-12T08:00:00Z"
        assert properties["proj:code"] == "EPSG:2056" and properties["gsd"] == mini_netcdf.CELL
        assert len({str(item["geometry"]) for item in items}) == 1
        west, south, east, north = items[0]["bbox"]
        assert 7.4 < west < east < 8.0 and 46.3 < south < north < 46.8

    def test_the_end_of_temporal_extent_withholds_later_years(self, archive: Archive) -> None:
        config = entry(METEOSWISS_DAILY_1KM)
        config = replace(config, temporal_extent=replace(config.temporal_extent, end=config.temporal_extent.end.replace(year=2023)))
        outcome = run(archive, config)
        assert {item["id"][-8:-4] for item in outcome.items} == {"2023"}
        assert outcome.withheld == 3

    def test_the_dispatch_of_discovery_reaches_it(self, archive: Archive) -> None:
        async def go() -> MaterializeOutcome:
            async with archive.gateway() as gateway:
                return await materialize_items(
                    entry(METEOSWISS_DAILY_1KM), adapters=MATERIALIZE_SPECS, gateway=gateway, known_version=None
                )

        assert asyncio.run(go()).status == "loaded"


class TestUnchanged:
    def test_a_304_on_the_archive_item_is_one_request(self, archive: Archive) -> None:
        first = run(archive, entry(METEOSWISS_DAILY_1KM))
        archive.seen.clear()
        again = run(archive, entry(METEOSWISS_DAILY_1KM), known_version=first.source_version)
        assert again.status == "unchanged" and again.source_version == first.source_version
        assert len(archive.seen) == 1 and archive.seen[0].headers["if-none-match"] == ITEM_ETAG

    def test_a_new_etag_with_the_same_chosen_files_reads_no_file(self, archive: Archive, tmp_path: Path) -> None:
        first = run(archive, entry(METEOSWISS_DAILY_1KM))
        known = '"archive-0"' + first.source_version[len(ITEM_ETAG):]
        # Another file of the archive changed, none of the chosen ones.
        archive.files[name("TabsD", "ch01r", 2025)] = annual_file(tmp_path, 2025, days=[0])
        archive.seen.clear()
        again = run(archive, entry(METEOSWISS_DAILY_1KM), known_version=known)
        assert again.status == "unchanged" and again.source_version == first.source_version
        assert archive.files_read() == set()

    def test_a_changed_chosen_file_loads_anew(self, archive: Archive, tmp_path: Path) -> None:
        first = run(archive, entry(METEOSWISS_DAILY_1KM))
        known = '"archive-0"' + first.source_version[len(ITEM_ETAG):]
        archive.files[name("TabsD", "ch01r", 2023)] = annual_file(tmp_path, 2023, days=[0, 1])
        assert run(archive, entry(METEOSWISS_DAILY_1KM), known_version=known).status == "loaded"

    def test_a_longer_period_is_loaded_although_the_archive_answers_304(self, archive: Archive) -> None:
        config = entry(METEOSWISS_DAILY_1KM)
        earlier = replace(config, temporal_extent=replace(config.temporal_extent, end=config.temporal_extent.end.replace(year=2023)))
        first = run(archive, earlier)
        archive.seen.clear()
        again = run(archive, config, known_version=first.source_version)
        assert "if-none-match" not in archive.seen[0].headers
        assert again.status == "loaded" and {item["id"][-8:-4] for item in again.items} == {"2023", "2024"}

    def test_a_version_of_another_form_is_not_trusted(self, archive: Archive) -> None:
        assert run(archive, entry(METEOSWISS_DAILY_1KM), known_version="sha256:abc").status == "loaded"


class TestRefused:
    def test_a_time_step_off_midnight(self, archive: Archive, tmp_path: Path) -> None:
        archive.files[name("TabsD", "ch01r", 2023)] = annual_file(tmp_path, 2023, days=[0.25, 1.25])  # type: ignore[list-item]
        with pytest.raises(UpstreamShapeError, match="TabsD for 2023.*midnight"):
            run(archive, entry(METEOSWISS_DAILY_1KM))

    def test_a_time_step_in_another_year(self, archive: Archive, tmp_path: Path) -> None:
        archive.files[name("TabsD", "ch01r", 2023)] = annual_file(tmp_path, 2023, days=[364, 365])
        with pytest.raises(UpstreamShapeError, match="midnight UTC of a day of 2023"):
            run(archive, entry(METEOSWISS_DAILY_1KM))

    def test_a_file_on_another_grid(self, archive: Archive, tmp_path: Path) -> None:
        data = mini_netcdf.values(steps=3, rows=mini_netcdf.ROWS + 1)
        path = mini_netcdf.build(tmp_path / "other.nc", data, chunks=(1, mini_netcdf.ROWS + 1, mini_netcdf.COLUMNS), time_units="days since 2024-01-01 00:00:00")
        archive.files[name("TminD", "ch01r", 2024)] = path.read_bytes()
        with pytest.raises(UpstreamShapeError, match="another grid"):
            run(archive, entry(METEOSWISS_DAILY_1KM))

    def test_a_layout_the_readers_would_not_read_names_quantity_and_year_not_the_address(
        self, archive: Archive, tmp_path: Path
    ) -> None:
        archive.files[name("TabsD", "ch01r", 2024)] = annual_file(tmp_path, 2024, fletcher32=True)
        with pytest.raises(UpstreamShapeError, match="TabsD for 2024") as raised:
            run(archive, entry(METEOSWISS_DAILY_1KM))
        assert HOST not in str(raised.value)

    def test_two_files_of_one_quantity_and_year(self, archive: Archive, tmp_path: Path) -> None:
        archive.files[name("TabsD", "ch01r", 2023, end="0101000000").replace("_20230101000000.nc", "_20240101000000.nc")] = annual_file(tmp_path, 2023)
        with pytest.raises(UpstreamShapeError, match="two files of TabsD for 2023"):
            run(archive, entry(METEOSWISS_DAILY_1KM))

    def test_a_grid_beyond_the_entrys_extent(self, archive: Archive) -> None:
        config = replace(entry(METEOSWISS_DAILY_1KM), spatial_extent=SpatialExtent((5.4, 45.2, 7.5, 48.2)))
        with pytest.raises(UnsupportedSource, match="beyond spatial_extent"):
            run(archive, config)

    def test_a_quantity_meteoswiss_has_no_daily_grid_of(self, archive: Archive) -> None:
        config = replace(
            entry(METEOSWISS_DAILY_1KM),
            band_units={"TabsD": "°C", "TabsM": "°C"},
            band_descriptions={"TabsD": "Daily mean air temperature, 2 m", "TabsM": "Monthly mean air temperature, 2 m"},
        )
        with pytest.raises(UnsupportedSource, match="TabsM"):
            run(archive, config)
        assert archive.seen == []

    def test_quantities_of_two_grids_in_one_entry(self, archive: Archive) -> None:
        config = replace(
            entry(METEOSWISS_DAILY_1KM),
            band_units={"TabsD": "°C", "RhiresD": "mm"},
            band_descriptions={"TabsD": "Daily mean air temperature, 2 m", "RhiresD": "Daily precipitation sum"},
        )
        with pytest.raises(UnsupportedSource, match="different grids"):
            run(archive, config)

    def test_an_archive_without_a_file_of_the_entry(self, tmp_path: Path) -> None:
        with pytest.raises(UpstreamShapeError, match="no annual file"):
            run(Archive({name("RhiresD", "ch01h", 2024): annual_file(tmp_path, 2024)}), entry(METEOSWISS_DAILY_1KM))

    def test_more_than_one_percent_of_the_files_gone(self, archive: Archive) -> None:
        archive.gone.add(name("TabsD", "ch01r", 2023))
        with pytest.raises(UpstreamShapeError, match="1% abort"):
            run(archive, entry(METEOSWISS_DAILY_1KM))

    def test_a_file_on_a_host_outside_the_entry_is_unknown_and_never_asked(self, archive: Archive) -> None:
        archive.hrefs[name("TminD", "ch01r", 2024)] = "https://elsewhere.example.invalid/tmind.nc"
        outcome = run(archive, entry(METEOSWISS_DAILY_1KM))
        assert outcome.unknown == 1
        assert all(request.headers["host"] == HOST for request in archive.seen)
        assert all(set(item["assets"]) == {"TabsD"} for item in outcome.items)

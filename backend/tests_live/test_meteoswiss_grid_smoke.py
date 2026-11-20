"""T-D: is the item list of the MeteoSwiss climate grids still the source both entries describe? (M5-11 plan §5.10,
M5-58 plan §11)

Runs on the schedule of the live smokes in GitHub Actions, never in a pull request and never in a cloud session. Small
on purpose (adr/0005 §3.6): the item list once per entry, and the header of the newest file of each kind (archive, month,
day) of each entry's default quantity (5–8 ranged requests each, no data). The materialization itself is Otto's local
run.

It checks what the entries and the adapter assume (M5-11 plan §10.7, §10.9; M5-58 plan §11.1, §11.2): every quantity
of an entry has annual files without a gap up to at most two years back, final files of one month and provisional
files of one day; the newest file of each kind lies in LV95, is Float32 without filter, one chunk a day, each day
stamped at 00:00 UTC and as many days as its kind promises (the checks of ``build_units``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx
import pytest

from earthx.catalog.datasets import registry
from earthx.catalog.registry import ItemState
from earthx.catalog.source_units import SourceUnit
from earthx.discovery import meteoswiss_grid
from earthx.gateway import Policy
from earthx.gateway.client import Gateway

ENTRIES = [registry().get("meteoswiss-daily-1km"), registry().get("meteoswiss-daily-precip-1km")]

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.live_dataset("meteoswiss-daily-1km"),
    pytest.mark.live_dataset("meteoswiss-daily-precip-1km"),
]


@asynccontextmanager
async def open_gateway() -> AsyncIterator[Gateway]:
    hosts = {httpx.URL(entry.source.endpoint).host for entry in ENTRIES} | {
        host for entry in ENTRIES for host in entry.source.asset_hosts
    }
    async with Gateway(Policy(allowed_hosts=frozenset(hosts))) as gateway:
        yield gateway


@pytest.fixture
async def gateway() -> AsyncIterator[Gateway]:
    async with open_gateway() as gateway:
        yield gateway


async def test_every_quantity_has_annual_month_and_day_files(gateway: Gateway) -> None:
    """Both entries in one test: the replay of the smokes hands a test the gateway and nothing else."""
    for entry in ENTRIES:
        units = (await meteoswiss_grid.list_units(entry, gateway=gateway, known_groups={})).units
        parsed = [(unit, file) for unit in units if (file := meteoswiss_grid.parse_name(entry, unit.key)) is not None]
        for quantity in entry.band_units:
            mine = [(unit, file) for unit, file in parsed if file.asset_key == quantity]
            years = sorted(file.year for _, file in mine if file.year is not None)
            assert years, f"the list holds no annual file of {quantity}"
            assert years == list(range(years[0], years[-1] + 1)), f"the annual files of {quantity} skip a year"
            assert years[-1] >= datetime.now(UTC).year - 2, f"the newest annual file of {quantity} is of {years[-1]}"
            kinds = {(file.kind, unit.state) for unit, file in mine}
            assert ("-last", ItemState.FINAL) in kinds, f"the list holds no month file of {quantity}"
            assert ("", ItemState.PROVISIONAL) in kinds, f"the list holds no provisional day file of {quantity}"


async def test_the_newest_file_of_each_kind_is_laid_out_as_the_items_assume(gateway: Gateway) -> None:
    for entry in ENTRIES:
        quantity = entry.default_render.assets[0] if entry.default_render is not None else next(iter(entry.band_units))
        units = (await meteoswiss_grid.list_units(entry, gateway=gateway, known_groups={})).units
        newest: dict[str, SourceUnit] = {}
        for unit in sorted(units, key=lambda unit: unit.key):
            file = meteoswiss_grid.parse_name(entry, unit.key)
            if file is not None and file.asset_key == quantity:
                newest[file.kind] = unit
        assert set(newest) == {"-archive", "-last", ""}, f"{entry.dataset_id}: not every kind of file is listed"
        # `build_units` refuses another CRS or grid, a step off midnight and more days than the kind of file holds.
        built = await meteoswiss_grid.build_units(entry, gateway=gateway, units=list(newest.values()))
        for made in built:
            asset = made.contributions[0].asset
            refs = asset["earthx:refs"]
            assert asset["raster:bands"][0]["data_type"] == "float32", entry.dataset_id
            assert refs["filters"] == [], entry.dataset_id
            assert refs["chunks"][0] == 1, f"{entry.dataset_id}: a chunk holds more than one day"

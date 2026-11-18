"""T-D: is the archive of the MeteoSwiss climate grids still the source both entries describe? (M5-11 plan §5.10)

Runs on the schedule of the live smokes in GitHub Actions, never in a pull request and never in a cloud session. Small
on purpose (adr/0005 §3.6): the archive item once, and the header of the newest annual file of each entry's default
quantity (5–8 ranged requests each, no data). The materialization itself reads all 295 files and is Otto's local run.

It checks what the entries and the materialization assume (plan §10.7, §10.9): every quantity of an entry has annual
files up to the last year of ``temporal_extent``, and no completed year beyond it (a new year is followed up in review
first); the newest file lies in LV95, is Float32 without filter, one chunk a day, each day stamped at 00:00 UTC.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, time

import httpx
import pytest

from earthx.catalog.datasets import registry
from earthx.catalog.registry import DatasetConfig
from earthx.discovery import meteoswiss_grid
from earthx.discovery.netcdf_refs import reference_file
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


async def _files(gateway: Gateway, entry: DatasetConfig):
    assets = (await gateway.get(entry.source.endpoint)).json()["assets"]
    chosen, withheld, unknown = meteoswiss_grid.choose_files(entry, assets, first_year=1800, last_year=2999)
    return chosen, unknown


async def test_every_quantity_has_its_annual_files_up_to_the_entrys_end(gateway: Gateway) -> None:
    """Both entries in one test: the replay of the smokes hands a test the gateway and nothing else."""
    for entry in ENTRIES:
        chosen, unknown = await _files(gateway, entry)
        assert unknown == 0, f"{entry.dataset_id}: {unknown} archive files of its quantities are not one year on an asset host"
        for quantity in entry.band_units:
            years = sorted(year for name, year in chosen if name == quantity)
            assert years, f"the archive lists no annual file of {quantity}"
            assert years[-1] == meteoswiss_grid.last_year_of(entry), (
                f"the newest annual file of {quantity} is of {years[-1]}; follow temporal_extent of {entry.dataset_id} up"
            )
            assert years == list(range(years[0], years[-1] + 1)), f"the annual files of {quantity} skip a year"


async def test_the_newest_file_is_laid_out_as_the_items_assume(gateway: Gateway) -> None:
    for entry in ENTRIES:
        chosen, _ = await _files(gateway, entry)
        quantity = entry.default_render.assets[0] if entry.default_render is not None else next(iter(entry.band_units))
        file = chosen[(quantity, meteoswiss_grid.last_year_of(entry))]
        references = await reference_file(gateway, file.href)
        layout = references.layout
        assert layout.crs == meteoswiss_grid.CRS, entry.dataset_id
        assert layout.dtype == "<f4", entry.dataset_id
        assert layout.filters == (), entry.dataset_id
        assert layout.chunks[0] == 1, f"{entry.dataset_id}: a chunk holds more than one day"
        assert all(instant.timetz() == time(0, tzinfo=UTC) for instant in references.times), "a day is not at 00:00 UTC"
        assert references.last_modified, "the file names no Last-Modified, which the items carry as updated"

"""A synthetic item list of the MeteoSwiss climate grids and its files behind one fake host (M5-11, M5-58 PR 2).

The list holds the archive item ``archive-ch`` with annual files and, where a test adds them, items of one month
(``-last``) and of one day (preliminary), as the probe found them (M5-58 plan §11.1). The files are written by
`tests/earthx/readers/mini_netcdf.py`; the host answers the list like the FSDI (one page, no ETag) and each file like
the measured source (``206`` on a range, ETag, ``If-Match``, ``304`` on ``If-None-Match``). Nothing of any real source
is in them.
"""

from __future__ import annotations

import calendar
import hashlib
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import numpy

from earthx.catalog.registry import DatasetConfig
from earthx.catalog.source_units import Contribution
from earthx.discovery.materialize import MATERIALIZE_SPECS
from earthx.discovery.materialize_units import assemble_item
from earthx.gateway import Gateway, Policy
from tests.earthx.readers import mini_netcdf

HOST = mini_netcdf.HOST
LIST_PATH = "/api/stac/v1/collections/ch.meteoschweiz.ogd-surface-derived-grid/items"
ENDPOINT = f"https://{HOST}{LIST_PATH}"
ARCHIVE = "archive-ch"
#: What the list names as `updated` of a file unless a test says otherwise; the files answer with the same instant.
UPDATED = "2025-02-12T08:00:00Z"


def entry(config: DatasetConfig) -> DatasetConfig:
    return replace(config, source=replace(config.source, endpoint=ENDPOINT, asset_hosts=(HOST,)))


def name(quantity: str, grid: str, year: int, end: str = "1231235959") -> str:
    """An annual file of the archive."""
    return f"ogd-surface-derived-grid-archive.{quantity.lower()}_{grid}.swiss.lv95_{year}0101000000_{year}{end}.nc"


def month_name(quantity: str, grid: str, year: int, month: int) -> str:
    """The file of one month with daily values in an item ``CH at MM.YYYY``."""
    last = calendar.monthrange(year, month)[1]
    return f"ogd-surface-derived-grid-last.{quantity.lower()}_{grid}.swiss.lv95_{year}{month:02}01000000_{year}{month:02}{last}000000.nc"


def day_name(quantity: str, grid: str, day: date) -> str:
    """The preliminary file of one day in an item ``CH at DD.MM.YYYY``."""
    stamp = day.strftime("%Y%m%d")
    return f"ogd-surface-derived-grid.{quantity.lower()}_{grid}.swiss.lv95_{stamp}000000_{stamp}000000.nc"


def netcdf_file(tmp_path: Path, first: date, days: list[int], *, seed: int = 0, **options: Any) -> bytes:
    """A file of ``days`` (offsets from ``first``), each stamped at 00:00 UTC; another ``seed`` gives other values."""
    data = mini_netcdf.values(steps=len(days), seed=first.toordinal() % 1000 + len(days) + seed)
    path = tmp_path / f"{first.isoformat()}-{len(list(tmp_path.iterdir()))}.nc"
    return mini_netcdf.build(
        path,
        data,
        time_units=f"days since {first.isoformat()} 00:00:00",
        time_values=numpy.asarray(days, dtype="f8"),
        **options,
    ).read_bytes()


def annual_file(tmp_path: Path, year: int, days: list[int] | None = None, **options: Any) -> bytes:
    return netcdf_file(tmp_path, date(year, 1, 1), [0, 1, 2] if days is None else days, **options)


@dataclass
class Archive:
    """The item list and its files behind one fake host, answering like the FSDI (adr/0029 §4, M5-58 plan §11.1).

    ``files`` are those of the archive item; ``items`` the other source items by id, each with its files.
    """

    files: dict[str, bytes]
    items: dict[str, dict[str, bytes]] = field(default_factory=dict)
    expires: dict[str, str] = field(default_factory=dict)
    updated: dict[str, str] = field(default_factory=dict)
    hrefs: dict[str, str] = field(default_factory=dict)
    gone: set[str] = field(default_factory=set)
    #: Further pages of the list, each a list of features; the first page links the next.
    pages: list[list[dict[str, Any]]] = field(default_factory=list)
    seen: list[httpx.Request] = field(default_factory=list)

    def all_files(self) -> dict[str, bytes]:
        return {key: body for files in [self.files, *self.items.values()] for key, body in files.items()}

    def feature(self, item_id: str, files: dict[str, bytes]) -> dict[str, Any]:
        properties = {"datetime": None, **({"expires": self.expires[item_id]} if item_id in self.expires else {})}
        return {
            "type": "Feature",
            "id": item_id,
            "properties": properties,
            "assets": {
                key: {
                    "href": self.hrefs.get(key, f"https://{HOST}/files/{key}"),
                    "file:checksum": hashlib.md5(body).hexdigest(),  # noqa: S324 — a fake checksum
                    "updated": self.updated.get(key, UPDATED),
                }
                for key, body in files.items()
            },
        }

    def page(self, number: int) -> dict[str, Any]:
        if number == 0:
            features = [self.feature(ARCHIVE, self.files)]
            features += [self.feature(item_id, files) for item_id, files in self.items.items()]
        else:
            features = self.pages[number - 1]
        links = [{"rel": "next", "href": f"{ENDPOINT}?page={number + 1}"}] if number < len(self.pages) else []
        return {"type": "FeatureCollection", "features": features, "links": links}

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        if request.url.path == LIST_PATH:
            return httpx.Response(200, json=self.page(int(request.url.params.get("page", 0))))
        key = request.url.path.removeprefix("/files/")
        files = self.all_files()
        if key in self.gone or key not in files:
            return httpx.Response(404)
        source = mini_netcdf.Source(files[key])
        if request.headers.get("if-none-match") == source.etag:
            return httpx.Response(304, headers={"etag": source.etag})
        return source.handler(request)

    def gateway(self) -> Gateway:
        return Gateway(
            Policy(allowed_hosts=frozenset({HOST})),
            transport=httpx.MockTransport(self.handler),
            resolve=mini_netcdf.from_memory,
        )

    def files_read(self) -> set[str]:
        return {request.url.path.removeprefix("/files/") for request in self.seen if request.url.path != LIST_PATH}


async def materialized_items(archive: Archive, config: DatasetConfig) -> list[dict[str, Any]]:
    """The items a first run writes from ``archive``, without a database."""
    async with archive.gateway() as gateway:
        return await units_items(config, gateway)


async def units_items(config: DatasetConfig, gateway: Gateway) -> list[dict[str, Any]]:
    """The items a first run of an entry with ``updates.detect: units`` writes, without a database: every unit listed,
    built and assembled by the rule of the core (the higher state, then the younger file)."""
    units = MATERIALIZE_SPECS[config.source.adapter].units
    assert units is not None
    listing = await units.list_units(config, gateway=gateway, known_groups={})
    built = await units.build(config, gateway=gateway, units=listing.units)
    best: dict[tuple[str, str], tuple[tuple[int, str], Contribution, Any]] = {}
    for unit, made in zip(listing.units, built, strict=True):
        rank = (unit.state.rank, unit.validators.last_modified or "")
        for contribution in made.contributions:
            if contribution.pair not in best or rank > best[contribution.pair][0]:
                best[contribution.pair] = (rank, contribution, unit.state)
    changes: dict[str, dict[str, Any]] = {}
    for (item_id, asset_key), (_, contribution, state) in best.items():
        changes.setdefault(item_id, {})[asset_key] = (contribution, state)
    items = [assemble_item(config, None, changes[item_id]) for item_id in sorted(changes)]
    return [item for item in items if item is not None]

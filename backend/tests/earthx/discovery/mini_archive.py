"""A synthetic archive item of the MeteoSwiss climate grids and its annual files behind one fake host (M5-11 PR 2).

The files are written by `tests/earthx/readers/mini_netcdf.py`; the host answers the archive item like the FSDI
(ETag, ``304`` on ``If-None-Match``) and each file like the measured source (``206`` on a range, ETag, ``If-Match``).
Nothing of any real source is in them.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import numpy

from earthx.catalog.registry import DatasetConfig
from earthx.gateway import Gateway, Policy
from tests.earthx.readers import mini_netcdf

HOST = mini_netcdf.HOST
ITEM_PATH = "/api/stac/v1/collections/ch.meteoschweiz.ogd-surface-derived-grid/items/archive-ch"
ENDPOINT = f"https://{HOST}{ITEM_PATH}"
ITEM_ETAG = '"archive-1"'
TODAY = date(2025, 6, 1)


def entry(config: DatasetConfig) -> DatasetConfig:
    return replace(config, source=replace(config.source, endpoint=ENDPOINT, asset_hosts=(HOST,)))


def name(quantity: str, grid: str, year: int, end: str = "1231235959") -> str:
    return f"ogd-surface-derived-grid-archive.{quantity.lower()}_{grid}.swiss.lv95_{year}0101000000_{year}{end}.nc"


def annual_file(tmp_path: Path, year: int, days: list[int] | None = None, **options: Any) -> bytes:
    days = [0, 1, 2] if days is None else days
    data = mini_netcdf.values(steps=len(days), seed=year)
    path = tmp_path / f"{year}-{len(list(tmp_path.iterdir()))}.nc"
    return mini_netcdf.build(
        path,
        data,
        time_units=f"days since {year}-01-01 00:00:00",
        time_values=numpy.asarray(days, dtype="f8"),
        **options,
    ).read_bytes()


@dataclass
class Archive:
    """The archive item and its files behind one fake host, answering like the FSDI (adr/0029 §4)."""

    files: dict[str, bytes]
    hrefs: dict[str, str] = field(default_factory=dict)
    gone: set[str] = field(default_factory=set)
    seen: list[httpx.Request] = field(default_factory=list)

    def item(self) -> dict[str, Any]:
        return {
            "type": "Feature",
            "id": "archive-ch",
            "assets": {
                key: {"href": self.hrefs.get(key, f"https://{HOST}/files/{key}"), "file:checksum": hashlib.md5(body).hexdigest()}  # noqa: S324
                for key, body in self.files.items()
            },
        }

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        if request.url.path == ITEM_PATH:
            if request.headers.get("if-none-match") == ITEM_ETAG:
                return httpx.Response(304, headers={"etag": ITEM_ETAG})
            return httpx.Response(200, json=self.item(), headers={"etag": ITEM_ETAG})
        key = request.url.path.removeprefix("/files/")
        if key in self.gone or key not in self.files:
            return httpx.Response(404)
        body = self.files[key]
        return mini_netcdf.Source(body).handler(request)

    def gateway(self) -> Gateway:
        return Gateway(
            Policy(allowed_hosts=frozenset({HOST})),
            transport=httpx.MockTransport(self.handler),
            resolve=mini_netcdf.from_memory,
        )

    def files_read(self) -> set[str]:
        return {request.url.path.removeprefix("/files/") for request in self.seen if request.url.path != ITEM_PATH}

"""Synthetic NetCDF-4 files and a source that serves them with ``Range``, ``ETag`` and ``If-Match`` (M5-11).

The files are written with ``h5py`` in the shape both measured sources have (adr/0029 §3): an array (time, y, x) of
Float32 on an LV95 grid of 1 km, rows stored south to north, ``_FillValue`` as a CF attribute, the axes as dimension
scales, the time counted in days since the first day. Values are random but seeded, so every run writes the same
bytes. Nothing of any real source is in them.

:class:`Source` answers like the measured hosts (adr/0029 §5.1): ``206`` to a range, a strong ETag, ``412`` to an
``If-Match`` with another ETag. Its file can be replaced in the middle of a test, and it can be told to ignore ``Range``
or to cut an answer short.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import h5py
import httpx
import numpy
import pytest

from earthx.gateway import Gateway, Policy

HOST = "grid.example.invalid"
URL = f"https://{HOST}/archive/tabsd_ch01r.swiss.lv95_20240101_20241231.nc"
POLICY = Policy(allowed_hosts=frozenset({HOST}))
DATASET = "synthetic-netcdf"
VARIABLE = "TabsD"
FILL = -999.99
CELL = 1000.0
# The south-west corner of the synthetic grid in LV95, inside Switzerland.
WEST, SOUTH = 2_600_000.0, 1_150_000.0
ROWS, COLUMNS, STEPS = 24, 37, 6
LV95 = {
    "grid_mapping_name": "oblique_mercator",
    "latitude_of_projection_origin": 46.9524055555556,
    "longitude_of_projection_origin": 7.43958333333333,
    "azimuth_of_central_line": 90.0,
    "scale_factor_at_projection_origin": 1.0,
    "false_easting": 2600000.0,
    "false_northing": 1200000.0,
    "semi_major_axis": 6377397.155,
    "inverse_flattening": 299.1528128,
}


def values(steps: int = STEPS, rows: int = ROWS, columns: int = COLUMNS, seed: int = 11) -> numpy.ndarray:
    """The data as stored: (time, y, x), rows south to north, a few cells at the fill value."""
    data = numpy.random.default_rng(seed).normal(8.0, 6.0, (steps, rows, columns)).astype("<f4")
    data[:, 0, :3] = numpy.float32(FILL)
    return data


def build(
    path: Path,
    data: numpy.ndarray | None = None,
    *,
    chunks: tuple[int, int, int] | None = (1, ROWS, COLUMNS),
    shuffle: bool = False,
    zlib: bool = False,
    fletcher32: bool = False,
    south_to_north: bool = True,
    grid_mapping: dict[str, object] | None = None,
    time_units: str = "days since 2024-01-01 00:00:00",
    calendar: str = "standard",
    bounds: bool = False,
    extra_attributes: dict[str, object] | None = None,
    even: bool = True,
) -> Path:
    """One file at ``path``; the switches make the layouts the readers take or refuse."""
    data = values() if data is None else data
    steps, rows, columns = data.shape
    with h5py.File(path, "w") as hdf:
        time = hdf.create_dataset("time", data=numpy.arange(steps, dtype="f8"))
        time.attrs["units"] = time_units
        time.attrs["calendar"] = calendar
        time.attrs["axis"] = "T"
        if bounds:
            # A daily sum from 06 UTC to 06 UTC of the next day, as MeteoSwiss names it for precipitation [S].
            hdf.create_dataset("time_bnds", data=numpy.stack([numpy.arange(steps) + 0.25, numpy.arange(steps) + 1.25], axis=1))
            time.attrs["bounds"] = "time_bnds"
        time.make_scale("time")
        north = SOUTH + CELL * (numpy.arange(rows) + 0.5)
        if not even:
            north[-1] += CELL / 2
        y = hdf.create_dataset("N", data=north if south_to_north else north[::-1])
        y.attrs.update({"standard_name": "projection_y_coordinate", "units": "m", "axis": "Y"})
        y.make_scale("N")
        x = hdf.create_dataset("E", data=WEST + CELL * (numpy.arange(columns) + 0.5))
        x.attrs.update({"standard_name": "projection_x_coordinate", "units": "m", "axis": "X"})
        x.make_scale("E")
        mapping = hdf.create_dataset("swiss_lv95_coordinates", data=numpy.int8(0))
        for name, value in (LV95 if grid_mapping is None else grid_mapping).items():
            mapping.attrs[name] = value
        stored = data if south_to_north else data[:, ::-1, :]
        array = hdf.create_dataset(
            VARIABLE,
            data=stored,
            chunks=chunks,
            shuffle=shuffle,
            compression="gzip" if zlib else None,
            fletcher32=fletcher32,
            fillvalue=numpy.float32(FILL),
        )
        array.attrs["_FillValue"] = numpy.float32(FILL)
        array.attrs["grid_mapping"] = "swiss_lv95_coordinates"
        array.attrs["units"] = "degC"
        for name, value in (extra_attributes or {}).items():
            array.attrs[name] = value
        for dimension, scale in enumerate((time, y, x)):
            array.dims[dimension].attach_scale(scale)
    return path


def from_memory(host: str, port: int) -> tuple[str, ...]:
    """What the system resolver would have said. ``tests/conftest.py`` forbids asking it."""
    return ("93.184.216.34",)


@dataclass
class Source:
    """One file behind a fake host, answering like the measured sources; every request is logged."""

    body: bytes
    ignore_range: bool = False
    short: bool = False
    seen: list[httpx.Request] = field(default_factory=list)

    @property
    def etag(self) -> str:
        return f'"{hashlib.md5(self.body).hexdigest()}-1"'  # noqa: S324 — a fake ETag, not a security hash

    def replace(self, body: bytes) -> None:
        self.body = body

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        if request.headers.get("host") != HOST:
            return httpx.Response(404)
        headers = {"etag": self.etag, "last-modified": "Wed, 12 Feb 2025 08:00:00 GMT"}
        wanted = request.headers.get("if-match")
        if wanted is not None and wanted != self.etag:
            return httpx.Response(412, headers=headers)
        header = request.headers.get("range")
        if header is None or self.ignore_range:
            return httpx.Response(200, content=self.body, headers=headers)
        first, _, last = header.removeprefix("bytes=").partition("-")
        start, end = int(first), min(int(last), len(self.body) - 1)
        piece = self.body[start : end + 1]
        if self.short:
            piece = piece[:-1]
        headers["content-range"] = f"bytes {start}-{end}/{len(self.body)}"
        return httpx.Response(206, content=piece, headers=headers)

    def gateway(self) -> Gateway:
        return Gateway(POLICY, transport=httpx.MockTransport(self.handler), resolve=from_memory)

    def serve_readers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Put this source behind the readers' gateway seam, as `mini_zarr.serve_store` does for a store."""

        def open_gateway(policy: Policy, resolve: Callable[[str, int], tuple[str, ...]], slots=None) -> Gateway:
            return Gateway(policy, transport=httpx.MockTransport(self.handler), resolve=resolve, slots=slots)

        monkeypatch.setattr("earthx.readers.zarr_reader.open_gateway", open_gateway)

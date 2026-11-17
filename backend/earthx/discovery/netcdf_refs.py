"""Chunk references into a NetCDF-4/HDF5 file, made with ``h5py`` through the gateway (adr/0029 A2, §8a.1).

``h5py`` reads the header and the chunk index of a file from :class:`GatewayFile`, a read-only file object in which
every read of a 64 KiB page is one ranged ``GET`` through :class:`~earthx.gateway.Gateway` (5–8 requests per file,
adr/0029 §4). No byte of data is read: the result says, for each time step, at which offsets its chunks lie, and
:func:`step_references` writes that as the ``earthx:refs`` of an item asset, which `readers` reads back
(``readers/reference_store.py`` names every field). This is the only module that imports ``h5py``
(``.importlinter``, ``h5py-only-in-discovery``).

A file whose layout the readers could not read faithfully is refused here with :class:`UnsupportedLayout`, never
referenced with a guess: a filter other than shuffle and zlib, a chunk stored with a filter skipped, CF scaling, a
grid without an EPSG code or with uneven spacing, a time axis that is not days, hours, minutes or seconds since a
date in the standard calendar.
"""

from __future__ import annotations

import asyncio
import io
import math
import re
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import h5py
import numpy
from pyproj import CRS
from pyproj.exceptions import CRSError

from earthx.gateway import Gateway, GatewayError, UpstreamError

__all__ = [
    "PAGE_BYTES",
    "ArrayLayout",
    "FileChanged",
    "FileReferences",
    "GatewayFile",
    "UnsupportedLayout",
    "reference_file",
    "step_references",
]

#: The page a read of the header fetches: 5–8 requests per file instead of 42–93 unbuffered (adr/0029 §4).
PAGE_BYTES = 64 * 1024
# Pages kept while one file is read; its header and chunk index fit many times over.
_PAGES_KEPT = 64
# One chunk must fit into one gateway answer (`Policy.max_response_bytes`), and the readers refuse larger ones.
_MAX_CHUNK_BYTES = 8 * 1024 * 1024
# How long one page may take, waited for from the thread `h5py` runs in.
_PAGE_TIMEOUT_S = 120.0

_FILTERS = {h5py.h5z.FILTER_SHUFFLE: "shuffle", h5py.h5z.FILTER_DEFLATE: "zlib"}
_TIME_UNITS = re.compile(
    r"(?P<unit>days|hours|minutes|seconds)\s+since\s+"
    r"(?P<date>\d{4}-\d{1,2}-\d{1,2})(?:[ T](?P<time>\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?))?\s*(?:Z|UTC|\+00:?00)?$"
)
_STANDARD_CALENDARS = {None, "standard", "gregorian", "proleptic_gregorian"}


class UnsupportedLayout(ValueError):
    """The file is laid out in a way the readers would not read faithfully; the text names what, never the address."""


class FileChanged(Exception):
    """The source replaced the file while its references were being made (``412`` on ``If-Match``)."""


@dataclass(frozen=True, slots=True)
class ArrayLayout:
    """One (time, y, x) array of a file, as the readers need it, with every allocated chunk."""

    variable: str
    dtype: str
    shape: tuple[int, int, int]
    chunks: tuple[int, int, int]
    filters: tuple[str, ...]
    fill_value: float | int | None
    #: (a, b, c, d, e, f) of the stored rows; e > 0 where they run south to north.
    transform: tuple[float, float, float, float, float, float]
    crs: str
    #: The CF ``units`` of the values, where the file names them.
    units: str | None
    #: (time chunk, row chunk, column chunk) → (offset, length).
    chunk_index: Mapping[tuple[int, int, int], tuple[int, int]]


@dataclass(frozen=True, slots=True)
class FileReferences:
    """What one file says about itself: its version, its time steps and the layout of the one array asked for."""

    etag: str
    last_modified: str | None
    size: int
    times: tuple[datetime, ...]
    #: (start, end) of each time step where the file names its bounds (``time_bnds``), else ``None``.
    time_bounds: tuple[tuple[datetime, datetime], ...] | None
    layout: ArrayLayout


class GatewayFile(io.RawIOBase):
    """A read-only, seekable file over one address, read in pages through the gateway from another thread.

    ``h5py`` reads synchronously; the gateway is asynchronous and belongs to ``loop``. So every page is one
    ``Gateway.get`` with ``Range`` run on that loop and waited for here. The first page learns the size
    (``Content-Range``) and the ETag; every later page is sent with ``If-Match``, so a file replaced in the middle
    ends in :class:`FileChanged` rather than in a header from two versions.
    """

    def __init__(self, gateway: Gateway, url: str, loop: asyncio.AbstractEventLoop) -> None:
        super().__init__()
        self._gateway = gateway
        self._url = url
        self._loop = loop
        self._position = 0
        self._pages: OrderedDict[int, bytes] = OrderedDict()
        self.etag: str | None = None
        self.last_modified: str | None = None
        self.size: int | None = None
        #: Every request this file made; read by the tests.
        self.request_count = 0
        self._page(0)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(requests={self.request_count})"

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._position

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self._position, io.SEEK_END: self._size()}[whence]
        if base + offset < 0:
            raise OSError("a negative position")
        self._position = base + offset
        return self._position

    def readinto(self, buffer: Any) -> int:
        view = memoryview(buffer).cast("B")
        end = min(self._position + len(view), self._size())
        written = 0
        while self._position < end:
            number, start = divmod(self._position, PAGE_BYTES)
            page = self._page(number)
            piece = page[start : start + end - self._position]
            if not piece:
                break
            view[written : written + len(piece)] = piece
            written += len(piece)
            self._position += len(piece)
        return written

    def _size(self) -> int:
        assert self.size is not None
        return self.size

    def _page(self, number: int) -> bytes:
        page = self._pages.get(number)
        if page is not None:
            self._pages.move_to_end(number)
            return page
        first = number * PAGE_BYTES
        last = first + PAGE_BYTES - 1 if self.size is None else min(first + PAGE_BYTES, self.size) - 1
        headers = {"Range": f"bytes={first}-{last}"}
        if self.etag is not None:
            headers["If-Match"] = self.etag
        future = asyncio.run_coroutine_threadsafe(self._gateway.get(self._url, headers=headers), self._loop)
        self.request_count += 1
        try:
            response = future.result(timeout=_PAGE_TIMEOUT_S)
        except UpstreamError as error:
            if error.status_code == 412:
                raise FileChanged("the source replaced the file while it was read") from error
            raise
        if response.status_code != 206:
            raise UnsupportedLayout(f"the source answered a range with {response.status_code}, not 206")
        if self.size is None:
            self.size, self.etag, self.last_modified = _first_answer(response.headers)
        page = response.content
        if len(page) != min(last, self.size - 1) - first + 1:
            raise UnsupportedLayout("the source answered a range with another length than asked for")
        self._pages[number] = page
        while len(self._pages) > _PAGES_KEPT:
            self._pages.popitem(last=False)
        return page


def _first_answer(headers: Mapping[str, str]) -> tuple[int, str, str | None]:
    total = headers.get("content-range", "").rpartition("/")[2]
    if not total.isdigit():
        raise UnsupportedLayout("the source names no size of the file (Content-Range)")
    etag = headers.get("etag")
    if not etag or etag.startswith("W/") or not (etag.startswith('"') and etag.endswith('"')) or len(etag) > 256:
        raise UnsupportedLayout("the source names no strong ETag for the file, so its references could not be checked")
    return int(total), etag, headers.get("last-modified")


async def reference_file(gateway: Gateway, url: str, variable: str | None = None) -> FileReferences:
    """The references of ``variable`` in the file at ``url``; ``h5py`` runs in a thread, the requests on this loop.

    Without ``variable`` the file must carry exactly one array over (time, y, x), as each file of MeteoSwiss does, and
    that one is taken. ``url`` must have passed the gateway's policy, which checks it again on every page.
    """
    loop = asyncio.get_running_loop()
    return await asyncio.to_thread(_reference, gateway, url, variable, loop)


def _reference(gateway: Gateway, url: str, variable: str | None, loop: asyncio.AbstractEventLoop) -> FileReferences:
    file = GatewayFile(gateway, url, loop)
    try:
        with h5py.File(file, "r") as hdf:
            variable = _the_one_array(hdf) if variable is None else variable
            if variable not in hdf or not isinstance(hdf[variable], h5py.Dataset):
                raise UnsupportedLayout(f"the file carries no array {variable!r}")
            array = hdf[variable]
            times, bounds = _time_axis(array)
            layout = _layout(hdf, array, variable)
    except OSError as error:
        if isinstance(error.__context__, FileChanged | UnsupportedLayout | GatewayError):
            raise error.__context__ from None
        raise UnsupportedLayout(f"the file is no HDF5 file h5py can open ({error})") from None
    if len(times) != layout.shape[0]:
        raise UnsupportedLayout("the time axis and the array have different lengths")
    assert file.etag is not None and file.size is not None
    return FileReferences(
        etag=file.etag, last_modified=file.last_modified, size=file.size, times=times, time_bounds=bounds, layout=layout
    )


def _the_one_array(hdf: h5py.File) -> str:
    names = [
        name
        for name, node in hdf.items()
        if isinstance(node, h5py.Dataset) and node.ndim == 3 and [s.name for s in node.dims[0].values()] == ["/time"]
    ]
    if len(names) != 1:
        raise UnsupportedLayout(f"the file carries {len(names)} arrays over (time, y, x), not exactly one")
    return names[0]


def _layout(hdf: h5py.File, array: h5py.Dataset, variable: str) -> ArrayLayout:
    if array.ndim != 3:
        raise UnsupportedLayout(f"{variable!r} has {array.ndim} dimensions, not (time, y, x)")
    if array.dtype.kind not in "fiu" or array.dtype.itemsize not in (1, 2, 4, 8) or array.dtype.kind == "f" and array.dtype.itemsize < 4:
        raise UnsupportedLayout(f"{variable!r} is of type {array.dtype}, which the readers do not take")
    attrs = _attributes(array.attrs)
    for name in ("scale_factor", "add_offset"):
        if name in attrs:
            raise UnsupportedLayout(f"{variable!r} carries {name}, which the readers would not apply")
    fill = attrs.get("_FillValue")
    if fill is not None and (not isinstance(fill, int | float) or not math.isfinite(fill)):
        raise UnsupportedLayout(f"{variable!r} has a _FillValue that is not a finite number")
    rows, columns = array.shape[1], array.shape[2]
    y = _axis(array, 1, rows)
    x = _axis(array, 2, columns)
    dx, dy = float(x[1] - x[0]), float(y[1] - y[0])
    if dx <= 0:
        raise UnsupportedLayout("the x axis does not run west to east")
    transform = (dx, 0.0, float(x[0]) - dx / 2, 0.0, dy, float(y[0]) - dy / 2)
    return ArrayLayout(
        variable=variable,
        dtype=array.dtype.str,
        shape=(array.shape[0], rows, columns),
        chunks=tuple(array.chunks) if array.chunks is not None else (array.shape[0], rows, columns),  # type: ignore[arg-type]
        filters=_filters(array),
        fill_value=fill,
        transform=transform,
        crs=_crs(hdf, attrs.get("grid_mapping"), variable),
        units=attrs["units"] if isinstance(attrs.get("units"), str) else None,
        chunk_index=_chunk_index(array),
    )


def _attributes(attrs: Any) -> dict[str, Any]:
    """HDF5 attributes as plain Python: text as ``str``, a one-element array as its value."""
    plain: dict[str, Any] = {}
    for name, value in attrs.items():
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        elif isinstance(value, numpy.ndarray):
            value = value.item() if value.size == 1 else value.tolist()
        elif isinstance(value, numpy.generic):
            value = value.item()
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        plain[name] = value
    return plain


def _axis(array: h5py.Dataset, dimension: int, length: int) -> numpy.ndarray:
    """The coordinates of one spatial dimension: its dimension scale, evenly spaced."""
    scales = list(array.dims[dimension].values())
    if len(scales) != 1 or scales[0].shape != (length,):
        raise UnsupportedLayout(f"dimension {dimension} of the array has no coordinate variable of its length")
    values = numpy.asarray(scales[0][()], dtype="float64")
    if length < 2:
        raise UnsupportedLayout("a grid needs at least two cells along each axis")
    steps = numpy.diff(values)
    if not numpy.all(numpy.isfinite(values)) or numpy.max(numpy.abs(steps - steps[0])) > 1e-3 * abs(steps[0]) or steps[0] == 0:
        raise UnsupportedLayout(f"the coordinates of dimension {dimension} are not evenly spaced")
    return values


def _filters(array: h5py.Dataset) -> tuple[str, ...]:
    plist = array.id.get_create_plist()
    names: list[str] = []
    for index in range(plist.get_nfilters()):
        code = plist.get_filter(index)[0]
        if code not in _FILTERS:
            raise UnsupportedLayout(f"the array is stored with HDF5 filter {code}, which the readers do not decode")
        names.append(_FILTERS[code])
    if names not in ([], ["shuffle"], ["zlib"], ["shuffle", "zlib"]):
        raise UnsupportedLayout(f"the array's filters run in an order the readers do not decode: {names}")
    return tuple(names)


def _chunk_index(array: h5py.Dataset) -> dict[tuple[int, int, int], tuple[int, int]]:
    """Every allocated chunk: index → (offset, length). A chunk HDF5 never wrote is absent and reads as fill."""
    if array.chunks is None:
        offset = array.id.get_offset()
        length = array.id.get_storage_size()
        _check_length(length)
        return {} if offset is None else {(0, 0, 0): (offset, length)}
    chunks = array.chunks
    index: dict[tuple[int, int, int], tuple[int, int]] = {}

    def visit(info: Any) -> None:
        if info.filter_mask != 0:
            raise UnsupportedLayout("a chunk is stored with a filter skipped, which the readers cannot tell")
        _check_length(info.size)
        key = tuple(position // size for position, size in zip(info.chunk_offset, chunks, strict=True))
        index[key] = (info.byte_offset, info.size)  # type: ignore[index]

    array.id.chunk_iter(visit)
    return index


def _check_length(length: int) -> None:
    if length > _MAX_CHUNK_BYTES:
        raise UnsupportedLayout(f"a chunk of {length} bytes is larger than one read of the readers")


def _crs(hdf: h5py.File, name: Any, variable: str) -> str:
    """The EPSG code of the array's ``grid_mapping`` — only where the projection matches that code exactly.

    ``pyproj`` finds EPSG:2056 and EPSG:3035 from the CF attributes of both measured sources only with a low
    confidence, because the attributes name no datum (adr/0029 §5.3). So the candidate is accepted only where its
    ellipsoid and every parameter of its projection equal the file's; otherwise the file is refused.
    """
    if not isinstance(name, str) or name not in hdf:
        raise UnsupportedLayout(f"{variable!r} names no grid_mapping the file carries")
    attrs = _attributes(hdf[name].attrs)
    try:
        crs = CRS.from_cf(attrs)
        code = crs.to_epsg() or crs.to_epsg(min_confidence=20)
        candidate = CRS.from_epsg(code) if code is not None else None
    except CRSError:
        raise UnsupportedLayout("the grid_mapping of the file is no coordinate reference system") from None
    if candidate is None or not _same_projection(crs, candidate):
        raise UnsupportedLayout("the grid_mapping of the file matches no EPSG code exactly")
    return f"EPSG:{code}"


def _same_projection(crs: CRS, candidate: CRS) -> bool:
    if not (crs.is_projected and candidate.is_projected):
        return False
    ours, theirs = crs.ellipsoid, candidate.ellipsoid
    if ours is None or theirs is None:
        return False
    if not (_close(ours.semi_major_metre, theirs.semi_major_metre) and _close(ours.inverse_flattening, theirs.inverse_flattening)):
        return False
    a, b = crs.coordinate_operation, candidate.coordinate_operation
    if a is None or b is None or a.method_name != b.method_name:
        return False
    theirs_params = {p.name: (p.value, p.unit_name) for p in b.params}
    for parameter in a.params:
        other = theirs_params.get(parameter.name)
        if other is None or other[1] != parameter.unit_name or not _close(parameter.value, other[0]):
            return False
    return len(a.params) == len(b.params)


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)


def _time_axis(array: h5py.Dataset) -> tuple[tuple[datetime, ...], tuple[tuple[datetime, datetime], ...] | None]:
    scales = list(array.dims[0].values())
    if len(scales) != 1 or scales[0].name.rsplit("/", 1)[-1] != "time":
        raise UnsupportedLayout("the first dimension of the array is not the time axis 'time'")
    time = scales[0]
    attrs = _attributes(time.attrs)
    origin, unit = _time_units(attrs)
    times = tuple(_instant(origin, unit, value) for value in numpy.asarray(time[()], dtype="float64").ravel())
    bounds_name = attrs.get("bounds")
    if bounds_name is None:
        return times, None
    file = time.file
    if not isinstance(bounds_name, str) or bounds_name not in file or file[bounds_name].shape != (len(times), 2):
        raise UnsupportedLayout("the time axis names bounds the file does not carry in the shape (time, 2)")
    values = numpy.asarray(file[bounds_name][()], dtype="float64")
    return times, tuple((_instant(origin, unit, start), _instant(origin, unit, end)) for start, end in values)


def _time_units(attrs: Mapping[str, Any]) -> tuple[datetime, str]:
    if attrs.get("calendar") not in _STANDARD_CALENDARS:
        raise UnsupportedLayout(f"the time axis uses the calendar {attrs.get('calendar')!r}, not the standard one")
    units = attrs.get("units")
    match = _TIME_UNITS.fullmatch(units.strip()) if isinstance(units, str) else None
    if match is None:
        raise UnsupportedLayout("the time axis is not counted in days, hours, minutes or seconds since a date")
    date = datetime.strptime(match["date"], "%Y-%m-%d").replace(tzinfo=UTC)
    if match["time"]:
        hours, minutes, *seconds = match["time"].split(":")
        date += timedelta(hours=int(hours), minutes=int(minutes), seconds=float(seconds[0]) if seconds else 0.0)
    return date, match["unit"]


def _instant(origin: datetime, unit: str, value: float) -> datetime:
    if not math.isfinite(value):
        raise UnsupportedLayout("the time axis holds a value that is not a number")
    return origin + timedelta(**{unit: float(value)})


def step_references(references: FileReferences, step: int) -> dict[str, Any]:
    """The ``earthx:refs`` of time step ``step``: the row of chunks it lies in, nothing of any other row."""
    layout = references.layout
    if not 0 <= step < layout.shape[0]:
        raise IndexError(f"time step {step} lies outside the file's {layout.shape[0]}")
    row, offset = divmod(step, layout.chunks[0])
    chunk_refs = [
        [[0, index[1], index[2]], position, length]
        for index, (position, length) in sorted(layout.chunk_index.items())
        if index[0] == row
    ]
    return {
        "etag": references.etag,
        "variable": layout.variable,
        "dtype": layout.dtype,
        "shape": [layout.shape[1], layout.shape[2]],
        "chunks": list(layout.chunks),
        "time_offset": offset,
        "filters": list(layout.filters),
        "fill_value": layout.fill_value,
        "transform": list(layout.transform),
        "chunk_refs": chunk_refs,
    }

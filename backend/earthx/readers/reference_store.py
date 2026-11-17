"""Virtual chunk references into a NetCDF-4/HDF5 file, read through the gateway (adr/0029 A2, §8a.1).

A NetCDF-4 file is an HDF5 file: its arrays are stored in chunks at fixed byte offsets. `discovery` reads the
offsets once with ``h5py`` and writes them into the item, one time step per item (adr/0029 F2, F3). This module
reads them back: :func:`parse_references` checks what the item says, and :class:`ReferenceStore` hands ``xarray``
a Zarr v3 group in which one chunk key is one ranged ``GET`` on the source file, sent with ``If-Match`` and the
ETag the references were made from. A file the source has replaced since then answers ``412`` and the read ends in
:class:`SourceChanged`, never in bytes from wrong offsets (adr/0029 §5.1, F7).

What the item carries, under the asset's ``earthx:refs`` (adr/0029 F3, plan M5-11 §4.1)::

    etag         the strong ETag of the file when the references were made
    variable     the name of the array in the file
    dtype        the stored type as a NumPy string with its byte order, e.g. "<f4"
    shape        [rows, columns] of the whole grid
    chunks       [time steps, rows, columns] of one chunk
    time_offset  the position of this item's time step inside its row of chunks
    filters      the HDF5 filters in the order they were applied: "shuffle", "zlib"
    fill_value   the CF ``_FillValue``, or null
    transform    [a, b, c, d, e, f] of the stored rows (x = a·col + c, y = e·row + f); e > 0 means rows run south to north
    chunk_refs   [[time chunk, row chunk, column chunk], offset, length] for every chunk of this row of chunks

The store offers the one row of chunks this time step lies in as an array of shape (chunks[0], rows, columns);
the reader picks ``time_offset`` and turns the rows round where they run south to north. Nothing else of the
file is visible, so a read can never reach another day's bytes. The metadata are built by ``zarr`` itself into a
small in-memory store, which is the one place the format is spelled; only chunk keys of the data array go out.
"""

from __future__ import annotations

import asyncio
import functools
import math
import re
import threading
import warnings
from collections import OrderedDict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import numpy
import zarr
from xarray.backends.zarr import FillValueCoder
from zarr.abc.store import ByteRequest, Store
from zarr.codecs import BytesCodec
from zarr.core.buffer import Buffer, BufferPrototype
from zarr.storage import MemoryStore

from earthx.gateway import Policy, Resolver, UpstreamError, resolve_host

__all__ = [
    "FILTERS",
    "REFS_KEY",
    "TILER_CHUNK_CACHE_BYTES",
    "ChunkRef",
    "ReferenceMismatch",
    "References",
    "ReferencesInvalid",
    "ReferenceStore",
    "SourceChanged",
    "configure_chunk_cache",
    "parse_references",
]

#: The key of an item asset that carries the references.
REFS_KEY = "earthx:refs"

#: The HDF5 filters a reference may name, in the order they were applied on writing. Anything else (szip, Fletcher32,
#: lzf, plugins) is refused when the references are made, so a reader never meets it.
FILTERS = ("shuffle", "zlib")

#: The chunk cache of the tiler (plan M5-11 F6): a view of one day asks for the same chunk once per tile, and
#: MeteoSwiss forbids downloading the same content again and again (adr/0023 §3.1). Workers and the runner keep none
#: (KLAERUNGEN B9).
TILER_CHUNK_CACHE_BYTES = 64 * 1024 * 1024

# Generous for one row of chunks: MeteoSwiss has one chunk per day, DWD HYRAS 25 (adr/0029 §5.4).
_MAX_CHUNK_REFS = 4096
_MAX_GRID_SIDE = 100_000
# One chunk must fit into one gateway answer (`Policy.max_response_bytes`).
_MAX_CHUNK_BYTES = 8 * 1024 * 1024
_DTYPE = re.compile(r"[<>](?:f[48]|[iu][248])|\|[iu]1")
_ETAG = re.compile(r'"[^"\s]{1,254}"')
# zarr says it once per codec it builds; the numcodecs codecs are exactly what an HDF5 chunk needs.
_FIELDS = ("etag", "variable", "dtype", "shape", "chunks", "time_offset", "filters", "fill_value", "transform", "chunk_refs")
_NUMCODECS_WARNING = "Numcodecs codecs are not in the Zarr version 3 specification"
_CONSOLIDATED_WARNING = "Consolidated metadata is currently not part in the Zarr format 3 specification"
warnings.filterwarnings("ignore", message=_NUMCODECS_WARNING)
# Said at every consolidation; the metadata here are built in memory and only ever read by this process.
warnings.filterwarnings("ignore", message=_CONSOLIDATED_WARNING)


class ReferencesInvalid(ValueError):
    """The item's ``earthx:refs`` cannot be read; the text names the field, never an address."""


class SourceChanged(Exception):
    """The source has replaced the file since its references were made: it answered ``412`` to ``If-Match``.

    Raised from the gateway's ``UpstreamError`` so that :func:`earthx.readers.failures.source_failure_kind` finds the
    status in the chain and names it ``source_changed`` (adr/0029 F7).
    """


class ReferenceMismatch(Exception):
    """The source answered a chunk request, but not with the bytes the reference names (no ``206``, wrong length)."""


@dataclass(frozen=True, slots=True)
class ChunkRef:
    """One chunk of the row: its index in (time, row, column) chunks, and where it lies in the file."""

    index: tuple[int, int, int]
    offset: int
    length: int


@dataclass(frozen=True, slots=True)
class References:
    """The checked form of ``earthx:refs`` (see the module docstring for each field)."""

    href: str
    etag: str
    variable: str
    dtype: str
    shape: tuple[int, int]
    chunks: tuple[int, int, int]
    time_offset: int
    filters: tuple[str, ...]
    fill_value: float | int | None
    transform: tuple[float, float, float, float, float, float]
    chunk_refs: tuple[ChunkRef, ...]

    @property
    def y_ascending(self) -> bool:
        """Rows stored from south to north, as both measured sources do (adr/0029 §5.3)."""
        return self.transform[4] > 0


def parse_references(raw: Any, href: str) -> References:
    """``raw`` (the asset's ``earthx:refs``) checked field by field, or :class:`ReferencesInvalid`."""
    if not isinstance(raw, Mapping):
        raise ReferencesInvalid(f"{REFS_KEY} is not an object")
    expected = set(_FIELDS)
    if set(raw) != expected:
        raise ReferencesInvalid(
            f"{REFS_KEY} needs exactly its fields (missing {sorted(expected - set(raw))}, "
            f"unknown {sorted(str(key) for key in set(raw) - expected)})"
        )
    etag = raw["etag"]
    if not isinstance(etag, str) or not _ETAG.fullmatch(etag):
        raise ReferencesInvalid(f"{REFS_KEY}.etag is not a strong ETag")
    variable = raw["variable"]
    if not isinstance(variable, str) or not variable or "/" in variable or len(variable) > 128:
        raise ReferencesInvalid(f"{REFS_KEY}.variable is not the name of an array")
    dtype = raw["dtype"]
    if not isinstance(dtype, str) or not _DTYPE.fullmatch(dtype):
        raise ReferencesInvalid(f"{REFS_KEY}.dtype is not a numeric type with its byte order")
    shape = _ints(raw["shape"], 2, "shape", upper=_MAX_GRID_SIDE)
    chunks = _ints(raw["chunks"], 3, "chunks", upper=_MAX_GRID_SIDE)
    time_offset = raw["time_offset"]
    if not _is_int(time_offset) or not 0 <= time_offset < chunks[0]:
        raise ReferencesInvalid(f"{REFS_KEY}.time_offset lies outside its row of chunks")
    filters = raw["filters"]
    if not isinstance(filters, list) or any(name not in FILTERS for name in filters) or len(set(filters)) != len(filters):
        raise ReferencesInvalid(f"{REFS_KEY}.filters names a filter outside {list(FILTERS)}")
    if filters and filters != [name for name in FILTERS if name in filters]:
        raise ReferencesInvalid(f"{REFS_KEY}.filters are not in the order HDF5 applies them")
    fill_value = raw["fill_value"]
    if fill_value is not None and (not _is_number(fill_value) or not math.isfinite(fill_value)):
        raise ReferencesInvalid(f"{REFS_KEY}.fill_value is not a finite number")
    transform = _transform(raw["transform"])
    return References(
        href=href,
        etag=etag,
        variable=variable,
        dtype=dtype,
        shape=shape,
        chunks=chunks,
        time_offset=time_offset,
        filters=tuple(filters),
        fill_value=fill_value,
        transform=transform,
        chunk_refs=_chunk_refs(raw["chunk_refs"], shape, chunks),
    )


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _ints(value: Any, length: int, name: str, *, upper: int) -> Any:
    if not isinstance(value, list) or len(value) != length or not all(_is_int(v) and 0 < v <= upper for v in value):
        raise ReferencesInvalid(f"{REFS_KEY}.{name} is not {length} positive whole numbers")
    return tuple(value)


def _transform(value: Any) -> tuple[float, float, float, float, float, float]:
    if not isinstance(value, list) or len(value) != 6 or not all(_is_number(v) and math.isfinite(v) for v in value):
        raise ReferencesInvalid(f"{REFS_KEY}.transform is not six finite numbers")
    a, b, c, d, e, f = (float(v) for v in value)
    if b != 0 or d != 0 or a <= 0 or e == 0:
        raise ReferencesInvalid(f"{REFS_KEY}.transform is not a north-up grid with square axes")
    return a, b, c, d, e, f


def _chunk_refs(value: Any, shape: tuple[int, int], chunks: tuple[int, int, int]) -> tuple[ChunkRef, ...]:
    if not isinstance(value, list) or len(value) > _MAX_CHUNK_REFS:
        raise ReferencesInvalid(f"{REFS_KEY}.chunk_refs is not a list of at most {_MAX_CHUNK_REFS} entries")
    limits = (1, -(-shape[0] // chunks[1]), -(-shape[1] // chunks[2]))
    refs: list[ChunkRef] = []
    seen: set[tuple[int, int, int]] = set()
    for entry in value:
        if not (isinstance(entry, list) and len(entry) == 3 and isinstance(entry[0], list) and len(entry[0]) == 3):
            raise ReferencesInvalid(f"{REFS_KEY}.chunk_refs holds an entry that is not [index, offset, length]")
        index, offset, length = entry
        if not all(_is_int(i) and 0 <= i < limit for i, limit in zip(index, limits, strict=True)):
            raise ReferencesInvalid(f"{REFS_KEY}.chunk_refs names a chunk outside the grid")
        if not (_is_int(offset) and offset >= 0 and _is_int(length) and 0 < length <= _MAX_CHUNK_BYTES):
            raise ReferencesInvalid(f"{REFS_KEY}.chunk_refs names a byte range that cannot be read")
        key = (index[0], index[1], index[2])
        if key in seen:
            raise ReferencesInvalid(f"{REFS_KEY}.chunk_refs names one chunk twice")
        seen.add(key)
        refs.append(ChunkRef(index=key, offset=offset, length=length))
    # Empty is allowed: a time step HDF5 never wrote a chunk of reads as its fill value, as it would from the file.
    return tuple(refs)


class _ChunkCache:
    """Bytes of chunks by (address, ETag, offset, length), least recently used out first; off at size 0."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: OrderedDict[tuple[str, str, int, int], bytes] = OrderedDict()
        self._bytes = 0
        self.max_bytes = 0

    def get(self, key: tuple[str, str, int, int]) -> bytes | None:
        with self._lock:
            value = self._entries.get(key)
            if value is not None:
                self._entries.move_to_end(key)
            return value

    def put(self, key: tuple[str, str, int, int], value: bytes) -> None:
        with self._lock:
            if len(value) > self.max_bytes or key in self._entries:
                return
            self._entries[key] = value
            self._bytes += len(value)
            while self._bytes > self.max_bytes:
                _, dropped = self._entries.popitem(last=False)
                self._bytes -= len(dropped)

    def resize(self, max_bytes: int) -> None:
        with self._lock:
            self.max_bytes = max_bytes
            while self._entries and self._bytes > max_bytes:
                _, dropped = self._entries.popitem(last=False)
                self._bytes -= len(dropped)


_CACHE = _ChunkCache()


def configure_chunk_cache(max_bytes: int) -> None:
    """Keep up to ``max_bytes`` of chunks in this process (the tiler: :data:`TILER_CHUNK_CACHE_BYTES`); 0 keeps none."""
    if max_bytes < 0:
        raise ValueError("a cache size is not negative")
    _CACHE.resize(max_bytes)


class ReferenceStore(Store):
    """A read-only Zarr store over one time step's references; one chunk key is one gateway request.

    Like :class:`~earthx.readers.zarr_reader.GatewayStore` it never lists and never writes. The metadata and the
    small coordinate arrays ``x`` and ``y`` come from memory; a chunk key of the data array is a ranged ``GET`` with
    ``If-Match``, and every request is checked again by the gateway.
    """

    def __init__(self, refs: References, policy: Policy, *, resolve: Resolver = resolve_host) -> None:
        super().__init__(read_only=True)
        self._refs = refs
        self._policy = policy
        self._resolve = resolve
        self._local = _metadata(
            refs.variable, refs.dtype, refs.shape, refs.chunks, refs.filters, refs.fill_value, refs.transform
        )
        self._remote = {f"{refs.variable}/c/{i}/{j}/{k}": ref for ref in refs.chunk_refs for i, j, k in [ref.index]}
        #: Every request this store has made; read by the tests and by the closing log line of the reader.
        self.request_count = 0

    def __repr__(self) -> str:
        return f"{type(self).__name__}(requests={self.request_count})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ReferenceStore) and other._refs == self._refs

    def __hash__(self) -> int:
        return hash((type(self), self._refs.href, self._refs.etag, self._refs.chunk_refs))

    @property
    def supports_writes(self) -> bool:
        return False

    @property
    def supports_deletes(self) -> bool:
        return False

    @property
    def supports_listing(self) -> bool:
        return False

    async def get(
        self,
        key: str,
        prototype: BufferPrototype,
        byte_range: ByteRequest | None = None,
    ) -> Buffer | None:
        """Metadata from memory, a data chunk from the source — or ``None`` for a chunk HDF5 never wrote."""
        if byte_range is not None:
            raise NotImplementedError("a reference store hands out whole chunks; nothing here is sharded")
        local = self._local.get(key)
        if local is not None:
            return prototype.buffer.from_bytes(local)
        ref = self._remote.get(key)
        if ref is None:
            return None
        return prototype.buffer.from_bytes(await self._fetch(ref))

    async def _fetch(self, ref: ChunkRef) -> bytes:
        cache_key = (self._refs.href, self._refs.etag, ref.offset, ref.length)
        cached = _CACHE.get(cache_key)
        if cached is not None:
            return cached
        # Imported here: `zarr_reader` imports this module for the store, and the shared client lives there.
        from earthx.readers.zarr_reader import shared_gateway

        gateway = shared_gateway(self._policy, self._resolve)
        self.request_count += 1
        headers = {"Range": f"bytes={ref.offset}-{ref.offset + ref.length - 1}", "If-Match": self._refs.etag}
        try:
            response = await gateway.get(self._refs.href, headers=headers)
        except UpstreamError as error:
            if error.status_code == 412:
                raise SourceChanged("the source has updated this file; it is being catalogued again") from error
            raise
        content = response.content
        if response.status_code != 206 or len(content) != ref.length:
            raise ReferenceMismatch(
                f"the source answered a chunk with status {response.status_code} and {len(content)} bytes, "
                f"not 206 and {ref.length}"
            )
        _CACHE.put(cache_key, content)
        return content

    async def get_partial_values(
        self,
        prototype: BufferPrototype,
        key_ranges: Iterable[tuple[str, ByteRequest | None]],
    ) -> list[Buffer | None]:
        return list(await asyncio.gather(*(self.get(key, prototype, byte_range) for key, byte_range in key_ranges)))

    async def exists(self, key: str) -> bool:
        return key in self._local or key in self._remote

    async def set(self, key: str, value: Buffer) -> None:
        raise NotImplementedError("a reference store reads; the platform never writes to a source")

    async def delete(self, key: str) -> None:
        raise NotImplementedError("a reference store reads; the platform never writes to a source")

    def list(self) -> Any:
        raise NotImplementedError(_NO_LISTING)

    def list_prefix(self, prefix: str) -> Any:
        raise NotImplementedError(_NO_LISTING)

    def list_dir(self, prefix: str) -> Any:
        raise NotImplementedError(_NO_LISTING)


_NO_LISTING = "this store does not list: its keys come from the item's references (adr/0029 F3)"


@functools.lru_cache(maxsize=64)
def _metadata(
    variable: str,
    dtype_name: str,
    shape: tuple[int, int],
    chunks: tuple[int, int, int],
    filters: tuple[str, ...],
    fill_value: float | int | None,
    transform: tuple[float, float, float, float, float, float],
) -> dict[str, bytes]:
    """The consolidated Zarr v3 group of one row of chunks, with ``x`` and ``y``, as the bytes of each key.

    The same for every time step of a grid, so built once per process and layout (about 7 ms each).
    """
    memory: dict[str, Buffer] = {}
    store = MemoryStore(memory)
    dtype = numpy.dtype(dtype_name)
    rows, columns = shape
    attributes: dict[str, Any] = {}
    if fill_value is not None:
        # In the form xarray reads `_FillValue` of a v3 array; the Zarr `fill_value` alone does not mask (adr/0029 §8a.1).
        attributes["_FillValue"] = FillValueCoder.encode(dtype.type(fill_value), dtype)
    compressors: list[Any] = []
    if "shuffle" in filters:
        compressors.append(zarr.codecs.numcodecs.Shuffle(elementsize=dtype.itemsize))
    if "zlib" in filters:
        compressors.append(zarr.codecs.numcodecs.Zlib())
    group = zarr.open_group(store=store, mode="w", zarr_format=3)
    group.create_array(
        variable,
        shape=(chunks[0], rows, columns),
        chunks=chunks,
        dtype=dtype.newbyteorder("="),
        fill_value=fill_value if fill_value is not None else 0,
        serializer=BytesCodec(endian="big" if dtype.byteorder == ">" else "little"),
        compressors=compressors,
        dimension_names=("time", "y", "x"),
        attributes=attributes,
    )
    a, _, c, _, e, f = transform
    for name, length, origin, step in (("y", rows, f, e), ("x", columns, c, a)):
        axis = group.create_array(name, shape=(length,), dtype="float64", dimension_names=(name,), fill_value=0.0)
        axis[:] = origin + step * (numpy.arange(length, dtype="float64") + 0.5)
    zarr.consolidate_metadata(store)
    return {key: value.to_bytes() for key, value in memory.items()}

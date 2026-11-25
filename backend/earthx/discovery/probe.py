"""What the first bytes of a file say about its format, without GDAL (adr/0025 §6.3; adr/0031 §4.4; M5-20 plan §14.1.3).

Verify of a candidate for a full entry reads at most the first 16 KB of a file (``Range: bytes=0-16383``) and hands
them here. Recognised: TIFF and BigTIFF (a COG by the layout note GDAL writes into its header, if tiled), NetCDF classic,
HDF5 (also NetCDF-4) and Zarr by the address of its metadata. Of a TIFF, the first image file directory is read as far
as it lies in the bytes: size, bands, data type, tiling, the number of further directories (overviews), the EPSG code of
its GeoKeys and the nodata value of GDAL. What lies beyond the bytes is ``None`` (unknown), never guessed.

Pure: no request, no file, no driver; the bytes come from a foreign host and are only parsed by the code below, which
checks every offset and count against the length it was given.
"""

from __future__ import annotations

import re
import struct
from dataclasses import asdict, dataclass
from typing import Any

__all__ = ["HEAD_BYTES", "READABLE", "FileFormat", "TiffHeader", "sniff"]

#: How many bytes Verify reads of a file (adr/0025 §6.3).
HEAD_BYTES = 16384
#: The formats a full entry can read (M5-20 F6 = 1): what Verify must find for a candidate.
READABLE = frozenset({"cog", "geotiff", "netcdf", "hdf5", "zarr"})

_HDF5 = b"\x89HDF\r\n\x1a\n"
#: HDF5 may put its signature at 0, 512, 1024, 2048 … (a user block before it); within the bytes read.
_HDF5_OFFSETS = (0, 512, 1024, 2048, 4096, 8192)
_ZARR_NAMES = re.compile(r"/(?:zarr\.json|\.zarray|\.zgroup|\.zattrs|\.zmetadata)(?:[?#]|$)", re.IGNORECASE)
#: GDAL writes one of these into the ghost area of a COG header, right after the first 8 or 16 bytes.
_COG_NOTES = (b"LAYOUT=IFDS_BEFORE_DATA", b"LAYOUT=COG")

# TIFF tags read here.
_WIDTH, _LENGTH, _BITS, _SAMPLES, _SAMPLE_FORMAT = 256, 257, 258, 277, 339
_TILE_WIDTH, _TILE_LENGTH, _SUBFILE = 322, 323, 254
_GEO_KEYS, _GDAL_NODATA = 34735, 42113
_PROJECTED_CRS, _GEOGRAPHIC_CRS = 3072, 2048
#: TIFF field types: size in bytes and struct code (``None``: not read as a number).
_TYPES: dict[int, tuple[int, str | None]] = {
    1: (1, "B"), 2: (1, None), 3: (2, "H"), 4: (4, "I"), 5: (8, None), 6: (1, "b"), 7: (1, None), 8: (2, "h"),
    9: (4, "i"), 10: (8, None), 11: (4, "f"), 12: (8, "d"), 16: (8, "Q"), 17: (8, "q"), 18: (8, "Q"),
}
#: The data types of a sample by SampleFormat (1 unsigned, 2 signed, 3 float) and bits.
_DATA_TYPES = {
    (1, 8): "uint8", (1, 16): "uint16", (1, 32): "uint32", (1, 64): "uint64",
    (2, 8): "int8", (2, 16): "int16", (2, 32): "int32", (2, 64): "int64",
    (3, 16): "float16", (3, 32): "float32", (3, 64): "float64",
}
#: More directories than this in a chain is no TIFF a full entry reads (and stops a crafted loop).
_MAX_DIRECTORIES = 64
#: Entries of one directory above this are no image header (a crafted count).
_MAX_ENTRIES = 512
#: A value list longer than this is not read (a crafted count); GeoKeys and BitsPerSample are short.
_MAX_VALUES = 4096


@dataclass(frozen=True, slots=True)
class TiffHeader:
    """What the first directory of a TIFF says, ``None`` where it lies beyond the bytes read."""

    width: int | None
    height: int | None
    bands: int | None
    data_type: str | None
    tiled: bool | None
    tile_size: tuple[int, int] | None
    #: Further directories found in the bytes (the overviews of a COG); ``None`` where the chain leaves the bytes.
    overviews: int | None
    epsg: int | None
    nodata: str | None


@dataclass(frozen=True, slots=True)
class FileFormat:
    """The format of a file by its first bytes: one of :data:`READABLE`, ``tiff`` (a TIFF without geo keys),
    ``hdf4``, ``html`` (an error or login page) or ``unknown``."""

    format: str
    big_tiff: bool = False
    tiff: TiffHeader | None = None

    @property
    def readable(self) -> bool:
        return self.format in READABLE

    def to_document(self) -> dict[str, Any]:
        document = {"format": self.format}
        if self.tiff is not None:
            header = asdict(self.tiff)
            header["tile_size"] = list(self.tiff.tile_size) if self.tiff.tile_size else None
            document["tiff"] = header
        if self.big_tiff:
            document["big_tiff"] = True
        return document


class _Bytes:
    """Bounded reads from the head of a file in one byte order; ``None`` where a read leaves the bytes."""

    def __init__(self, data: bytes, order: str) -> None:
        self.data = data
        self.order = order

    def unpack(self, code: str, offset: int, count: int = 1) -> tuple[Any, ...] | None:
        size = struct.calcsize(code) * count
        if offset < 0 or count < 0 or offset + size > len(self.data):
            return None
        return struct.unpack_from(f"{self.order}{count}{code}", self.data, offset)


def _values(head: _Bytes, field_type: int, count: int, value_at: int, inline: int, big: bool) -> tuple[Any, ...] | None:
    """The values of one directory entry: inline where they fit into the entry, else at the offset it names."""
    size, code = _TYPES.get(field_type, (0, None))
    if code is None or count > _MAX_VALUES:
        return None
    if size * count <= inline:
        return head.unpack(code, value_at, count)
    pointer = head.unpack("Q" if big else "I", value_at)
    return None if pointer is None else head.unpack(code, pointer[0], count)


def _ascii(head: _Bytes, count: int, value_at: int, inline: int, big: bool) -> str | None:
    if count > _MAX_VALUES:
        return None
    if count <= inline:
        start = value_at
    else:
        pointer = head.unpack("Q" if big else "I", value_at)
        if pointer is None:
            return None
        start = pointer[0]
    if start < 0 or start + count > len(head.data):
        return None
    return head.data[start : start + count].split(b"\x00", 1)[0].decode("ascii", "replace").strip() or None


def _directory(head: _Bytes, offset: int, big: bool) -> tuple[dict[int, Any], int | None] | None:
    """The tags of the directory at ``offset`` that are read here, and the offset of the next directory (``0``: none;
    ``None``: beyond the bytes). ``None`` where the directory itself leaves the bytes."""
    count = head.unpack("Q" if big else "H", offset)
    if count is None or count[0] > _MAX_ENTRIES:
        return None
    entry_size, inline = (20, 8) if big else (12, 4)
    first = offset + (8 if big else 2)
    tags: dict[int, Any] = {}
    for index in range(count[0]):
        at = first + index * entry_size
        entry = head.unpack("HHQ" if big else "HHI", at)
        if entry is None:
            return None
        tag, field_type, number = entry
        value_at = at + 4 + (8 if big else 4)
        if tag == _GDAL_NODATA and field_type == 2:
            tags[tag] = _ascii(head, number, value_at, inline, big)
        elif tag in (_WIDTH, _LENGTH, _BITS, _SAMPLES, _SAMPLE_FORMAT, _TILE_WIDTH, _TILE_LENGTH, _SUBFILE, _GEO_KEYS):
            tags[tag] = _values(head, field_type, number, value_at, inline, big)
    following = head.unpack("Q" if big else "I", first + count[0] * entry_size)
    return tags, (None if following is None else following[0])


def _first(values: tuple[Any, ...] | None) -> int | None:
    return int(values[0]) if values else None


def _epsg(keys: tuple[Any, ...] | None) -> tuple[int | None, bool]:
    """The EPSG code of the GeoKey directory (projected before geographic), and whether there are geo keys at all."""
    if not keys or len(keys) < 4:
        return None, False
    found: dict[int, int] = {}
    for index in range(1, min(int(keys[3]), (len(keys) - 4) // 4) + 1):
        key, location, _count, value = (int(v) for v in keys[index * 4 : index * 4 + 4])
        if location == 0:
            found[key] = value
    code = found.get(_PROJECTED_CRS) or found.get(_GEOGRAPHIC_CRS)
    # 32767 is "user defined": no EPSG code to name.
    return (code if code and code != 32767 else None), True


def _tiff(data: bytes) -> FileFormat:
    order = "<" if data[:2] == b"II" else ">"
    head = _Bytes(data, order)
    version = head.unpack("H", 2)
    big = version is not None and version[0] == 43
    pointer = head.unpack("Q", 8) if big else head.unpack("I", 4)
    noted = any(note in data[:512] for note in _COG_NOTES)
    directory = None if pointer is None else _directory(head, pointer[0], big)
    if directory is None:
        return FileFormat("tiff", big_tiff=big, tiff=TiffHeader(*([None] * 9)))
    tags, following = directory
    bits = tags.get(_BITS)
    sample_format = _first(tags.get(_SAMPLE_FORMAT)) or 1
    data_type = _DATA_TYPES.get((sample_format, int(bits[0]))) if bits else None
    tile_width, tile_height = _first(tags.get(_TILE_WIDTH)), _first(tags.get(_TILE_LENGTH))
    tiled = None if _WIDTH not in tags else tile_width is not None
    overviews: int | None = 0
    seen = {pointer[0]} if pointer else set()
    while following:
        if following in seen or len(seen) >= _MAX_DIRECTORIES:
            overviews = None
            break
        seen.add(following)
        nested = _directory(head, following, big)
        if nested is None:
            overviews = None
            break
        overviews = (overviews or 0) + 1
        following = nested[1]
    if following is None:
        overviews = None
    epsg, geo = _epsg(tags.get(_GEO_KEYS))
    header = TiffHeader(
        width=_first(tags.get(_WIDTH)),
        height=_first(tags.get(_LENGTH)),
        bands=_first(tags.get(_SAMPLES)) or (1 if _WIDTH in tags else None),
        data_type=data_type,
        tiled=tiled,
        tile_size=(tile_width, tile_height) if tile_width and tile_height else None,
        overviews=overviews,
        epsg=epsg,
        nodata=tags.get(_GDAL_NODATA),
    )
    # A COG is tiled with its directories before the data, which GDAL notes in the ghost area; a TIFF without geo keys
    # is no geodata a full entry can place.
    kind = "cog" if noted and tiled and geo else ("geotiff" if geo else "tiff")
    return FileFormat(kind, big_tiff=big, tiff=header)


def sniff(data: bytes, url: str = "") -> FileFormat:
    """The format of a file by its first bytes (``data``) and, for Zarr, the address its metadata came from."""
    if data[:4] in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"):
        return _tiff(data)
    if data[:4] in (b"CDF\x01", b"CDF\x02", b"CDF\x05"):
        return FileFormat("netcdf")
    if any(data[offset : offset + 8] == _HDF5 for offset in _HDF5_OFFSETS):
        return FileFormat("hdf5")
    if data[:4] == b"\x0e\x03\x13\x01":
        return FileFormat("hdf4")
    if _ZARR_NAMES.search(url) and data.lstrip()[:1] == b"{":
        return FileFormat("zarr")
    if data.lstrip()[:15].lower().startswith((b"<!doctype html", b"<html")):
        return FileFormat("html")
    return FileFormat("unknown")

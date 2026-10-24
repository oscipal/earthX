"""The ZIP of a raster result, laid out before a byte of it is read (M4-11b-1; plans/m4/m4-11b-angebot-und-zip.md §3.1).

`api` hands a job's result out as one ZIP: a folder with `result.tif`, `mask.tif` and the files of a
crop's ZIP beside its rasters (`aoi.geojson`, `recipe.json`, `citation.bib`, `ATTRIBUTION.txt`). The rasters are not compressed (``ZIP_STORED``) and their size and CRC-32 are known
before the first byte leaves (the supervisor reported them when it uploaded the files), so no data
descriptor is needed and the whole archive is a list of parts with fixed offsets: headers and small
documents as bytes, the rasters as ranges of objects in the store. That gives ``Content-Length``
and lets any byte range of the ZIP be answered without building it — the same design as nginx's
`mod_zip` with its manifest of "CRC-32, size, location, name" per file.

Same format as `zipfile` reads and writes (CPython 3.12), with the limits of the specification:
an entry is ZIP64 where its size reaches ``0xFFFFFFFF`` (extra field 0x0001 with both sizes, in
the local header), a central entry adds its offset where that reaches ``0xFFFFFFFF``, and the end
record is ZIP64 where the central directory begins at or past ``0xFFFFFFFF`` or has that many bytes
or ``0xFFFF`` entries. Names are UTF-8 (flag bit 11); one fixed time stamp covers every entry, so
two builds of the same layout are the same bytes.

Nothing here reads a file or the store: :meth:`Layout.segments` says which bytes are where.
"""

from __future__ import annotations

import bisect
import hashlib
import re
import struct
import zlib
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from earthx.objectstore.results import FILES_META

__all__ = [
    "FileFacts",
    "Layout",
    "Literal",
    "Member",
    "RangeNotSatisfiable",
    "Stored",
    "byte_range",
    "reported_files",
]

LIMIT = 0xFFFFFFFF
COUNT_LIMIT = 0xFFFF

_LOCAL = struct.Struct("<4sBBHHHHLLLHH")
_CENTRAL = struct.Struct("<4sBBBBHHHHLLLHHHHHLL")
_END = struct.Struct("<4s4H2LH")
_END64 = struct.Struct("<4sQBBBBLLQQQQ")
_LOCATOR64 = struct.Struct("<4sLQL")
_EXTRA = struct.Struct("<HH")

_DEFAULT_VERSION = 20
_ZIP64_VERSION = 45
_UNIX = 3
_FLAG_UTF8 = 1 << 11
_STORED = 0
_FILE_MODE = 0o100644 << 16
_NAME_MAX = 255


@dataclass(frozen=True)
class FileFacts:
    """What the supervisor reported of one uploaded file."""

    bytes: int
    crc32: int


def reported_files(result: Mapping[str, Any] | None, names: Sequence[str]) -> dict[str, FileFacts] | None:
    """The facts of every file in ``names`` from a run's ``files_meta``; ``None`` if any is missing or odd.

    A run from before the facts were kept, an export and a document of another shape all give
    ``None``: there is no ZIP for them.
    """
    meta = (result or {}).get(FILES_META)
    if not isinstance(meta, Mapping):
        return None
    found: dict[str, FileFacts] = {}
    for name in names:
        entry = meta.get(name)
        if not isinstance(entry, Mapping):
            return None
        size, crc = entry.get("bytes"), entry.get("crc32")
        if not _is_int(size) or not _is_int(crc) or size < 0 or not 0 <= crc <= LIMIT:
            return None
        found[name] = FileFacts(size, crc)
    return found


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True)
class Member:
    """One entry of the archive: its name inside it, its size and CRC-32, and where its bytes are."""

    name: str
    size: int
    crc32: int
    data: bytes | None = None
    #: The name of the stored result file (``result.tif``) when ``data`` is ``None``.
    source: str | None = None

    @classmethod
    def of_bytes(cls, name: str, data: bytes) -> Member:
        return cls(name, len(data), zlib.crc32(data), data=data)

    @classmethod
    def stored(cls, name: str, source: str, facts: FileFacts) -> Member:
        return cls(name, facts.bytes, facts.crc32, source=source)

    def __post_init__(self) -> None:
        if (self.data is None) == (self.source is None):
            raise ValueError("a member has its bytes either in memory or in the store")
        if self.data is not None and len(self.data) != self.size:
            raise ValueError("the size of a member in memory is the length of its bytes")
        if self.size < 0 or not 0 <= self.crc32 <= LIMIT:
            raise ValueError("size and CRC-32 of a member are not negative and fit 32 bits")
        _check_name(self.name)


def _check_name(name: str) -> None:
    parts = name.split("/")
    if (
        not name
        or "\\" in name
        or name.startswith("/")
        or any(part in ("", ".", "..") for part in parts)
        or not name.isprintable()
        or len(name.encode("utf-8")) > _NAME_MAX
    ):
        raise ValueError("the name of a member is a relative path of printable characters without '..'")


@dataclass(frozen=True)
class Literal:
    """Bytes of the archive that are known: a header, a small document, the directory."""

    data: bytes


@dataclass(frozen=True)
class Stored:
    """Bytes ``begin`` to ``end`` (end excluded) of the stored result file ``source``."""

    source: str
    begin: int
    end: int


Segment = Literal | Stored


class RangeNotSatisfiable(Exception):
    """The ``Range`` of a request begins behind the end of the archive (``416``)."""


def _dos_time(moment: datetime) -> tuple[int, int]:
    """DOS ``(date, time)`` of ``moment`` in UTC, clamped to 1980 to 2107, as ZIP stores it."""
    if moment.tzinfo is None:
        raise ValueError("the time stamp of the archive must be timezone-aware")
    utc = moment.astimezone(UTC)
    if utc.year < 1980:
        utc = datetime(1980, 1, 1, tzinfo=UTC)
    elif utc.year > 2107:
        utc = datetime(2107, 12, 31, 23, 59, 58, tzinfo=UTC)
    date = ((utc.year - 1980) << 9) | (utc.month << 5) | utc.day
    time = (utc.hour << 11) | (utc.minute << 5) | (utc.second // 2)
    return date, time


class Layout:
    """The archive as parts with fixed offsets: ``total`` bytes, any range of them by :meth:`segments`."""

    def __init__(self, members: Sequence[Member], *, modified: datetime) -> None:
        if not members:
            raise ValueError("an archive has at least one member")
        names = [member.name for member in members]
        if len(set(names)) != len(names):
            raise ValueError("the names of the members are all different")
        self.members = tuple(members)
        self.modified = modified
        date, time = _dos_time(modified)
        parts: list[Segment] = []
        offsets: list[int] = []
        position = 0
        for member in self.members:
            offsets.append(position)
            header = _local_header(member, date, time)
            parts.append(Literal(header))
            position += len(header)
            if member.size:
                parts.append(
                    Literal(member.data) if member.data is not None else Stored(str(member.source), 0, member.size)
                )
                position += member.size
        directory = b"".join(
            _central_entry(m, offset, date, time) for m, offset in zip(self.members, offsets, strict=True)
        )
        parts.append(Literal(directory))
        parts.append(Literal(_end_records(len(self.members), len(directory), position)))
        self._parts = parts
        self._starts: list[int] = []
        start = 0
        for part in parts:
            self._starts.append(start)
            start += _length(part)
        self.total = start
        self.etag = _etag(self.members, date, time)

    def segments(self, start: int, end: int) -> Iterator[Segment]:
        """The parts of bytes ``start`` to ``end`` (end excluded) of the archive, cut at both ends."""
        start, end = max(start, 0), min(end, self.total)
        if start >= end:
            return
        index = bisect.bisect_right(self._starts, start) - 1
        while index < len(self._parts) and self._starts[index] < end:
            part, first = self._parts[index], self._starts[index]
            low, high = max(start, first) - first, min(end, first + _length(part)) - first
            if isinstance(part, Literal):
                yield Literal(part.data[low:high])
            else:
                yield Stored(part.source, part.begin + low, part.begin + high)
            index += 1


def _length(part: Segment) -> int:
    return len(part.data) if isinstance(part, Literal) else part.end - part.begin


#: Raised when the way the archive is written changes, so that no validator of the old form matches.
FORMAT = 1


def _etag(members: Sequence[Member], date: int, time: int) -> str:
    """A strong validator over everything that decides the bytes: names, sizes, CRCs, the time stamp, the format."""
    digest = hashlib.sha256(f"{FORMAT}:{date}:{time}".encode())
    for member in members:
        digest.update(f"\0{member.name}\0{member.size}\0{member.crc32}".encode())
    return f'"{digest.hexdigest()[:32]}"'


def _local_header(member: Member, date: int, time: int) -> bytes:
    name = member.name.encode("utf-8")
    zip64 = member.size >= LIMIT
    extra = _EXTRA.pack(1, 16) + struct.pack("<QQ", member.size, member.size) if zip64 else b""
    size = LIMIT if zip64 else member.size
    version = _ZIP64_VERSION if zip64 else _DEFAULT_VERSION
    head = _LOCAL.pack(
        b"PK\x03\x04", version, 0, _FLAG_UTF8, _STORED, time, date, member.crc32, size, size, len(name), len(extra)
    )
    return head + name + extra


def _central_entry(member: Member, offset: int, date: int, time: int) -> bytes:
    name = member.name.encode("utf-8")
    big_size, big_offset = member.size >= LIMIT, offset >= LIMIT
    extra_fields: list[int] = []
    if big_size:
        extra_fields += [member.size, member.size]
    if big_offset:
        extra_fields.append(offset)
    extra = (
        _EXTRA.pack(1, 8 * len(extra_fields)) + struct.pack(f"<{len(extra_fields)}Q", *extra_fields)
        if extra_fields
        else b""
    )
    size = LIMIT if big_size else member.size
    version = _ZIP64_VERSION if extra_fields else _DEFAULT_VERSION
    head = _CENTRAL.pack(
        b"PK\x01\x02",
        version,
        _UNIX,
        version,
        0,
        _FLAG_UTF8,
        _STORED,
        time,
        date,
        member.crc32,
        size,
        size,
        len(name),
        len(extra),
        0,
        0,
        0,
        _FILE_MODE,
        LIMIT if big_offset else offset,
    )
    return head + name + extra


def _end_records(count: int, directory_size: int, directory_offset: int) -> bytes:
    needs64 = count >= COUNT_LIMIT or directory_size >= LIMIT or directory_offset >= LIMIT
    records = b""
    if needs64:
        records += _END64.pack(
            b"PK\x06\x06",
            44,
            _ZIP64_VERSION,
            _UNIX,
            _ZIP64_VERSION,
            0,
            0,
            0,
            count,
            count,
            directory_size,
            directory_offset,
        )
        records += _LOCATOR64.pack(b"PK\x06\x07", 0, directory_offset + directory_size, 1)
    return records + _END.pack(
        b"PK\x05\x06",
        0,
        0,
        min(count, COUNT_LIMIT),
        min(count, COUNT_LIMIT),
        min(directory_size, LIMIT),
        min(directory_offset, LIMIT),
        0,
    )


_RANGE = re.compile(r"^(?P<first>[0-9]{1,18})?-(?P<last>[0-9]{1,18})?$")


def byte_range(header: str | None, total: int) -> tuple[int, int] | None:
    """The one range ``(first, last)``, both included, a ``Range`` header asks for; ``None`` to send it all.

    RFC 9110 §14.2 lets a server ignore a range it cannot use, so those are ``None``: no header,
    another unit than ``bytes``, more than one range, a range of the wrong shape or one that ends
    before it begins. A range that begins behind the end — or a suffix of no bytes — raises
    :class:`RangeNotSatisfiable`. A last position past the end is cut to the end.
    """
    if not header:
        return None
    unit, _, spec = header.partition("=")
    if unit.strip().lower() != "bytes" or "," in spec:
        return None
    match = _RANGE.match(spec.strip())
    if match is None or (match["first"] is None and match["last"] is None):
        return None
    first, last = match["first"], match["last"]
    if first is None:  # the last n bytes
        count = int(last)
        if count == 0:
            raise RangeNotSatisfiable
        return max(total - count, 0), total - 1
    begin = int(first)
    if last is not None and int(last) < begin:
        return None
    if begin >= total:
        raise RangeNotSatisfiable
    return begin, total - 1 if last is None else min(int(last), total - 1)

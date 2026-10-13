"""The ZIP of a raster result: its layout, its byte ranges and the ZIP64 limits (M4-11b-1, plan §3.1.4, §3.4).

``zipfile`` of the standard library is the counter-party: it reads what ``Layout`` lays out and checks the
CRC of every entry. Nothing here touches a store or the disk; the rasters are bytes in a dict, and the one
entry over 4 GiB is a stream of zero bytes that is never held.
"""

from __future__ import annotations

import io
import random
import struct
import zipfile
import zlib
from collections.abc import Mapping
from datetime import UTC, datetime

import pytest

from earthx.api.result_zip import (
    FileFacts,
    Layout,
    Literal,
    Member,
    RangeNotSatisfiable,
    Stored,
    byte_range,
    reported_files,
)

MODIFIED = datetime(2026, 3, 5, 10, 0, 7, tzinfo=UTC)
FOLDER = "sentinel-2-c1-l2a_scale_20260305"
RESULT = random.Random(1).randbytes(10_000)
MASK = random.Random(2).randbytes(3_000)
RECIPE = b'{"recipe_id": "x"}\n'
CITATION = b"@misc{x, title={X}}\n"
STORE = {"result.tif": RESULT, "mask.tif": MASK}


def members(*, result: bytes = RESULT, mask: bytes = MASK) -> list[Member]:
    return [
        Member.stored(f"{FOLDER}/result.tif", "result.tif", FileFacts(len(result), zlib.crc32(result))),
        Member.stored(f"{FOLDER}/mask.tif", "mask.tif", FileFacts(len(mask), zlib.crc32(mask))),
        Member.of_bytes(f"{FOLDER}/recipe.json", RECIPE),
        Member.of_bytes(f"{FOLDER}/citation.bib", CITATION),
    ]


def build(layout: Layout, store: Mapping[str, bytes] = STORE, start: int = 0, end: int | None = None) -> bytes:
    """The bytes ``start`` to ``end`` of the archive, from the segments and the files in ``store``."""
    parts = []
    for segment in layout.segments(start, layout.total if end is None else end):
        if isinstance(segment, Literal):
            parts.append(segment.data)
        else:
            parts.append(store[segment.source][segment.begin : segment.end])
    return b"".join(parts)


@pytest.fixture
def layout() -> Layout:
    return Layout(members(), modified=MODIFIED)


class TestTheArchive:
    def test_zipfile_reads_it_and_finds_every_crc_right(self, layout: Layout) -> None:
        archive = zipfile.ZipFile(io.BytesIO(build(layout)))
        assert archive.testzip() is None
        assert archive.namelist() == [
            f"{FOLDER}/{name}" for name in ("result.tif", "mask.tif", "recipe.json", "citation.bib")
        ]
        assert archive.read(f"{FOLDER}/result.tif") == RESULT
        assert archive.read(f"{FOLDER}/mask.tif") == MASK
        assert archive.read(f"{FOLDER}/recipe.json") == RECIPE
        assert archive.read(f"{FOLDER}/citation.bib") == CITATION

    def test_the_rasters_and_the_texts_are_stored_not_compressed(self, layout: Layout) -> None:
        archive = zipfile.ZipFile(io.BytesIO(build(layout)))
        for info in archive.infolist():
            assert info.compress_type == zipfile.ZIP_STORED and info.compress_size == info.file_size
            assert not info.flag_bits & 0x08, "sizes and CRCs are in the local header, no data descriptor"
            assert info.date_time == (2026, 3, 5, 10, 0, 6), "ZIP keeps two-second steps"
            assert info.external_attr >> 16 == 0o100644 and info.create_system == 3

    def test_it_is_as_long_as_it_says(self, layout: Layout) -> None:
        assert len(build(layout)) == layout.total

    def test_two_builds_are_the_same_bytes_and_have_one_etag(self, layout: Layout) -> None:
        again = Layout(members(), modified=MODIFIED)
        assert build(layout) == build(again) and layout.etag == again.etag
        assert layout.etag.startswith('"') and layout.etag.endswith('"') and len(layout.etag) == 34

    def test_the_etag_changes_with_anything_that_changes_the_bytes(self, layout: Layout) -> None:
        other_result = Layout(members(result=RESULT[:-1] + b"?"), modified=MODIFIED)
        later = Layout(members(), modified=datetime(2026, 3, 5, 10, 0, 9, tzinfo=UTC))
        renamed = Layout([Member.of_bytes("other/recipe.json", RECIPE)], modified=MODIFIED)
        assert len({layout.etag, other_result.etag, later.etag, renamed.etag}) == 4

    def test_a_time_before_1980_or_after_2107_is_clamped_not_refused(self) -> None:
        for moment in (datetime(1970, 1, 1, tzinfo=UTC), datetime(2200, 1, 1, tzinfo=UTC)):
            archive = zipfile.ZipFile(io.BytesIO(build(Layout(members(), modified=moment))))
            assert archive.testzip() is None

    def test_a_time_zone_is_converted_not_read_as_local(self) -> None:
        from datetime import timedelta, timezone

        plus_two = datetime(2026, 3, 5, 12, 0, 0, tzinfo=timezone(timedelta(hours=2)))
        archive = zipfile.ZipFile(io.BytesIO(build(Layout(members(), modified=plus_two))))
        assert archive.infolist()[0].date_time == (2026, 3, 5, 10, 0, 0)

    def test_an_empty_file_is_an_entry_with_no_bytes(self) -> None:
        empty = Member.stored(f"{FOLDER}/mask.tif", "mask.tif", FileFacts(0, 0))
        built = build(Layout([empty, *members()[2:]], modified=MODIFIED), {"mask.tif": b""})
        archive = zipfile.ZipFile(io.BytesIO(built))
        assert archive.testzip() is None and archive.read(f"{FOLDER}/mask.tif") == b""

    def test_a_name_with_umlauts_is_utf8_and_flagged_so(self) -> None:
        member = Member.of_bytes("Ordner-ä/recipe.json", RECIPE)
        archive = zipfile.ZipFile(io.BytesIO(build(Layout([member], modified=MODIFIED))))
        assert archive.namelist() == ["Ordner-ä/recipe.json"] and archive.infolist()[0].flag_bits & 0x800


class TestByteRanges:
    def test_every_range_is_the_slice_of_the_whole(self, layout: Layout) -> None:
        whole = build(layout)
        rng = random.Random(3)
        edges = {0, 1, layout.total - 1, layout.total}
        for offset in layout._starts:
            edges |= {offset - 1, offset, offset + 1}
        edges = sorted(e for e in edges if 0 <= e <= layout.total)
        pairs = [(a, b) for a in edges for b in edges if a <= b]
        pairs += [tuple(sorted((rng.randrange(layout.total + 1), rng.randrange(layout.total + 1)))) for _ in range(300)]
        for start, end in pairs:
            assert build(layout, start=start, end=end) == whole[start:end], (start, end)

    def test_no_segment_is_empty_and_their_lengths_add_up(self, layout: Layout) -> None:
        for start, end in [(0, layout.total), (5, 12_000), (layout.total - 3, layout.total)]:
            sizes = [len(s.data) if isinstance(s, Literal) else s.end - s.begin for s in layout.segments(start, end)]
            assert all(size > 0 for size in sizes) and sum(sizes) == end - start

    def test_a_range_outside_gives_nothing_and_one_beyond_the_end_is_cut(self, layout: Layout) -> None:
        assert list(layout.segments(layout.total, layout.total + 10)) == []
        assert list(layout.segments(5, 5)) == [] and list(layout.segments(9, 3)) == []
        assert build(layout, start=layout.total - 4, end=layout.total + 99) == build(layout)[-4:]
        assert build(layout, start=-5, end=3) == build(layout)[:3], "a negative start is the start"

    def test_the_rasters_are_read_from_the_store_and_the_rest_comes_as_bytes(self, layout: Layout) -> None:
        kinds = [type(s) for s in layout.segments(0, layout.total)]
        assert kinds.count(Stored) == 2 and kinds[0] is Literal
        stored = [s for s in layout.segments(0, layout.total) if isinstance(s, Stored)]
        assert [(s.source, s.begin, s.end) for s in stored] == [
            ("result.tif", 0, len(RESULT)),
            ("mask.tif", 0, len(MASK)),
        ]


class TestAMemberOrANameThatIsRefused:
    @pytest.mark.parametrize(
        "name", ["", "/abs/result.tif", "a//b", "../x", "a/../b", "a\\b", "a/./b", "line\nbreak", "a/", "x" * 256]
    )
    def test_a_name_that_could_leave_the_folder_or_break_a_reader(self, name: str) -> None:
        with pytest.raises(ValueError, match="name of a member"):
            Member.of_bytes(name, b"x")

    def test_a_member_has_its_bytes_in_one_place(self) -> None:
        with pytest.raises(ValueError, match="either in memory or in the store"):
            Member("a", 1, 0)
        with pytest.raises(ValueError, match="either in memory or in the store"):
            Member("a", 1, 0, data=b"x", source="result.tif")

    @pytest.mark.parametrize(("size", "crc"), [(-1, 0), (1, -1), (1, 2**32)])
    def test_a_size_or_crc_out_of_range(self, size: int, crc: int) -> None:
        with pytest.raises(ValueError, match="not negative"):
            Member("a", size, crc, source="result.tif")

    def test_a_length_that_is_not_the_bytes(self) -> None:
        with pytest.raises(ValueError, match="length of its bytes"):
            Member("a", 3, 0, data=b"xy")

    def test_an_archive_needs_members_with_different_names_and_a_time_zone(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            Layout([], modified=MODIFIED)
        twice = [Member.of_bytes("a", b"1"), Member.of_bytes("a", b"2")]
        with pytest.raises(ValueError, match="all different"):
            Layout(twice, modified=MODIFIED)
        with pytest.raises(ValueError, match="timezone-aware"):
            Layout(members(), modified=datetime(2026, 3, 5))


ZEROS = bytes(1 << 20)
BIG = 4_500_000_000


class _Zeros(io.RawIOBase):
    """The archive as a file that reads through ``Layout`` and holds nothing: the big entry is zeros."""

    def __init__(self, layout: Layout, small: Mapping[str, bytes]) -> None:
        self.layout, self.small, self.position = layout, small, 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.position

    def seek(self, offset: int, whence: int = 0) -> int:
        base = {0: 0, 1: self.position, 2: self.layout.total}[whence]
        self.position = base + offset
        return self.position

    def read(self, size: int = -1) -> bytes:
        end = self.layout.total if size < 0 else min(self.position + size, self.layout.total)
        out = bytearray()
        for segment in self.layout.segments(self.position, end):
            if isinstance(segment, Literal):
                out += segment.data
            elif segment.source in self.small:
                out += self.small[segment.source][segment.begin : segment.end]
            else:
                out += (
                    ZEROS[: segment.end - segment.begin]
                    if segment.end - segment.begin <= len(ZEROS)
                    else bytes(segment.end - segment.begin)
                )
        self.position += len(out)
        return bytes(out)

    def readinto(self, buffer: memoryview) -> int:
        data = self.read(len(buffer))
        buffer[: len(data)] = data
        return len(data)


def _crc_of_zeros(count: int) -> int:
    crc = 0
    while count > 0:
        piece = min(count, len(ZEROS))
        crc = zlib.crc32(ZEROS[:piece], crc)
        count -= piece
    return crc


class TestZip64:
    def test_an_entry_over_4_gib_and_everything_behind_it_is_read_right_by_zipfile(self) -> None:
        """Plan §3.4 (b): sizes, offsets and the end records past 4 GiB, with no 4 GiB written anywhere."""
        big = Member.stored(f"{FOLDER}/result.tif", "result.tif", FileFacts(BIG, _crc_of_zeros(BIG)))
        small = Member.stored(f"{FOLDER}/mask.tif", "mask.tif", FileFacts(len(MASK), zlib.crc32(MASK)))
        layout = Layout([big, small, Member.of_bytes(f"{FOLDER}/recipe.json", RECIPE)], modified=MODIFIED)
        assert layout.total > BIG > 2**32
        archive = zipfile.ZipFile(_Zeros(layout, {"mask.tif": MASK}))  # type: ignore[arg-type]
        infos = {info.filename.rsplit("/", 1)[1]: info for info in archive.infolist()}
        assert infos["result.tif"].file_size == infos["result.tif"].compress_size == BIG
        assert infos["result.tif"].header_offset == 0 and infos["mask.tif"].header_offset > 2**32
        assert infos["recipe.json"].header_offset > infos["mask.tif"].header_offset
        assert archive.read(f"{FOLDER}/mask.tif") == MASK and archive.read(f"{FOLDER}/recipe.json") == RECIPE
        assert archive.testzip() is None, "every byte of the 4.5 GB entry, against the CRC the header carries"

    def test_the_crc_check_of_that_reader_would_notice_a_wrong_crc(self) -> None:
        """The counter-proof: the same layout with one CRC off by one is a bad archive to ``zipfile``."""
        wrong = Member.stored("x/mask.tif", "mask.tif", FileFacts(len(MASK), zlib.crc32(MASK) ^ 1))
        archive = zipfile.ZipFile(_Zeros(Layout([wrong], modified=MODIFIED), {"mask.tif": MASK}))  # type: ignore[arg-type]
        assert archive.testzip() == "x/mask.tif"

    @staticmethod
    def _local_header(size: int) -> tuple[int, int, int, int]:
        member = Member.stored("x/result.tif", "result.tif", FileFacts(size, 0))
        layout = Layout([member], modified=MODIFIED)
        header = (
            build(layout, {"result.tif": b""}, 0, 30)
            if size == 0
            else b"".join(s.data for s in layout.segments(0, 30) if isinstance(s, Literal))
        )
        _, version, _, _, _, _, _, _, csize, usize, _, extra = struct.unpack("<4sBBHHHHLLLHH", header)
        return version, csize, usize, extra

    def test_the_limit_is_ffffffff_not_before(self) -> None:
        assert self._local_header(0xFFFFFFFE) == (20, 0xFFFFFFFE, 0xFFFFFFFE, 0)
        assert self._local_header(0xFFFFFFFF) == (45, 0xFFFFFFFF, 0xFFFFFFFF, 20)

    @staticmethod
    def _tail(layout: Layout, count: int) -> bytes:
        return b"".join(s.data for s in layout.segments(layout.total - count, layout.total) if isinstance(s, Literal))

    def test_a_small_archive_has_no_zip64_records_and_a_big_one_has_them_before_the_end_record(
        self, layout: Layout
    ) -> None:
        assert b"PK\x06\x06" not in build(layout) and b"PK\x06\x07" not in build(layout)
        huge = Layout(
            [Member.stored("x/result.tif", "result.tif", FileFacts(0xFFFFFFFE, 0)), Member.of_bytes("x/b", b"b")],
            modified=MODIFIED,
        )
        tail = self._tail(huge, 22 + 20 + 56)
        assert tail[:4] == b"PK\x06\x06" and tail[56:60] == b"PK\x06\x07" and tail[76:80] == b"PK\x05\x06"
        directory_offset = struct.unpack("<Q", tail[48:56])[0]
        assert directory_offset > 0xFFFFFFFF
        assert struct.unpack("<L", tail[-6:-2])[0] == 0xFFFFFFFF, "the 32-bit offset says: look in the ZIP64 record"

    def test_the_offset_of_a_member_behind_4_gib_is_in_its_central_entry_only(self) -> None:
        big = Member.stored("x/a", "a", FileFacts(0xFFFFFFFE, 0))
        small = Member.of_bytes("x/b", b"b")
        layout = Layout([big, small], modified=MODIFIED)
        archive = zipfile.ZipFile(_Zeros(layout, {}))  # type: ignore[arg-type]
        assert archive.getinfo("x/b").header_offset > 0xFFFFFFFF
        assert archive.getinfo("x/a").file_size == 0xFFFFFFFE


class TestTheRangeHeader:
    @pytest.mark.parametrize(
        ("header", "expected"),
        [
            ("bytes=0-0", (0, 0)),
            ("bytes=0-99", (0, 99)),
            ("bytes=100-", (100, 999)),
            ("bytes=-100", (900, 999)),
            ("bytes=-5000", (0, 999)),
            ("bytes=999-999", (999, 999)),
            ("bytes=900-5000", (900, 999)),
            ("BYTES=1-2", (1, 2)),
            (" bytes= 1-2 ", (1, 2)),
        ],
    )
    def test_one_range_is_a_pair_cut_to_the_end(self, header: str, expected: tuple[int, int]) -> None:
        assert byte_range(header, 1000) == expected

    @pytest.mark.parametrize(
        "header",
        [None, "", "bytes=", "bytes=-", "bytes=abc", "bytes=1-2-3", "items=0-5", "0-5", "bytes=5-2", "bytes=0-1,5-6",
         "bytes=-5,7-", "bytes=+1-2", "bytes=1.5-2", "bytes=٣-٤", "bytes=" + "9" * 400 + "-", "bytes=0x1-0x5"],
    )  # fmt: skip
    def test_what_cannot_be_used_is_overheard_and_the_whole_is_sent(self, header: str | None) -> None:
        assert byte_range(header, 1000) is None

    @pytest.mark.parametrize("header", ["bytes=1000-", "bytes=1000-2000", "bytes=5000-", "bytes=-0"])
    def test_a_range_that_begins_behind_the_end_is_not_satisfiable(self, header: str) -> None:
        with pytest.raises(RangeNotSatisfiable):
            byte_range(header, 1000)


class TestReportedFiles:
    GOOD = {"files_meta": {"result.tif": {"bytes": 5, "crc32": 7}, "mask.tif": {"bytes": 0, "crc32": 0}}}
    NAMES = ("result.tif", "mask.tif")

    def test_the_facts_of_both_files(self) -> None:
        assert reported_files(self.GOOD, self.NAMES) == {"result.tif": FileFacts(5, 7), "mask.tif": FileFacts(0, 0)}

    @pytest.mark.parametrize(
        "result",
        [
            None,
            {},
            {"files_meta": None},
            {"files_meta": []},
            {"files_meta": {"result.tif": {"bytes": 5, "crc32": 7}}},
            {"files_meta": {"result.tif": {"bytes": 5, "crc32": 7}, "mask.tif": "x"}},
            {"files_meta": {"result.tif": {"bytes": -1, "crc32": 7}, "mask.tif": {"bytes": 0, "crc32": 0}}},
            {"files_meta": {"result.tif": {"bytes": 5, "crc32": 2**32}, "mask.tif": {"bytes": 0, "crc32": 0}}},
            {"files_meta": {"result.tif": {"bytes": "5", "crc32": 7}, "mask.tif": {"bytes": 0, "crc32": 0}}},
            {"files_meta": {"result.tif": {"bytes": True, "crc32": 7}, "mask.tif": {"bytes": 0, "crc32": 0}}},
            {"files_meta": {"result.tif": {"bytes": 5.0, "crc32": 7}, "mask.tif": {"bytes": 0, "crc32": 0}}},
        ],
    )
    def test_anything_less_than_both_files_with_sound_numbers_is_no_report(self, result: object) -> None:
        assert reported_files(result, self.NAMES) is None  # type: ignore[arg-type]

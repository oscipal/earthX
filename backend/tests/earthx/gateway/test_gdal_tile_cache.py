"""The tile profile fetches each byte of a COG once; the base profile fetches it again (NM4-26 §8–§10, §18).

A view of the map reads neighbouring tiles of the same file, and those share blocks. With
``GDAL_HTTP_MULTIRANGE=YES`` the GeoTIFF driver fetches the blocks of one read in parallel through
``VSICurlHandle::ReadMultiRange``, which neither reads nor fills GDAL's ``/vsicurl/`` region cache
(GDAL 3.12.2, ``port/cpl_vsil_curl.cpp`` l. 2507–2772): the next tile fetches the same blocks again.
``SERIAL`` goes through ``VSICurlHandle::Read()``, which does both (l. 2361, 2402, 2350).

These tests read a small synthetic GeoTIFF from a range server on the loopback address that counts what
it sends — GDAL does its own sockets, so the count is on the server's side. The file is a few MB, far below
the 16 MB GDAL starts with, and every test reads its own URL so that nothing an earlier test cached can help.

The two tests that expect a cache hit read in a fresh ``spawn`` process, the way the `tiler` starts: the
cache is one per process, GDAL fixes its size at its first use, and under pytest-xdist the tests that ran
before in the same worker change from run to run. Once (NM4-23) a second read of the same window there
fetched every byte again. In a process of its own nothing but the test reads, and its size is the profile's.
"""

from __future__ import annotations

import multiprocessing
import re
import threading
import uuid
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import rasterio
import rasterio.session
from rasterio.transform import from_origin
from rasterio.windows import Window

from earthx.gateway import Policy
from earthx.gateway.gdal import crop_gdal_options, gdal_options, tile_gdal_options

POLICY = Policy(allowed_hosts=frozenset())
BLOCK = 256

# Four blocks each; the second window shares one block with the first (column 1, row 1).
FIRST = Window(0, 0, 2 * BLOCK, 2 * BLOCK)
SECOND = Window(BLOCK, BLOCK, 2 * BLOCK, 2 * BLOCK)


class RangeServer:
    """Serves one file over HTTP/1.1 with single ``Range`` requests and records every range it sends."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.sent: list[tuple[int, int]] = []  # [start, end), in the order they were served
        self._lock = threading.Lock()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: object) -> None:
                pass

            def _headers(self, status: int, start: int, end: int) -> None:
                self.send_response(status)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(end - start))
                if status == 206:
                    self.send_header("Content-Range", f"bytes {start}-{end - 1}/{len(owner.data)}")
                self.end_headers()

            def do_HEAD(self) -> None:
                self._headers(200, 0, len(owner.data))

            def do_GET(self) -> None:
                found = re.fullmatch(r"bytes=(\d+)-(\d*)", self.headers.get("Range", ""))
                if found is None:
                    start, end, status = 0, len(owner.data), 200
                else:
                    start = int(found.group(1))
                    end = min(int(found.group(2) or len(owner.data) - 1) + 1, len(owner.data))
                    status = 206
                if start >= len(owner.data):
                    self.send_response(416)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                # Counted before it goes out: once GDAL has the bytes, the count has them too.
                with owner._lock:
                    owner.sent.append((start, end))
                self._headers(status, start, end)
                self.wfile.write(owner.data[start:end])

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.path = f"{uuid.uuid4().hex}.tif"  # a URL of its own, so no earlier test's cache can answer
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def vsicurl_path(self) -> str:
        return f"/vsicurl/http://127.0.0.1:{self.httpd.server_address[1]}/{self.path}"

    @property
    def bytes_sent(self) -> int:
        with self._lock:
            return sum(end - start for start, end in self.sent)

    @property
    def bytes_distinct(self) -> int:
        with self._lock:
            merged: list[list[int]] = []
            for start, end in sorted(self.sent):
                if merged and start <= merged[-1][1]:
                    merged[-1][1] = max(merged[-1][1], end)
                else:
                    merged.append([start, end])
        return sum(end - start for start, end in merged)


@pytest.fixture
def cog_bytes(tmp_path: Path) -> bytes:
    """1024×1024 uint16 noise in 256×256 DEFLATE blocks: a few MB, each block well above GDAL's 16 KB chunk."""
    path = tmp_path / "noise.tif"
    noise = np.random.default_rng(7).integers(0, 65535, size=(1024, 1024), dtype=np.uint16)
    profile = {
        "driver": "GTiff",
        "width": 1024,
        "height": 1024,
        "count": 1,
        "dtype": "uint16",
        "tiled": True,
        "blockxsize": BLOCK,
        "blockysize": BLOCK,
        "compress": "deflate",
        "crs": "EPSG:32632",
        "transform": from_origin(500000.0, 5000000.0, 10.0, 10.0),
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(noise, 1)
    return path.read_bytes()


@pytest.fixture
def server(cog_bytes: bytes) -> Iterator[RangeServer]:
    served = RangeServer(cog_bytes)
    served.thread.start()
    try:
        yield served
    finally:
        served.httpd.shutdown()
        served.httpd.server_close()
        served.thread.join(timeout=5)


def read_windows(server: RangeServer, options: dict[str, str], windows: list[Window]) -> list[np.ndarray]:
    """Each window read through a file opened afresh, the way every tile opens its own."""
    pixels = []
    with rasterio.Env(**options):
        for window in windows:
            with rasterio.open(server.vsicurl_path) as src:
                pixels.append(src.read(1, window=window))
    return pixels


def _read_batches(path: str, options: dict[str, str], batches: list[list[Window]], conn: Any) -> None:
    """In a fresh process: each batch read as `read_windows` reads it, then a word to the test and a wait for its answer."""
    rasterio.session.boto3 = None  # as in the image and in the test process (tests/conftest.py)
    try:
        for batch in batches:
            with rasterio.Env(**options):
                for window in batch:
                    with rasterio.open(path) as src:
                        src.read(1, window=window)
            conn.send("read")
            conn.recv()
    except Exception as error:  # noqa: BLE001 - handed to the test, which fails with it
        conn.send(f"{type(error).__name__}: {error}")
    finally:
        conn.close()


def read_in_a_fresh_process(server: RangeServer, options: dict[str, str], batches: list[list[Window]]) -> list[int]:
    """The bytes the server sent after each batch; the batches read one after another in one new process."""
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(target=_read_batches, args=(server.vsicurl_path, options, batches, child))
    process.start()
    child.close()
    sent = []
    try:
        for _ in batches:
            assert parent.poll(60), "the reading process did not answer"
            word = parent.recv()
            assert word == "read", word
            sent.append(server.bytes_sent)
            parent.send("go on")
    finally:
        process.join(60)
        process.kill()
    return sent


def test_the_tile_profile_fetches_each_byte_once(server: RangeServer) -> None:
    read_in_a_fresh_process(server, tile_gdal_options(POLICY), [[FIRST, SECOND]])
    assert server.bytes_sent > 0
    assert server.bytes_sent == server.bytes_distinct


def test_the_tile_profile_asks_for_nothing_when_the_same_window_is_read_again(server: RangeServer) -> None:
    first, second = read_in_a_fresh_process(server, tile_gdal_options(POLICY), [[FIRST], [FIRST]])
    assert first > 0
    assert second == first


def test_the_base_profile_fetches_the_blocks_of_a_window_again(server: RangeServer) -> None:
    """The regression the tile profile fixes: the parallel read leaves nothing in the cache."""
    read_windows(server, gdal_options(POLICY), [FIRST, SECOND])
    assert server.bytes_sent > server.bytes_distinct


def test_the_crop_profile_keeps_the_parallel_reads_of_the_base(server: RangeServer) -> None:
    read_windows(server, crop_gdal_options(POLICY), [FIRST, SECOND])
    assert server.bytes_sent > server.bytes_distinct


def test_both_profiles_deliver_the_same_pixels(server: RangeServer, cog_bytes: bytes) -> None:
    serial = read_windows(server, tile_gdal_options(POLICY), [FIRST, SECOND])
    other = RangeServer(cog_bytes)
    other.thread.start()
    try:
        parallel = read_windows(other, crop_gdal_options(POLICY), [FIRST, SECOND])
    finally:
        other.httpd.shutdown()
        other.httpd.server_close()
        other.thread.join(timeout=5)
    for left, right in zip(serial, parallel, strict=True):
        assert left.dtype == right.dtype and np.array_equal(left, right)

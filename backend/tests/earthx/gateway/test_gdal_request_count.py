"""Every request GDAL makes to a source is counted, the size probe and the retries included (M5-37, Otto 17.11.2026).

The pyramid build charges the requests of each file to the host's shared turn; before M5-37 PR 2 the count saw only
GDAL's ``Downloading`` lines and missed the ``HEAD`` with which GDAL learns a file's size, so the source saw two requests
for each one charged. These tests read a small COG from a server on the loopback address that counts every request it
gets, whatever it answers, and compare that with what :func:`counting_gdal_lines` counted: when all goes well, when the
size probe fails and GDAL retries it, when a range read fails and GDAL retries it, and with
``CPL_VSIL_CURL_USE_HEAD=NO``, which replaces the ``HEAD`` with a ``GET`` that GDAL breaks off. Every test reads a URL of
its own, so that nothing GDAL cached in this process can answer for it.
"""

from __future__ import annotations

import re
import threading
import uuid
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.errors import RasterioIOError
from rasterio.transform import from_origin
from rasterio.windows import Window

from earthx.gateway import Policy
from earthx.gateway.gdal import count_downloads, counting_gdal_lines, gdal_options

POLICY = Policy(allowed_hosts=frozenset())


class CountingSource:
    """Serves one file with ``HEAD`` and single ranges; counts every request on arrival; answers 503 when told to."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.requests: list[str] = []
        self.failing = False
        self.fail_ranges = False
        self._lock = threading.Lock()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: object) -> None:
                pass

            def _arrived(self) -> bool:
                with owner._lock:
                    owner.requests.append(self.command)
                ranged = bool(self.headers.get("Range"))
                if owner.failing or (owner.fail_ranges and ranged):
                    self.send_response(503)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return False
                return True

            def do_HEAD(self) -> None:
                if self._arrived():
                    self.send_response(200)
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Content-Length", str(len(owner.data)))
                    self.end_headers()

            def do_GET(self) -> None:
                if not self._arrived():
                    return
                found = re.fullmatch(r"bytes=(\d+)-(\d*)", self.headers.get("Range", ""))
                start, end, status = 0, len(owner.data), 200
                if found is not None:
                    start = int(found.group(1))
                    end = min(int(found.group(2) or len(owner.data) - 1) + 1, len(owner.data))
                    status = 206
                self.send_response(status)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(end - start))
                if status == 206:
                    self.send_header("Content-Range", f"bytes {start}-{end - 1}/{len(owner.data)}")
                self.end_headers()
                try:
                    self.wfile.write(owner.data[start:end])
                except (BrokenPipeError, ConnectionResetError):
                    self.close_connection = True

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def url(self) -> str:
        return f"/vsicurl/http://127.0.0.1:{self.server.server_address[1]}/{uuid.uuid4().hex}/b.tif"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture(scope="module")
def source(tmp_path_factory: pytest.TempPathFactory) -> Iterator[CountingSource]:
    path = Path(tmp_path_factory.mktemp("count")) / "b.tif"
    profile = {
        "driver": "GTiff", "width": 1024, "height": 1024, "count": 1, "dtype": "uint16", "crs": "EPSG:32632",
        "transform": from_origin(600000, 5300000, 10, 10), "tiled": True, "blockxsize": 256, "blockysize": 256,
        "compress": "deflate",
    }  # fmt: skip
    rng = np.random.default_rng(37)
    with rasterio.open(path, "w", **profile) as target:
        target.write(rng.integers(0, 4000, (1024, 1024), dtype="uint16"), 1)
    served = CountingSource(path.read_bytes())
    yield served
    served.close()


def _read(source: CountingSource, *, fail: str = "", **extra: str) -> tuple[int, int]:
    """Open and read a window of a fresh URL; requests counted by GDAL's lines, and requests at the source."""
    url = source.url()
    source.requests.clear()
    source.failing = fail == "open"
    source.fail_ranges = False
    options = {**gdal_options(POLICY), "GDAL_HTTP_RETRY_DELAY": "0.05", "CPL_DEBUG": "ON", **extra}
    with counting_gdal_lines(own_thread_only=True) as counter:
        try:
            with rasterio.Env(**options), rasterio.open(url) as dataset:
                source.fail_ranges = fail == "read"
                dataset.read(1, window=Window(256, 256, 512, 512))
        except RasterioIOError:
            if not fail:
                raise
        counted = counter.take()[0]
    source.failing = source.fail_ranges = False
    return counted, len(source.requests)


def test_a_read_that_works_counts_the_size_probe_and_every_range(source: CountingSource) -> None:
    counted, served = _read(source)
    assert served >= 2
    assert counted == served


def test_a_size_probe_that_fails_counts_each_of_its_attempts(source: CountingSource) -> None:
    counted, served = _read(source, fail="open")
    assert served == 3, "the first attempt and GDAL_HTTP_MAX_RETRY = 2"
    assert counted == served


def test_a_range_read_that_fails_counts_each_of_its_attempts(source: CountingSource) -> None:
    counted, served = _read(source, fail="read")
    assert served > 3
    assert counted == served


def test_without_head_the_get_gdal_breaks_off_is_counted_too(source: CountingSource) -> None:
    """``CPL_VSIL_CURL_USE_HEAD=NO`` saves no request: GDAL asks with a ``GET`` instead and breaks it off."""
    counted, served = _read(source, CPL_VSIL_CURL_USE_HEAD="NO")
    assert "HEAD" not in source.requests
    assert counted == served


# --- the rule on lines as GDAL 3.12 writes them (addresses replaced)

OK = [
    "CPLE_None in VSICURL: GetFileSize(<url>)=1000  response_code=200",
    "CPLE_None in VSICURL: Downloading 0-32767 (<url>)...",
    "CPLE_None in VSICURL: Got response_code=206",
    "VSICURL: Downloading 600-799 (<url>)...",
    "VSICURL: Download completed",
]
SIZE_RETRIED = [
    "CPLE_AppDefined in HTTP error code: 503 - <url>. Retrying again in 1.0 secs",
    "CPLE_AppDefined in HTTP error code: 503 - <url>. Retrying again in 2.4 secs",
    "CPLE_None in VSICURL: GetFileSize(<url>)=0  response_code=503",
]
RANGE_RETRIED = [
    "VSICURL: Downloading 600-799 (<url>)...",
    "VSICURL: Got response_code=503",
    "CPLE_AppDefined:HTTP error code: 503 - <url>. Retrying again in 1.0 secs",
    "VSICURL: Downloading 600-799 (<url>)...",
    "VSICURL: Got response_code=503",
]


@pytest.mark.parametrize(
    ("lines", "requests"),
    [
        (OK, 3),
        (SIZE_RETRIED, 3),
        (RANGE_RETRIED, 2),
        (OK + SIZE_RETRIED, 6),  # a second file opened after a range read that ended well
        ([*RANGE_RETRIED, "VSICURL: Got response_code=206", *SIZE_RETRIED], 5),
        (["VSICURL: Download completed", "GDAL: GDALClose(<url>)"], 0),
        (["VSICURL: Downloading 600-799 (<url>)...", *SIZE_RETRIED], 2),  # the retries follow a read under way
    ],
)
def test_each_request_is_one_line_or_one_retry_of_a_size_probe(lines: list[str], requests: int) -> None:
    assert count_downloads(lines)[0] == requests


def test_the_bytes_are_those_of_the_ranges_only() -> None:
    assert count_downloads(OK)[1] == 32768 + 200

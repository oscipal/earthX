"""How a failed read of a source is named (adr/0013 §5.6 and M10, plan M4-08a F1).

Two families: the classes `gateway` raises with the status attached, and the one
`RasterioIOError` GDAL raises for every cause with the status only in its text. The
second is read against a local server that answers `503`, `404`, `429` and not at
all, so a GDAL release that words the text differently breaks this test and not
the retry rule silently (adr/0013 §5.6, "Anmerkung").
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import rasterio
from rasterio.errors import RasterioIOError

from earthx.gateway import (
    AddressRejected,
    ResponseTooLarge,
    TooManyRedirects,
    UpstreamError,
    UpstreamTimeout,
    UpstreamUnreachable,
    UrlRejected,
    UrlTooLong,
)
from earthx.readers import AssetRejected, source_failure_kind
from earthx.readers.failures import SOURCE_KINDS


class TestGatewayClasses:
    @pytest.mark.parametrize(
        ("error", "kind"),
        [
            (UpstreamTimeout("slow"), "source_timeout"),
            (UpstreamUnreachable("refused"), "source_unreachable"),
            (UpstreamError(500), "source_5xx"),
            (UpstreamError(503, "x"), "source_5xx"),
            (UpstreamError(429), "source_429"),
            (UpstreamError(404), "source_4xx"),
            (UpstreamError(403), "source_4xx"),
            (UpstreamError(400), "source_4xx"),
            (UrlRejected("host not allowed"), "rejected"),
            (AssetRejected("a key"), "rejected"),
            (AddressRejected("private", host="x.example.invalid"), "rejected"),
            (UrlTooLong(9000, 2048), "rejected"),
            (ResponseTooLarge(10, 5), "rejected"),
            (TooManyRedirects(5), "rejected"),
        ],
    )
    def test_each_class_has_its_name(self, error: BaseException, kind: str) -> None:
        assert source_failure_kind(error) == kind

    def test_a_timeout_is_not_taken_for_the_unreachable_class_it_derives_from(self) -> None:
        assert source_failure_kind(UpstreamTimeout("slow")) == "source_timeout"

    def test_a_redirect_status_names_nothing(self) -> None:
        assert source_failure_kind(UpstreamError(302)) is None


class TestWhatIsNotASourceFailure:
    @pytest.mark.parametrize(
        "error",
        [
            ValueError("HTTP response code: 503"),
            RuntimeError("CURL error: Operation timed out"),
            KeyError("x"),
            RasterioIOError("not recognized as a supported file format"),
            RasterioIOError("HTTP response code: 302"),
            RasterioIOError(""),
        ],
    )
    def test_any_other_error_names_nothing(self, error: BaseException) -> None:
        assert source_failure_kind(error) is None


class TestTheChain:
    def test_a_failure_wrapped_by_another_is_found_through_its_cause(self) -> None:
        try:
            try:
                raise UpstreamError(503)
            except UpstreamError as inner:
                raise RuntimeError("the store could not be read") from inner
        except RuntimeError as outer:
            assert source_failure_kind(outer) == "source_5xx"

    def test_and_through_the_context_of_an_error_raised_while_handling_it(self) -> None:
        try:
            try:
                raise UpstreamTimeout("slow")
            except UpstreamTimeout:
                raise KeyError("chunk") from None
        except KeyError as outer:
            outer.__context__ = UpstreamTimeout("slow")
            assert source_failure_kind(outer) == "source_timeout"

    def test_a_cycle_ends(self) -> None:
        first, second = RuntimeError("a"), RuntimeError("b")
        first.__cause__ = second
        second.__cause__ = first
        assert source_failure_kind(first) is None

    def test_the_nearest_failure_wins(self) -> None:
        outer = UpstreamError(404)
        outer.__cause__ = UpstreamTimeout("slow")
        assert source_failure_kind(outer) == "source_4xx"


class _Answers(BaseHTTPRequestHandler):
    """`/503/x.tif` answers 503, `/404/…` 404, `/429/…` 429, `/silent/…` not at all."""

    release = threading.Event()

    def _answer(self) -> None:
        code = self.path.split("/")[1]
        if code == "silent":
            self.release.wait(10)
            return
        self.send_response(int(code))
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_GET = do_HEAD = _answer

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def server() -> Iterator[str]:
    _Answers.release.clear()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Answers)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        _Answers.release.set()
        httpd.shutdown()
        httpd.server_close()


def _read(base: str, code: str) -> RasterioIOError:
    """The error GDAL raises, with the time limits `gateway/gdal.py` sets, shortened."""
    options = {
        "GDAL_HTTP_TIMEOUT": "1",
        "GDAL_HTTP_CONNECTTIMEOUT": "1",
        "GDAL_HTTP_MAX_RETRY": "0",
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    }
    with rasterio.Env(**options), pytest.raises(RasterioIOError) as caught:
        rasterio.open(f"/vsicurl/{base}/{code}/x.tif")
    return caught.value


class TestWhatGdalSays:
    """The texts measured in adr/0013 M10, GDAL 3.12.2: same class, status only in the text."""

    @pytest.mark.parametrize(
        ("code", "kind"),
        [("503", "source_5xx"), ("500", "source_5xx"), ("404", "source_4xx"), ("429", "source_429")],
    )
    def test_the_status_in_the_text_names_the_failure(self, server: str, code: str, kind: str) -> None:
        error = _read(server, code)
        assert f"HTTP response code: {code}" in str(error)
        assert source_failure_kind(error) == kind

    def test_no_answer_is_a_timeout(self, server: str) -> None:
        error = _read(server, "silent")
        assert "timed out" in str(error)
        assert source_failure_kind(error) == "source_timeout"


def test_the_names_are_the_declared_ones() -> None:
    assert {
        "source_timeout",
        "source_5xx",
        "source_429",
        "source_4xx",
        "source_unreachable",
        "source_georeference",
        "rejected",
    } == SOURCE_KINDS


class TestTheTransportErrorsOfGdal:
    """The errors libcurl reports through GDAL are the source not answering (a retry can help), not an unknown failure."""

    @pytest.mark.parametrize(
        "text",
        [
            "CURL error: Connection reset by peer",
            "CURL error: SSL connect error",
            "CURL error: Could not resolve host: bucket.example.invalid",
            "CURL error: Recv failure: Connection reset by peer",
            "HTTP response code on https://bucket.example.invalid/a.tif: 0",
            "HTTP response code: 0",
        ],
    )
    def test_they_are_source_unreachable(self, text: str) -> None:
        from earthx.readers import source_failure_kind

        assert source_failure_kind(RasterioIOError(text)) == "source_unreachable"

    def test_a_timeout_and_a_status_keep_their_own_names(self) -> None:
        from earthx.readers import source_failure_kind

        assert source_failure_kind(RasterioIOError("CURL error: Operation timed out after 30000 ms")) == "source_timeout"
        assert source_failure_kind(RasterioIOError("HTTP response code: 503")) == "source_5xx"

    @pytest.mark.parametrize("text", ["not recognized as a supported file format", "HTTP response code: 302", "no such file"])
    def test_a_file_problem_is_not_the_source_not_answering(self, text: str) -> None:
        from earthx.readers import source_failure_kind

        assert source_failure_kind(RasterioIOError(text)) is None


class TestRetryAfter:
    def test_it_reads_the_seconds_a_failure_carries_even_from_its_cause(self) -> None:
        from earthx.readers import retry_after

        inner = RuntimeError("slow down")
        inner.retry_after = 7  # type: ignore[attr-defined]
        try:
            raise ValueError("outer") from inner
        except ValueError as outer:
            assert retry_after(outer) == 7.0

    def test_it_is_capped_and_ignores_what_is_no_wait(self) -> None:
        from earthx.readers import retry_after
        from earthx.readers.failures import RETRY_AFTER_CAP_S

        for value, expected in ((86_400, RETRY_AFTER_CAP_S), (-1, None), (True, None), ("7", None)):
            error = RuntimeError("x")
            error.retry_after = value  # type: ignore[attr-defined]
            assert retry_after(error) == expected
        assert retry_after(RuntimeError("no header")) is None

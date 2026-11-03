"""The script that plays a band download (`scripts/try-band-download.ps1`, NM4-75), read for what it asks of whom.

Otto's run found "[OK] Item gefunden", then "[FEHLER] Download: HTTP 404": the script sent the download to the api (8000),
but ``POST /collections/{dataset}/download`` is a route of the tiler (8001), which the viewer reaches through its proxy at
``/collections``. These tests pin the split in the two real apps and in the script; the script itself runs only
where PowerShell is installed (the CI image has it).
"""

from __future__ import annotations

import http.server
import io
import re
import shutil
import subprocess
import threading
import zipfile
from pathlib import Path

import pytest

from earthx.api import main as api_main
from earthx.api import tiler as tiler_main

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "try-band-download.ps1"
DOWNLOAD = "/collections/{dataset}/download"
SEARCH = "/stac/search"


def _text() -> str:
    return SCRIPT.read_bytes().removeprefix(b"\xef\xbb\xbf").decode("utf-8")


def test_the_download_is_a_route_of_the_tiler_and_not_of_the_api() -> None:
    assert DOWNLOAD in tiler_main.app.openapi()["paths"]
    assert DOWNLOAD not in api_main.app.openapi()["paths"]  # asked of the api it is a 404, as in Otto's run
    assert SEARCH in api_main.app.openapi()["paths"] and SEARCH not in tiler_main.app.openapi()["paths"]


def test_the_viewer_reaches_the_two_the_same_way() -> None:
    config = (REPO / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    assert re.search(r"'/collections':\s*\{\s*target:\s*tilerTarget", config)
    assert re.search(r"'/stac':\s*\{\s*target:\s*apiTarget", config)
    compose = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    assert '"8001:8000"' in compose and '"8000:8000"' in compose  # the tiler on 8001, the api on 8000


def test_the_script_searches_at_the_api_and_downloads_at_the_tiler() -> None:
    text = _text()
    assert "[string]$TilerUrl = 'http://localhost:8001'" in text and "[string]$BaseUrl = 'http://localhost:8000'" in text
    assert '"$BaseUrl/stac/search"' in text
    assert '"$TilerUrl/collections/$Dataset/download"' in text
    assert '"$BaseUrl/collections' not in text


def test_a_failure_names_method_service_and_path_pattern_but_no_identifier_or_body() -> None:
    text = _text()
    assert "Show-Failure 'Download' $answer 'tiler' '/collections/{dataset}/download'" in text
    assert "Show-Failure 'Item suchen' $found 'api' '/stac/search'" in text
    # The text of an answer can name a scene; it is never part of the printed result, only of -Verbose.
    assert not re.search(r"Write-Result[^\n]*\$\(?\$?(answer|found)\.Text", text)
    assert "Write-Verbose" in text
    assert not re.search(r'Write-(Result|Host)[^\n]*\$(itemId|aoi|body)\b', text)


class _Fake(http.server.BaseHTTPRequestHandler):
    """A platform of two services: the api answers the search and 404s the download, the tiler the other way round."""

    service = ""

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        if self.service == "api" and self.path == SEARCH:
            body = b'{"features": [{"id": "SCENE_FOR_THE_TEST"}]}'
            self._answer(200, "application/geo+json", body)
        elif self.service == "tiler" and re.fullmatch(r"/collections/[^/]+/download", self.path):
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w") as zipped:
                zipped.writestr("exports/B04_red_10m.tif", b"II*\x00" + b"\x00" * 12)
                zipped.writestr("exports/BANDS.txt", "EarthX band list\n\nFile: exports/B04_red_10m.tif\n")
                zipped.writestr("ATTRIBUTION.txt", "x")
                zipped.writestr("aoi.geojson", "{}")
            self._answer(200, "application/zip", archive.getvalue())
        else:
            self._answer(404, "application/json", b'{"detail": "item SCENE_FOR_THE_TEST not found"}')

    def _answer(self, status: int, kind: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


def _serve(service: str) -> tuple[http.server.ThreadingHTTPServer, int]:
    handler = type("Handler", (_Fake,), {"service": service})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def _run(tmp_path: Path, api_port: int, tiler_port: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "pwsh", "-NoProfile", "-File", str(SCRIPT),
            "-BaseUrl", f"http://127.0.0.1:{api_port}", "-TilerUrl", f"http://127.0.0.1:{tiler_port}",
            "-OutputDir", str(tmp_path / "out"),
        ],  # fmt: skip
        capture_output=True, text=True, timeout=120, cwd=tmp_path,
    )  # fmt: skip


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell (pwsh) is not installed; the CI image has it")
class TestAgainstAFakePlatform:
    def test_with_the_download_at_the_tiler_the_run_passes(self, tmp_path: Path) -> None:
        api, api_port = _serve("api")
        tiler, tiler_port = _serve("tiler")
        try:
            result = _run(tmp_path, api_port, tiler_port)
        finally:
            api.shutdown()
            tiler.shutdown()
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Alles OK" in result.stdout

    def test_with_the_download_sent_to_the_api_the_404_names_only_the_route_pattern(self, tmp_path: Path) -> None:
        api, api_port = _serve("api")
        try:
            result = _run(tmp_path, api_port, api_port)  # Otto's run: both addresses are the api
        finally:
            api.shutdown()
        output = result.stdout + result.stderr
        assert result.returncode != 0
        assert "HTTP 404 von POST tiler /collections/{dataset}/download" in output
        assert "SCENE_FOR_THE_TEST" not in output and "127.0.0.1" not in output.split("HTTP 404")[1].splitlines()[0]

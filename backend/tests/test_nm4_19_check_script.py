"""The check script of NM4-19 (`scripts/checks/nm4-19-statistics.ps1`, plan section 17.1).

The script is for Windows PowerShell 5.1 on Otto's machine. Here it is read for what 5.1 cannot take, and, where
PowerShell is installed (CI's Ubuntu image has `pwsh`; a plain cloud session may not, and then that class is skipped
with its reason), run against a small local platform: one HTTP server playing the search, the tiler's route, the job
API and its results, and a `docker` on the PATH that prints the tiler's log. pwsh 7 is not 5.1; what only 5.1 would
show is named in the PR.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "checks" / "nm4-19-statistics.ps1"
PWSH = shutil.which("pwsh")
ITEM = "S2TEST_ITEM_7E46N"
JOB = "JOBIDOFTHETEST0000000A"
STATISTICS = {
    "minimum": -0.07470075786113739,
    "maximum": 0.9391635060310364,
    "mean": 0.5850807751705179,
    "stddev": 0.2861072847580098,
    "count": 530133,
    "valid_percent": 100.0,
    "percentile_2": 0.123046875,
    "percentile_98": 0.9062499403953552,
}
#: The footprint of the scene: a square of one degree around 7 E / 46 N.
FOOTPRINT = {"type": "Polygon", "coordinates": [[[6.5, 45.5], [7.5, 45.5], [7.5, 46.5], [6.5, 46.5], [6.5, 45.5]]]}
LOG = '{"logger": "earthx.request", "method": "POST", "path": "/collections/sentinel-2-c1-l2a/statistics", "status": 200}\n'
LOG += '{"timestamp": "2026-10-28T12:46:06.973712+00:00", "message": "area statistics measured", "factor": 1}\n'


class TestWhatWindowsPowerShell51Takes:
    def test_the_script_is_ascii_so_5_1_reads_it_the_same_without_a_bom(self) -> None:
        assert SCRIPT.read_bytes().isascii()

    @pytest.mark.parametrize(
        "pattern",
        [
            r"-SkipHttpErrorCheck",
            r"-StatusCodeVariable",
            r"-ResponseHeadersVariable",
            r"-AsHashtable",
            r"ConvertFrom-Json\s+-Depth",
            r"Join-String",
            r"ForEach-Object\s+-Parallel",
            r"\?\?",
            r"\?\.",
            r"&&",
            r"\|\|",
            r"\$IsWindows",
            r"-Form\b",
        ],
    )
    def test_no_syntax_or_parameter_of_powershell_7(self, pattern: str) -> None:
        assert not re.search(pattern, SCRIPT.read_text(encoding="ascii"))

    def test_bodies_go_as_bytes_and_errors_are_caught(self) -> None:
        text = SCRIPT.read_text(encoding="ascii")
        assert "[System.Text.Encoding]::UTF8.GetBytes($Body)" in text
        assert "$_.Exception.Response" in text and "UseBasicParsing = $true" in text


class Platform:
    """What the local platform answers, and what it was asked."""

    def __init__(self) -> None:
        self.job_statistics: dict[str, Any] = dict(reversed(list(STATISTICS.items())))  # jsonb orders keys its own way
        self.status = "successful"
        self.asked: list[tuple[str, str]] = []


@contextmanager
def platform(state: Platform) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def _answer(self, status: int, body: dict[str, Any] | None) -> None:
            content = b"" if body is None else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/geo+json" if self.path == "/stac/search" else "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self) -> None:
            state.asked.append(("GET", self.path))
            if self.path == f"/processing/jobs/{JOB}":
                self._answer(200, {"jobID": JOB, "status": state.status})
            elif self.path == f"/processing/jobs/{JOB}/results":
                self._answer(200, {"result": {"properties": {"bands": [{"name": "band_math", "statistics": state.job_statistics}]}}})
            elif self.path.endswith("/statistics"):
                self._answer(405, {"detail": "Method Not Allowed"})
            else:
                self._answer(404, {"detail": "Not Found"})

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            state.asked.append(("POST", self.path))
            if self.path == "/stac/search":
                feature = {"id": ITEM, "type": "Feature", "geometry": FOOTPRINT, "properties": {"eo:cloud_cover": 2.5}}
                self._answer(200, {"type": "FeatureCollection", "features": [feature]})
            elif self.path == "/collections/sentinel-2-c1-l2a/statistics":
                if "aoi" not in body:
                    self._answer(422, {"detail": "aoi: the area is measured for an order with an AOI only"})
                    return
                ring = body["aoi"]["coordinates"][0]
                small = ring[1][0] - ring[0][0] < 0.1
                self._answer(
                    200,
                    {"bands": [{"name": "band_math", "statistics": STATISTICS}], "exact": small, "factor": 1 if small else 2},
                )
            elif self.path == "/processing/processes/recipe/execution":
                self._answer(201, {"jobID": JOB, "status": "accepted"})
            else:
                self._answer(404, {"detail": "Not Found"})

        def log_message(self, *args: Any) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.skipif(PWSH is None, reason="PowerShell (pwsh) is not installed; the CI image has it")
class TestTheScriptItself:
    def run(self, tmp_path: Path, state: Platform, log: str = LOG) -> tuple[int, str]:
        """The script against the local platform, with a `docker` that prints ``log``."""
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (tmp_path / "tiler.log").write_text(log, encoding="utf-8")
        docker = bin_dir / "docker"
        docker.write_text(f'#!/bin/sh\ncat "{tmp_path / "tiler.log"}"\n', encoding="utf-8")
        docker.chmod(0o755)
        environment = {
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "DOTNET_SYSTEM_GLOBALIZATION_INVARIANT": "1",
            "NO_COLOR": "1",
        }
        with platform(state) as base:
            process = subprocess.run(
                [PWSH or "pwsh", "-NoProfile", "-File", str(SCRIPT), "-ApiUrl", base, "-TilerUrl", base, "-JobTimeoutSeconds", "30"],
                capture_output=True,
                env=environment,
                timeout=180,
                check=False,
            )
        return process.returncode, (process.stdout + process.stderr).decode("utf-8", errors="replace")

    def test_all_pass_against_a_platform_that_answers_as_it_should(self, tmp_path: Path) -> None:
        state = Platform()
        code, output = self.run(tmp_path, state)
        assert code == 0, output
        assert "ALL PASS" in output and "FAIL" not in output
        assert ("POST", "/processing/processes/recipe/execution") in state.asked

    def test_it_prints_no_item_job_id_or_coordinate(self, tmp_path: Path) -> None:
        code, output = self.run(tmp_path, Platform())
        assert code == 0, output
        assert ITEM not in output and JOB not in output
        assert not re.search(r"(?<![0-9])(7\.0137|46\.0246|6\.9737|7\.0537|45\.9846|46\.0646|6\.8637|7\.1637)", output)

    def test_a_job_that_counts_otherwise_fails_with_the_field(self, tmp_path: Path) -> None:
        state = Platform()
        state.job_statistics = {**STATISTICS, "percentile_98": 0.91}
        code, output = self.run(tmp_path, state)
        assert code == 1
        assert "FAIL Statistik des Jobs gleich der Messung" in output and "percentile_98" in output
        assert "1 FAIL" in output

    def test_a_job_that_does_not_finish_fails_after_its_time(self, tmp_path: Path) -> None:
        state = Platform()
        state.status = "running"
        code, output = self.run(tmp_path, state)
        assert code == 1 and "FAIL Job fertig" in output

    def test_a_coordinate_in_the_log_fails_step_6(self, tmp_path: Path) -> None:
        code, output = self.run(tmp_path, Platform(), LOG + '{"message": "leak", "aoi": [6.9737913, 45.9846802]}\n')
        assert code == 1 and "FAIL Keine Koordinate der Quadrate im Log" in output

    def test_the_seconds_of_a_timestamp_are_no_coordinate(self, tmp_path: Path) -> None:
        """LOG carries ...:06.973712 in a timestamp, which holds the digits of the west edge (6.9737)."""
        code, output = self.run(tmp_path, Platform())
        assert code == 0, output
        assert "PASS Keine Koordinate der Quadrate im Log" in output

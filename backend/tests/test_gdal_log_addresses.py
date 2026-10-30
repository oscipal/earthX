"""NM4-57: no process writes the address of a file GDAL could not read into its log.

GDAL words a failed read with the address in it ("HTTP response code on <url>", "'/vsicurl/<url>' not
recognized"), and rasterio passes that on to the logging module; for a source with signed URLs the address holds
the token. Each process that reads rasters is started here as itself, in a process of its own, and made to fail one
read on purpose: `api`, `tiler`, the supervisor of the `worker` and its spawned child. The counter sample is the same
read in a process that never called `configure_logging`, which shows the address in GDAL's own lines — without it the
tests below could pass because GDAL said nothing.

The read goes to a port nothing listens on, so no network and no server is needed; GDAL answers that with a warning
that names the whole address. The address stands in a path and in a query, the two places a name and a token sit.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
PLACE = "secret-scene-name"
TOKEN = "sekret-sas-token"
ADDRESS = f"http://127.0.0.1:9/{PLACE}/B04.tif?sig={TOKEN}"

# The failing read, run by every process below once it is set up the way the process sets itself up.
READ = """
import logging
import rasterio

options = {
    "GDAL_HTTP_MAX_RETRY": "0",
    "GDAL_HTTP_TIMEOUT": "2",
    "GDAL_HTTP_CONNECTTIMEOUT": "2",
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
}
with rasterio.Env(**options):
    try:
        rasterio.open("/vsicurl/ADDRESS")
    except Exception as error:
        # What GDAL says when the answer is no file ("... not recognized as being in a supported file format"): the
        # address is in the text of the error, and so in the traceback of whatever logs it.
        try:
            raise OSError("'/vsicurl/ADDRESS' not recognized as being in a supported file format.") from error
        except OSError:
            logging.getLogger("probe").warning("could not read the scene", exc_info=True)
""".replace("ADDRESS", ADDRESS)

# How each process comes up. `api` and `tiler` build their app and so configure logging on import; the supervisor
# of the worker does at the top of its main module; the child, which is spawned without any of that, in `run_child`.
STARTS = {
    "api": ("import earthx.api.main", READ),
    "tiler": ("import earthx.api.tiler", READ),
    "worker": ("import earthx.jobs.main", READ),
    "worker child": (
        textwrap.dedent(
            """
            import earthx.jobs.child as child

            class Pipe:
                def send(self, message): pass
                def close(self): pass
                def poll(self): return False
            """
        ),
        "child._run = lambda workdir, conn: exec(%r)\nchild.run_child('nowhere', Pipe())" % READ,
    ),
    # Never configured: GDAL's own lines carry the address, so the tests above can fail.
    "none": ("import logging; logging.basicConfig(level=logging.INFO)", READ),
}


def run_process(name: str) -> subprocess.CompletedProcess[str]:
    setup, work = STARTS[name]
    environment = {**os.environ, "PYTHONPATH": str(BACKEND), "NO_PROXY": "*", "no_proxy": "*"}
    return subprocess.run(
        [sys.executable, "-c", setup + "\n" + work],
        capture_output=True,
        text=True,
        timeout=120,
        env=environment,
        cwd=BACKEND,
        check=True,
    )


def lines_of(result: subprocess.CompletedProcess[str]) -> list[dict[str, object]]:
    return [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]


@pytest.mark.parametrize("name", ["api", "tiler", "worker", "worker child"])
class TestNoAddressInTheLogOfAProcess:
    def test_neither_the_name_nor_the_token_leaves_the_process(self, name: str) -> None:
        result = run_process(name)
        everything = result.stdout + result.stderr
        for secret in (PLACE, TOKEN, "127.0.0.1:9", "/vsicurl"):
            assert secret not in everything

    def test_gdals_own_warning_is_there_with_a_placeholder_for_the_address(self, name: str) -> None:
        lines = lines_of(run_process(name))
        gdal = [line for line in lines if str(line["logger"]).startswith("rasterio")]
        assert any("<address>" in str(line["message"]) for line in gdal), "GDAL's warning names the address"
        probe = next(line for line in lines if line["logger"] == "probe")
        assert "OSError: '<address>' not recognized" in str(probe["exc_info"])


class TestTheCounterSample:
    def test_without_configure_logging_gdal_names_the_address(self) -> None:
        result = run_process("none")
        assert PLACE in result.stderr and TOKEN in result.stderr

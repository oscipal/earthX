"""The probe of the MeteoSwiss archive (`scripts/m5-11-meteoswiss/probe.py`, M5-11 plan §2.2, §7 step 1).

The script runs once on Otto's machine against the real collection. Here it runs through ``run(argv)`` against an
item list built after the measured shape (adr/0029 §3.1) and synthetic NetCDF files, through a real gateway with a
transport in memory; nothing leaves the process. The tests check that both modes reach their end, that the layout is
read from every file, and that the output never carries a URL, an item id or an ETag.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType

import httpx
import pytest

from earthx.gateway import Gateway, Policy
from tests.earthx.readers import mini_netcdf

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "m5-11-meteoswiss" / "probe.py"
BASE = "https://data.geo.admin.ch/assets/ch.meteoschweiz.ogd-surface-derived-grid/archive-ch"
NAMES = [
    "ogd-surface-derived-grid_tabsd_ch01r.swiss.lv95_19610101_19611231.nc",
    "ogd-surface-derived-grid_tabsd_ch01r.swiss.lv95_20240101_20241231.nc",
    "ogd-surface-derived-grid_rhiresd_ch01h.swiss.lv95_20240101_20241231.nc",
    "ogd-surface-derived-grid_tabsm_ch01r.swiss.lv95_202401_202412.nc",
    "ogd-surface-derived-grid_tabsd_ch01r.swiss.lv95_20990101_20991231.nc",
    "ogd-surface-derived-grid_tabsd_ch02r.swiss.lv95_20240101_20241231.nc",
    "readme_climate_grids.pdf",
]


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("meteoswiss_probe", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def probe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    module = load()
    body = mini_netcdf.build(tmp_path / "file.nc", bounds=True).read_bytes()
    source = mini_netcdf.Source(body)
    items = {
        "features": [
            {"id": "daily-item", "assets": {"a.nc": {"href": f"{BASE}/a.nc"}}},
            {
                "id": "archive-item",
                "assets": {
                    name: {"href": f"{BASE}/{name}", "type": "application/x-netcdf", "file:checksum": "1220ab", "updated": "x"}
                    for name in NAMES
                },
            },
        ],
        "links": [],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/items"):
            return httpx.Response(200, json=items)
        return source.handler(_with_host(request))

    async def no_wait(seconds: float) -> None:
        return None

    def gateway(policy: Policy) -> Gateway:
        return Gateway(policy, transport=httpx.MockTransport(handler), resolve=mini_netcdf.from_memory, sleep=no_wait)

    monkeypatch.setattr(module, "Gateway", gateway)
    module.SEEN = source.seen
    module.ETAG = source.etag
    return module


def _with_host(request: httpx.Request) -> httpx.Request:
    """The fake source answers only its own host; the probe asks the real one."""
    request.headers["host"] = mini_netcdf.HOST
    return request


def test_the_assets_by_kind(probe: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    assert probe.run(["--assets"]) == 0
    out = capsys.readouterr().out
    assert re.search(r"tabsd ch01r daily, one year\s+3 files, 1961–2099", out)
    assert "tabsm ch01r monthly, one year" in out
    assert "readme_climate_grids.pdf" in out  # an unknown name, as a form
    assert probe.SEEN == []


def test_the_layout_of_every_completed_daily_file(probe: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    assert probe.run(["--layout"]) == 0
    out = capsys.readouterr().out
    # 1961 and 2024 of ch01r, 2024 of ch01h; not 2099 (not completed), not monthly, not ch02r.
    assert re.search(r"daily annual files to read\s+3 ", out)
    assert "layout × 2" in out and "layout × 1" in out  # one layout per grid
    assert "EPSG:2056" in out and "<f4" in out and "degC" in out
    assert "from 06:00:00 to 06:00:00 (24 h)" in out


def test_limit(probe: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    assert probe.run(["--layout", "--limit", "1", "--grids", "ch01h"]) == 0
    assert "layout × 1" in capsys.readouterr().out


@pytest.mark.parametrize("argv", [["--assets"], ["--layout"]])
def test_the_output_names_no_address_no_id_and_no_etag(
    probe: ModuleType, capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    probe.run(argv)
    out = capsys.readouterr().out
    for secret in ("https://", "data.geo.admin.ch", "archive-item", "daily-item", probe.ETAG, json.dumps(probe.ETAG)):
        assert secret not in out

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
# The shapes of Otto's second run (17.11.2026), with the masked digits filled in: prefix `ogd-surface-derived-grid-archive.`,
# grid `ch01r`/`ch01h`, `.swiss.lv95`, two stamps of 14 digits. Beside them what the task must not read: monthly values,
# records, another grid, a year not yet completed, and outside the archive `-last` and the preliminary daily files.
ARCHIVE = "ogd-surface-derived-grid-archive"
NAMES = [
    f"{ARCHIVE}.tabsd_ch01r.swiss.lv95_19610101000000_19611231000000.nc",
    f"{ARCHIVE}.tabsd_ch01r.swiss.lv95_20250101000000_20251231000000.nc",
    f"{ARCHIVE}.tmaxd_ch01r.swiss.lv95_19710101000000_19711231000000.nc",
    f"{ARCHIVE}.rhiresd_ch01h.swiss.lv95_20250101000000_20251231000000.nc",
    f"{ARCHIVE}.tabsm_ch01r.swiss.lv95_20250101000000_20251231000000.nc",
    f"{ARCHIVE}.trecabsm_ch01r.swiss.lv95_20250101000000_20251231000000.nc",
    f"{ARCHIVE}.tabsd_ch02r.swiss.lv95_20250101000000_20251231000000.nc",
    f"{ARCHIVE}.tabsd_ch01r.swiss.lv95_20990101000000_20991231000000.nc",
    "readme_climate_grids.pdf",
]
OUTSIDE_THE_ARCHIVE = [
    "ogd-surface-derived-grid-last.tabsd_ch01r.swiss.lv95_20250101000000_20251231000000.nc",
    "ogd-surface-derived-grid-last.tabsd_ch01r.swiss.lv95_20251001000000_20251031000000.nc",
    "ogd-surface-derived-grid.rprelimd_ch01h.swiss.lv95_20261101000000_20261101000000.nc",
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
            {
                "id": "daily-item",
                "assets": {name: {"href": f"{BASE}/{name}"} for name in OUTSIDE_THE_ARCHIVE},
            },
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
    module.SOURCE = source
    module.ETAG = source.etag
    return module


def _with_host(request: httpx.Request) -> httpx.Request:
    """The fake source answers only its own host; the probe asks the real one."""
    request.headers["host"] = mini_netcdf.HOST
    return request


def test_the_assets_by_kind(probe: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    assert probe.run(["--assets"]) == 0
    out = capsys.readouterr().out
    # The seven names of the archive on ch01r/ch01h; ch02r, `-last` and the preliminary files are not among them.
    assert re.search(r"names this task reads \(distinct\)\s+7$", out, flags=re.MULTILINE), out
    assert re.search(r"tabsd ch01r daily values, file of one year\s+3 files, 1961–2099", out)
    assert re.search(r"rhiresd ch01h daily values, file of one year\s+1 files, 2025–2025", out)
    assert "tabsm ch01r monthly values, file of one year" in out
    assert "rprelimd" not in out.split("names this task reads")[1]
    assert probe.SEEN == []


def test_every_name_pattern_of_every_item(probe: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    """Not the ten most frequent of the largest item: all of them, over all items, with counts and years."""
    assert probe.run(["--assets"]) == 0
    out = capsys.readouterr().out
    tabsd = f"{ARCHIVE}.tabsd_ch##r.swiss.lv##_##############_##############.nc"
    assert re.search(re.escape(tabsd) + r"\s+× 4 in 1 items, years 1961–2099", out), out
    last = "ogd-surface-derived-grid-last.tabsd_ch##r.swiss.lv##_##############_##############.nc"
    assert re.search(re.escape(last) + r"\s+× 2 in 1 items, years 2025–2025", out)
    assert re.search(r"readme_climate_grids\.pdf\s+× 1 in 1 items$", out, flags=re.MULTILINE)
    # The grid's digits are masked too, so ch01r and ch02r share a pattern, as do all years of one product.
    assert re.search(r"name patterns\s+8$", out, flags=re.MULTILINE), out


def test_the_layout_of_every_completed_daily_file_of_the_archive(
    probe: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    assert probe.run(["--layout"]) == 0
    out = capsys.readouterr().out
    # tabsd 1961 and 2025, tmaxd 1971 (ch01r), rhiresd 2025 (ch01h); not monthly, not records, not ch02r, not 2099, not
    # `-last`, not the preliminary daily files.
    assert re.search(r"daily annual files to read\s+4 ", out), out
    assert "layout × 3" in out and "layout × 1" in out  # one layout per grid
    assert "EPSG:2056" in out and "<f4" in out and "degC" in out
    assert "from 06:00:00 to 06:00:00 (24 h)" in out
    assert len(probe.SEEN) >= 4


def test_a_refused_file_is_named_by_its_status_only(probe: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    """An answer of the source may quote a key or a path; the output names only the status."""

    def gone(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="<Error><Key>secret/path/file.nc</Key></Error>")

    probe.SOURCE.handler = gone
    assert probe.run(["--layout", "--grids", "ch01h"]) == 0
    out = capsys.readouterr().out
    assert "UpstreamError 404 × 1" in out
    assert "secret" not in out


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


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        ("19610101000000", "19611231000000", "one year"),
        ("19610101000000", "19611231235959", "one year"),
        ("19610101000000", "19620101000000", "one year"),
        ("20251001000000", "20251031000000", "one month"),
        ("20261101000000", "20261101000000", "one day"),
        ("19610101000000", "19701231000000", "several years"),
    ],
)
def test_what_one_file_covers(start: str, end: str, expected: str) -> None:
    assert load().span({"start": start, "end": end}) == expected

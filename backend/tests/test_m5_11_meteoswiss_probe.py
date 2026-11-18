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
        ("20261101000000", "20261101000000", "one time step"),
        # Yearly values stamped with the first instant of their year: one time step, no file of one day (18.11.2026).
        ("20250101000000", "20250101000000", "one time step"),
        ("20251101000000", "20251101235959", "one day"),
        ("19610101000000", "19701231000000", "several years"),
    ],
)
def test_what_one_file_covers(start: str, end: str, expected: str) -> None:
    assert load().span({"start": start, "end": end}) == expected


def test_yearly_values_are_one_time_step_not_one_day() -> None:
    name = {"quantity": "tabsy", "grid": "ch01r", "start": "20250101000000", "end": "20250101000000"}
    assert load().cadence(name) == "yearly values, file of one time step"


def test_a_grid_mapping_that_names_no_epsg_code_is_compared_with_lv95(
    probe: ModuleType, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Third run (18.11.2026): every file refused for its grid_mapping. The probe now says how it differs from 2056."""
    from pyproj import CRS

    esri = CRS.from_epsg(2056).to_wkt("WKT1_ESRI")
    mapping = {**mini_netcdf.LV95, "false_easting": 2600000.5, "esri_pe_string": esri}
    probe.SOURCE.replace(mini_netcdf.build(tmp_path / "shifted.nc", grid_mapping=mapping, bounds=True).read_bytes())
    assert probe.run(["--layout", "--grids", "ch01h"]) == 0
    out = capsys.readouterr().out
    # The rest of the layout is still read: type, time bounds; the platform itself would refuse the file.
    assert "layout × 1" in out and "<f4" in out and "from 06:00:00 to 06:00:00 (24 h)" in out
    assert "no exact EPSG code (see grid_mapping below)" in out
    assert re.search(r"grid_mapping 1 of 1 without an exact EPSG code\s+\{'rhiresd ch01h': 1\}", out), out
    assert re.search(r"attribute false_easting\s+2600000\.5$", out, flags=re.MULTILINE)
    assert re.search(r"from_cf: Easting at projection centre\s+DIFFERS: 2600000\.5 \| 2600000\.0", out), out
    assert re.search(r"from_cf: Northing at projection centre\s+same", out)
    assert re.search(r"esri_pe_string: pyproj matches\s+\[.*'EPSG:2056 \d+%'", out), out
    assert "ellipsoid (here)" in out and "axes (EPSG)" in out


# M5-58 plan §2.3: the items outside the archive, as `adr/0029` §3.1 measured them (an item per day with `expires`, an
# item per month); the names of their files are what `--current` is to find out, so these are made up in the same form.
DAY_ITEM = {
    "id": "day-item",
    "properties": {"datetime": "2026-11-17T06:00:00Z", "expires": "2026-12-28T00:00:00Z"},
    "assets": {
        name: {"href": f"{BASE}/{name}", "file:checksum": "1220ab", "updated": "x"}
        for name in (
            "ogd-surface-derived-grid.rprelimd_ch01h.swiss.lv95_20261116000000_20261116000000.nc",
            "ogd-surface-derived-grid.tabsd_ch01r.swiss.lv95_20261116000000_20261116000000.nc",
        )
    },
}
MONTH_ITEM = {
    "id": "month-item",
    "properties": {"datetime": "2026-11-10T06:00:00Z"},
    "assets": {
        name: {"href": f"{BASE}/{name}", "file:checksum": "1220cd"}
        for name in (
            "ogd-surface-derived-grid-last.rhiresd_ch01h.swiss.lv95_20261001000000_20261031000000.nc",
            "ogd-surface-derived-grid-last.tabsm_ch01r.swiss.lv95_20261001000000_20261031000000.nc",
        )
    },
}


@pytest.fixture
def current(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    module = load()
    source = mini_netcdf.Source(mini_netcdf.build(tmp_path / "file.nc", bounds=True).read_bytes())
    archive = {"id": "archive-item", "assets": {name: {"href": f"{BASE}/{name}"} for name in NAMES}}
    listing = {"features": [archive, DAY_ITEM, MONTH_ITEM], "links": []}
    by_id = {item["id"]: item for item in listing["features"]}

    def answer(body: dict[str, object], request: httpx.Request) -> httpx.Response:
        etag = f'"{len(json.dumps(body))}"'
        if request.headers.get("if-none-match") == etag:
            return httpx.Response(304, headers={"etag": etag})
        return httpx.Response(200, json=body, headers={"etag": etag})

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/items"):
            return answer(listing, request)
        if "/items/" in path:
            return answer(by_id[path.rsplit("/", 1)[1]], request)
        return source.handler(_with_host(request))

    async def no_wait(seconds: float) -> None:
        return None

    def gateway(policy: Policy) -> Gateway:
        return Gateway(policy, transport=httpx.MockTransport(handler), resolve=mini_netcdf.from_memory, sleep=no_wait)

    monkeypatch.setattr(module, "Gateway", gateway)
    module.SEEN = source.seen
    module.ETAG = source.etag
    return module


def test_current_reports_the_items_outside_the_archive_by_kind(current: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    assert current.run(["--current"]) == 0
    out = capsys.readouterr().out
    assert re.search(r"items outside the archive\s+2$", out, flags=re.MULTILINE), out
    assert re.search(r"^item of one day\s+1 items$", out, flags=re.MULTILINE), out
    assert re.search(r"^item of one month\s+1 items$", out, flags=re.MULTILINE), out
    assert re.search(r"ogd-surface-derived-grid rprelimd ch01h \(one time step\)\s+× 1", out), out
    assert re.search(r"ogd-surface-derived-grid-last rhiresd ch01h \(one month\)\s+× 1", out), out
    assert re.search(r"expires, earliest and latest\s+2026-12-28T00:00:00Z \| 2026-12-28T00:00:00Z", out), out
    assert re.search(r"conditional request per item\s+\{'strong ETag, 304 on If-None-Match': 1\}", out), out
    assert re.search(r"page 1\s+ETag, 304 on If-None-Match; Last-Modified none", out), out
    # One header per kind, grid and daily quantity: rprelimd and tabsd of the day, rhiresd of the month; not tabsm.
    assert re.search(r"file headers to read\s+3$", out, flags=re.MULTILINE), out
    assert "item of one day rprelimd ch01h" in out and "item of one month rhiresd ch01h" in out
    assert "from 06:00:00 to 06:00:00 (24 h)" in out
    # Nothing of the archive is read.
    assert "tabsd ch01r daily values, file of one year" not in out
    assert len(current.SEEN) >= 3


def test_current_names_no_address_no_id_and_no_etag(current: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    current.run(["--current"])
    out = capsys.readouterr().out
    for secret in ("https://", "data.geo.admin.ch", "day-item", "month-item", "archive-item", current.ETAG):
        assert secret not in out

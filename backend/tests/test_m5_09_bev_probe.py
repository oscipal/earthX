"""The probe of the BEV ATOM service (`scripts/m5-09-bev/probe.py`, M5-09 plan §2.4, §6).

The script runs once on Otto's machine against the real service. Here it runs through its command line, ``run(argv)``
and so ``main``, against feeds built after the shape Otto measured (plan §2.4) and a stand-in for ``Gateway``; nothing
leaves the process. The tests check that every mode reaches its end and that the output never carries a URL, a tile
name or an identifier, which is what lets Otto paste it into the pull request.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from rasterio.warp import transform

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "m5-09-bev" / "probe.py"

ATOM = (
    'xmlns="http://www.w3.org/2005/Atom" xmlns:georss="http://www.georss.org/georss" '
    'xmlns:inspire_dls="http://inspire.ec.europa.eu/schemas/inspire_dls/1.0"'
)
HOST = "https://data.bev.gv.at"
#: Made-up cells of the 50 km grid in EPSG:3035 (northing, easting of the lower left corner).
CELLS = ((2650000, 4800000), (2700000, 4700000), (2600000, 4650000))
DATES = ("15.09.2024", "15.09.2025")


def _tile(north: int, east: int) -> str:
    return f"CRS3035RES50000mN{north}E{east}"


def _code(north: int, east: int, day: str) -> str:
    """A made-up identifier in the form of a UUID, one per tile and date."""
    return f"{north:08x}-{east % 65536:04x}-4000-8000-{int(day[-4:]):012x}"


def _polygon(north: int, east: int) -> str:
    xs = [east, east + 50000, east + 50000, east, east]
    ys = [north, north, north + 50000, north + 50000, north]
    lons, lats = transform("EPSG:3035", "EPSG:4326", xs, ys)
    return " ".join(f"{lat:.6f} {lon:.6f}" for lat, lon in zip(lats, lons, strict=True))


def _entry(model: str, north: int, east: int, day: str) -> str:
    code = _code(north, east, day)
    return (
        f"<entry><title>ALS {model} {_tile(north, east)} Höhenraster 1m Stichtag {day}</title>"
        f"<author><name>BEV</name></author><id>{HOST}/feed/{code}</id><rights>CC-BY-4.0</rights>"
        f"<summary>s</summary><updated>2025-10-01T00:00:00Z</updated>"
        '<category term="http://www.opengis.net/def/crs/EPSG/0/3035"/>'
        f"<inspire_dls:spatial_dataset_identifier_code>{code}</inspire_dls:spatial_dataset_identifier_code>"
        f"<inspire_dls:spatial_dataset_identifier_namespace>{HOST}</inspire_dls:spatial_dataset_identifier_namespace>"
        f'<link rel="alternate" type="application/atom+xml" href="{HOST}/feed/{code}"/>'
        f'<link rel="describedby" type="application/xml" href="{HOST}/records/{code}"/>'
        f"<georss:polygon>{_polygon(north, east)}</georss:polygon></entry>"
    )


SERVICE = (
    f"<feed {ATOM}><title>t</title><updated>2026-11-16T10:00:00Z</updated><rights>r</rights>"
    "<entry><title>ALS DTM Höhenraster 1m Serie</title></entry>"
    + "".join(_entry(model, n, e, day) for model in ("DTM", "DSM") for n, e in CELLS for day in DATES)
    + "</feed>"
)


def _file(north: int, east: int, day: str) -> str:
    return f"{HOST}/download/ALS/DTM/{day[-4:]}{day[3:5]}{day[:2]}/ALS_DTM_{_tile(north, east)}.tif"


def _dataset_feed(code: str) -> str:
    north, east, day = next((n, e, d) for n, e in CELLS for d in DATES if _code(n, e, d) == code)
    return (
        f"<feed {ATOM}><entry><title>f</title><id>{code}</id><updated>2025-10-01T00:00:00Z</updated>"
        '<category term="http://www.opengis.net/def/crs/EPSG/0/3035"/>'
        f'<link rel="alternate" type="image/tiff" href="{_file(north, east, day)}"/>'
        f"<georss:polygon>{_polygon(north, east)}</georss:polygon></entry></feed>"
    )


class _Response:
    def __init__(self, status: int, content: bytes, headers: dict[str, str]) -> None:
        self.status_code = status
        self.content = content
        self.headers = headers


class _Gateway:
    """Answers the three kinds of address the probe asks for; any other address fails the test."""

    calls: list[str] = []

    def __init__(self, policy: Any) -> None:
        self.policy = policy

    async def __aenter__(self) -> _Gateway:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def get(self, url: str, headers: dict[str, str] | None = None, **_: object) -> _Response:
        self.calls.append(url)
        if "/geonetwork/srv/atom/describe/service" in url:
            return _Response(200, SERVICE.encode(), {"Content-Type": "application/atom+xml"})
        if url.startswith(f"{HOST}/feed/"):
            return _Response(200, _dataset_feed(url.rsplit("/", 1)[1]).encode(), {})
        if url.startswith(f"{HOST}/download/"):
            return _Response(206, b"II*\x00" + b"\x00" * 12, {"Content-Range": "bytes 0-15/100"})
        raise AssertionError("the probe asked for an address the test does not know")

    async def head(self, url: str, headers: dict[str, str] | None = None, **_: object) -> _Response:
        assert url.startswith(f"{HOST}/download/")
        self.calls.append(url)
        return _Response(
            200, b"", {"Content-Length": "1000000000", "ETag": '"e"', "Last-Modified": "x", "Accept-Ranges": "bytes"}
        )


@pytest.fixture
def probe(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location("bev_probe", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "Gateway", _Gateway)
    monkeypatch.setattr(_Gateway, "calls", [])
    return module


def _assert_clean(output: str) -> None:
    for north, east in CELLS:
        assert _tile(north, east) not in output
        for day in DATES:
            assert _code(north, east, day) not in output
    assert HOST not in output
    for north, east in CELLS:
        for day in DATES:
            assert _file(north, east, day).removeprefix(HOST) not in output


def test_shape_runs_through_the_command_line(probe: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    assert probe.run(["--shape"]) == 0
    output = capsys.readouterr().out
    lines = {line[:44].strip(): line[44:].strip() for line in output.splitlines()}
    assert lines["service feed body identical twice"] == "yes"
    assert lines["newest DTM date, tiles"] == f"2025-09-15, {len(CELLS)}"
    assert lines["polygon vs cell, name = lower left [deg]"] == "0.000000"
    assert "path /download/ALS/DTM/########/ALS_DTM_CRS####RES#####mN#######E#######.tif" in output
    assert "code in describedby link (12)" in output
    assert "other title (1)" in output
    # The service feed twice, then one dataset feed per tile of the newest date; no file is touched.
    assert len(_Gateway.calls) == 2 + len(CELLS)
    assert not any("/download/" in url for url in _Gateway.calls)
    _assert_clean(output)


def test_the_first_mode_runs_through_the_command_line(probe: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    assert probe.run(["--all"]) == 0
    output = capsys.readouterr().out
    assert "newest DTM date                              2025-09-15" in output
    assert f"files with a size                            {len(CELLS)} of {len(CELLS)}" in output
    _assert_clean(output)

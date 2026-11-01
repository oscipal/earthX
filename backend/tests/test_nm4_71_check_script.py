"""The check script of NM4-71 (`scripts/checks/nm4-71-normalize.ps1`), read for what Windows PowerShell 5.1 cannot take.

The script is for 5.1 on Otto's machine and needs the whole stack and the source on the net, so it is not run here;
the helpers are those of `nm4-11-normalize.ps1` and `nm4-19-statistics.ps1`; the latter runs in `test_nm4_19_check_script.py` against a local platform.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "checks" / "nm4-71-normalize.ps1"


BOM = b"\xef\xbb\xbf"


def _text() -> str:
    """The script without its byte order mark."""
    return SCRIPT.read_bytes().removeprefix(BOM).decode("ascii")


def test_the_script_is_utf_8_with_a_bom_and_ascii_after_it() -> None:
    """Windows PowerShell 5.1 reads a file without a BOM in the ANSI code page; with it, as UTF-8 (Otto, zu #273)."""
    raw = SCRIPT.read_bytes()
    assert raw.startswith(BOM) and raw[len(BOM) :].isascii()


def test_no_variable_is_followed_by_a_colon_in_a_string() -> None:
    """``"$Text: ..."`` is a drive-qualified reference to 5.1 and fails to parse; ``"${Text}: ..."`` is meant (Otto, zu #273).

    The scope modifiers (``$script:``, ``$env:`` ...) are the only names a colon may follow.
    """
    found = [
        match.group(0)
        for match in re.finditer(r"\$([A-Za-z_][A-Za-z0-9_]*):", _text())
        if match.group(1).lower() not in {"script", "global", "local", "private", "env", "using"}
    ]
    assert found == []


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
def test_no_syntax_or_parameter_of_powershell_7(pattern: str) -> None:
    assert not re.search(pattern, _text())


def test_no_function_takes_the_name_of_a_cmdlet() -> None:
    """A function called ``Wait-Job`` would hide the cmdlet for the rest of the session."""
    names = re.findall(r"^function ([A-Za-z]+-[A-Za-z]+)", _text(), flags=re.MULTILINE)
    assert names and not set(names) & {
        "Wait-Job",
        "Get-Job",
        "Start-Job",
        "Write-Host",
        "Invoke-WebRequest",
        "Get-Content",
    }


def test_bodies_go_as_bytes_and_errors_are_caught() -> None:
    text = _text()
    assert "[System.Text.Encoding]::UTF8.GetBytes($Body)" in text
    assert "$_.Exception.Response" in text and "UseBasicParsing = $true" in text


def test_the_script_prints_no_item_id_no_job_id_and_no_hash() -> None:
    """Every ``Write-*`` line is a fixed text; the item is only ever printed through ``Get-Detail``, which masks it."""
    text = _text()
    assert "$script:ItemId" in text and ".Replace($script:ItemId, '<item>')" in text
    assert not re.search(r"Write-(Host|Info|Pass)[^\n]*\$\(?\$?(job|placed)\.jobID", text)


def test_the_jobs_send_version_4_without_numbers_and_the_gear_version_3_with_them() -> None:
    text = _text()
    assert "New-Step 4 $percentileV4" in text and "New-Step 4 $zscoreV4" in text and "New-Step 3 $fixed" in text
    assert '"measured"' not in text.split("$percentileV4 = ", 1)[1].split("\n", 1)[0]


def test_the_whole_scene_is_asked_for_without_an_aoi() -> None:
    text = _text()
    assert "New-Order $script:ItemId '' ''" in text and "if ($Aoi) {" in text


# --- the choice of the scene, run in pwsh against a made-up search answer ---------------------------------------------

PWSH = shutil.which("pwsh")
#: The functions of step 1, taken from the script as they are, in the order they need each other.
SELECTION = ("Get-Rings", "Test-InRing", "Test-SquareInRing", "Find-Square", "Select-Scene", "Format-Reasons")
PREFER = (7.0137913, 46.0246802)
HALF = 0.15
DRIVER = """param([string]$Path)
$ErrorActionPreference = 'Stop'
%s
$features = @((Get-Content -Raw -Path $Path | ConvertFrom-Json).features)
$picked = Select-Scene $features 10.0 %r %r %r
$out = [ordered]@{ count = $picked.Count; reasons = (Format-Reasons $picked.Reasons); id = $null; lon = $null; lat = $null }
if ($null -ne $picked.Scene) { $out.id = $picked.Scene.Id; $out.lon = $picked.Scene.Lon; $out.lat = $picked.Scene.Lat }
$out | ConvertTo-Json -Compress
"""


def _function(name: str) -> str:
    match = re.search(rf"^function {re.escape(name)} \{{\n.*?^\}}\n", _text(), flags=re.MULTILINE | re.DOTALL)
    assert match, f"the script defines {name}"
    return match.group(0)


def _box(west: float, south: float, east: float, north: float) -> dict[str, Any]:
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    return {"type": "Polygon", "coordinates": [ring]}


def _scene(name: str, cloud: float | None, geometry: dict[str, Any] | None) -> dict[str, Any]:
    properties: dict[str, Any] = {} if cloud is None else {"eo:cloud_cover": cloud}
    return {"type": "Feature", "id": name, "properties": properties, "geometry": geometry}


def _choose(tmp_path: Path, features: list[dict[str, Any]]) -> dict[str, Any]:
    answer = tmp_path / "search.json"
    answer.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    driver = tmp_path / "choose.ps1"
    driver.write_text(DRIVER % ("".join(_function(name) for name in SELECTION), HALF, *PREFER), encoding="utf-8")
    process = subprocess.run(
        [PWSH or "pwsh", "-NoProfile", "-File", str(driver), "-Path", str(answer)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    return json.loads(process.stdout.strip().splitlines()[-1])


def _holds(geometry: dict[str, Any], lon: float, lat: float) -> bool:
    """Whether the square around the point lies in one ring of the outline (boxes only, as the cases here are)."""
    rings = geometry["coordinates"] if geometry["type"] == "Polygon" else [p[0] for p in geometry["coordinates"]]
    for ring in rings:
        lons, lats = [p[0] for p in ring], [p[1] for p in ring]
        if min(lons) <= lon - HALF and lon + HALF <= max(lons) and min(lats) <= lat - HALF and lat + HALF <= max(lats):
            return True
    return False


@pytest.mark.skipif(PWSH is None, reason="PowerShell (pwsh) is not installed; the CI image has it")
class TestTheChoiceOfTheScene:
    def test_the_square_moves_into_the_outline_of_the_clearest_scene(self, tmp_path: Path) -> None:
        """Otto's run: two neighbouring tiles overlap by about 0.09 degrees; at 7 E / 46 N the square of 0.3 degrees
        fits into neither, so it is laid into the clearest one instead of failing."""
        south = _box(6.0, 45.1, 7.4, 46.06)
        north = _box(6.0, 45.97, 7.4, 46.95)
        chosen = _choose(tmp_path, [_scene("north", 2.0, north), _scene("south", 1.0, south)])
        assert chosen["id"] == "south" and chosen["count"] == 2
        assert _holds(south, chosen["lon"], chosen["lat"])
        assert chosen["lat"] < PREFER[1], "moved south, into the outline"

    def test_the_preferred_point_stays_where_the_square_fits_there(self, tmp_path: Path) -> None:
        chosen = _choose(tmp_path, [_scene("wide", 3.0, _box(6.0, 45.5, 7.6, 46.6))])
        assert (chosen["lon"], chosen["lat"]) == pytest.approx(PREFER)

    def test_no_scene_names_each_reason_counted_and_no_id_or_coordinate(self, tmp_path: Path) -> None:
        features = [
            _scene("cloudy", 50.0, _box(6.0, 45.5, 7.6, 46.6)),
            _scene("unsaid", None, _box(6.0, 45.5, 7.6, 46.6)),
            _scene("outline", 1.0, None),
            _scene("small", 1.0, _box(6.9, 45.9, 7.1, 46.1)),
        ]
        chosen = _choose(tmp_path, features)
        assert chosen["id"] is None and chosen["count"] == 0
        assert chosen["reasons"] == "ohne Wolkenangabe: 1, wolkig: 1, ohne Umriss: 1, Quadrat nicht enthalten: 1"
        assert not re.search(r"cloudy|unsaid|outline|small|\d+\.\d+", chosen["reasons"])

    def test_the_square_lies_in_one_ring_of_a_multipolygon(self, tmp_path: Path) -> None:
        halves = {
            "type": "MultiPolygon",
            "coordinates": [_box(6.75, 45.5, 7.0, 46.6)["coordinates"], _box(7.0, 45.5, 7.25, 46.6)["coordinates"]],
        }
        assert _choose(tmp_path, [_scene("split", 1.0, halves)])["reasons"].endswith("Quadrat nicht enthalten: 1")
        wide = {
            "type": "MultiPolygon",
            "coordinates": [_box(6.0, 45.5, 6.2, 45.7)["coordinates"], _box(6.5, 45.5, 7.6, 46.6)["coordinates"]],
        }
        chosen = _choose(tmp_path, [_scene("wide", 1.0, wide)])
        assert chosen["id"] == "wide" and _holds(wide, chosen["lon"], chosen["lat"])

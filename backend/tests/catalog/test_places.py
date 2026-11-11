"""Place names from the extent of a dataset (docs/plans/m5/m5-22-suche-lexikalisch.md F4, adr/0026 F8)."""

from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path

import pytest

from earthx.catalog.places import GLOBAL_TERMS, PLACES_FILE, load_places, place_terms
from earthx.catalog.registry import ConfigError

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "write-place-outlines.py"


def test_the_file_names_its_release_checksum_and_script():
    data = json.loads(PLACES_FILE.read_text(encoding="utf-8"))
    script = runpy.run_path(str(SCRIPT), run_name="not_main")
    assert (data["release"], data["sha256"], data["file"]) == (
        script["RELEASE"],
        script["SOURCE_SHA256"],
        script["SOURCE_FILE"],
    )
    assert data["tolerance_deg"] == script["TOLERANCE_DEG"]
    assert (Path(__file__).resolve().parents[3] / data["script"]) == SCRIPT
    assert "public domain" in data["source"]


def test_every_country_has_both_names():
    known = load_places()
    assert len(known.countries) == 242
    by_code = {country.code: country for country in known.countries}
    assert (by_code["CHE"].en, by_code["CHE"].de) == ("Switzerland", "Schweiz")
    assert (by_code["AUT"].en, by_code["AUT"].de) == ("Austria", "Österreich")
    assert by_code["VAT"].area > 0


@pytest.mark.parametrize(
    ("bbox", "terms"),
    [
        # swissALTI3D: Switzerland and Liechtenstein, not Italy, though half the box lies south of the Alps' crest.
        ((5.9503666, 45.7213375, 10.4998461, 47.8216742), ("Liechtenstein", "Switzerland", "Schweiz")),
        ((9.5, 46.3, 17.2, 49.1), ("Austria", "Österreich", "Liechtenstein")),
        ((-180.0, -90.0, 180.0, 90.0), GLOBAL_TERMS),
        # Antarctica is left out of the rule: WorldCover stops at 60° S and is still global.
        ((-180.0, -60.0, 180.0, 84.0), GLOBAL_TERMS),
        # Open ocean holds no country.
        ((-40.0, 20.0, -30.0, 30.0), ()),
    ],
)
def test_terms_of_a_box(bbox, terms):
    assert place_terms(bbox) == terms


def test_a_continent_counts_once_half_of_it_is_in_the_box():
    terms = place_terms((-20.0, -36.0, 52.0, 38.0))
    assert ("Africa", "Afrika") == terms[-2:]
    assert "global" not in terms


def test_a_country_below_half_is_left_out():
    # A box over the west of Austria holds less than half of it.
    assert "Austria" not in place_terms((9.5, 46.3, 12.0, 47.8))


def _write(tmp_path: Path, change) -> Path:
    data = json.loads(PLACES_FILE.read_text(encoding="utf-8"))
    data["countries"] = data["countries"][:3]
    change(data)
    path = tmp_path / "places.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _set_country(key, value):
    def change(data):
        data["countries"][0][key] = value

    return change


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d.pop("release"), "has exactly the keys"),
        (lambda d: d.update(countries=[]), "'countries' is a non-empty list"),
        (lambda d: d.update(continents={}), "'continents' maps"),
        (_set_country("de", ""), "'de' is a non-empty text"),
        (_set_country("en", " Austria"), "'en' is a non-empty text"),
        (_set_country("continent", "Atlantis"), "the continent is one of"),
        (_set_country("outline", {"type": "Point", "coordinates": [1, 2]}), "valid polygon"),
        (_set_country("outline", {"type": "Polygon"}), "no GeoJSON geometry"),
        (_set_country("outline", "not a geometry"), "no GeoJSON geometry"),
        (
            _set_country("outline", {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]}),
            "valid polygon",
        ),
        (_set_country("extra", 1), "exactly the keys"),
        (lambda d: d["countries"].append(dict(d["countries"][0])), "appears twice"),
    ],
)
def test_a_malformed_file_is_refused(tmp_path, change, message):
    with pytest.raises(ConfigError, match=message):
        load_places(_write(tmp_path, change))


def test_a_file_that_is_no_json_is_refused(tmp_path):
    path = tmp_path / "places.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ConfigError, match="cannot be read"):
        load_places(path)


def test_the_script_refuses_a_file_of_another_release(tmp_path, monkeypatch, capsys):
    other = tmp_path / "ne_50m_admin_0_countries.geojson"
    other.write_text('{"features": []}', encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["write-place-outlines.py", str(other)])
    script = runpy.run_path(str(SCRIPT), run_name="not_main")
    assert script["main"]() == 1
    assert hashlib.sha256(other.read_bytes()).hexdigest() in capsys.readouterr().err

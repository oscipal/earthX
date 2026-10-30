"""The runner reads a ``recipe.json`` of recipe version 1 for good, and says so where the values can differ
(adr/0016 Nachtrag NM4-43c, adr/0020 §11, F9, F14)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from earthx.runner.cli import EXIT_OK, main
from earthx.runner.recipe_file import conversion_notes, load_recipe
from tests.earthx.processing import sources
from tests.earthx.runner import support

REPROJECT = {"crs": "EPSG:3035", "resolution": 20.0, "resampling": "nearest"}


@pytest.fixture(scope="module")
def cogs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("bands")
    return {
        sources.url("red"): sources.build_band_cog(root / "red.tif", sources.ramp(support.WIDTH, support.HEIGHT, 1200)),
        sources.url("nir"): sources.build_band_cog(root / "nir.tif", sources.ramp(support.WIDTH, support.HEIGHT, 3400)),
    }


@pytest.fixture
def served(cogs: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return sources.serve(cogs, monkeypatch)


@pytest.fixture
def out(tmp_path: Path) -> Path:
    path = tmp_path / "out"
    path.mkdir()
    return path


def _file(tmp_path: Path, recipe: dict[str, Any], *, engine: dict[str, str] | None = None) -> str:
    path = tmp_path / "recipe.json"
    path.write_bytes(support.recipe_file(recipe, engine=engine))
    return str(path)


def _with_reproject(recipe: dict[str, Any], version: int = 3) -> dict[str, Any]:
    recipe["steps"].append({"op": "reproject", "op_version": version, "params": REPROJECT})
    return recipe


def _run(*args: str) -> int:
    return main(list(args), registry=support.registry())


def _engine(version: str | None) -> dict[str, str]:
    engine = {"gdal": "3.12.2", "rasterio": "1.5.2", "numexpr": "2.14.2", "numpy": "2.5.3"}
    return engine if version is None else {"earthx": version, **engine}


class TestAFileOfVersion1:
    def test_without_reproject_the_values_are_the_same_and_nothing_is_said(
        self, tmp_path: Path, out: Path, served: list[str], capsys: pytest.CaptureFixture[str]
    ) -> None:
        recipe = _file(tmp_path, support.band_math_recipe())
        assert _run("run", recipe, "--out", str(out)) == EXIT_OK
        assert "Converted" not in capsys.readouterr().err
        (folder,) = out.iterdir()
        assert "notes" not in json.loads((folder / "provenance.json").read_text(encoding="utf-8"))
        assert (folder / "recipe.json").read_bytes() == Path(recipe).read_bytes()  # the file of the person, as it was

    def test_a_version_1_and_a_version_2_file_of_one_recipe_give_the_same_values(
        self, tmp_path: Path, out: Path, served: list[str]
    ) -> None:
        import rasterio

        (tmp_path / "v1").mkdir()
        (tmp_path / "v2").mkdir()
        one, two = out / "one", out / "two"
        one.mkdir()
        two.mkdir()
        assert _run("run", _file(tmp_path / "v1", support.band_math_recipe()), "--out", str(one)) == EXIT_OK
        assert _run("run", _file(tmp_path / "v2", support.band_math_recipe_v2()), "--out", str(two)) == EXIT_OK
        (first,), (second,) = one.iterdir(), two.iterdir()
        with rasterio.open(first / "result.tif") as a, rasterio.open(second / "result.tif") as b:
            assert a.read().tobytes() == b.read().tobytes()
            assert b.descriptions == ("Index",)
            assert a.descriptions == ("band_math",)

    @pytest.mark.parametrize("version", [2, 3])
    def test_a_reproject_that_warped_all_bands_in_one_go_earns_a_note_on_the_screen_and_in_the_provenance(
        self, tmp_path: Path, out: Path, served: list[str], capsys: pytest.CaptureFixture[str], version: int
    ) -> None:
        recipe = _file(tmp_path, _with_reproject(support.band_math_recipe(), version), engine=_engine("0.4.3"))
        assert _run("run", recipe, "--out", str(out)) == EXIT_OK
        note = (
            "Converted from recipe version 1. Values after reproject can differ; "
            "for identical values use earthx-runner:0.4.3."
        )
        assert note in capsys.readouterr().err.splitlines()
        (folder,) = out.iterdir()
        provenance = json.loads((folder / "provenance.json").read_text(encoding="utf-8"))
        assert provenance["notes"] == [note]
        assert provenance["source_engine"]["earthx"] == "0.4.3"

    def test_a_reproject_of_version_4_needs_no_note(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        recipe = _file(tmp_path, _with_reproject(support.band_math_recipe(), 4), engine=_engine("0.4.4"))
        assert _run("check", recipe) == EXIT_OK
        assert "Converted" not in capsys.readouterr().err

    def test_check_says_it_too(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        recipe = _file(tmp_path, _with_reproject(support.band_math_recipe()), engine=_engine("0.4.3"))
        assert _run("check", recipe) == EXIT_OK
        assert "use earthx-runner:0.4.3." in capsys.readouterr().err

    @pytest.mark.parametrize("version", [None, "0.4", "latest", "0.4.3\nrm -rf /", "0.4.3 ", "x" * 200, "0.4.3+gabc"])
    def test_without_a_version_that_looks_like_one_the_note_names_no_tag_and_nothing_of_the_file(
        self, version: str | None
    ) -> None:
        recipe = support.band_math_recipe()
        _with_reproject(recipe)
        loaded = load_recipe(support.recipe_file(recipe, engine=_engine(version)))
        assert loaded.notes == (
            "Converted from recipe version 1. Values after reproject can differ; "
            "for identical values use an older runner tag.",
        )

    def test_the_note_names_no_path_no_address_and_no_identifier(self) -> None:
        recipe = _with_reproject(support.band_math_recipe())
        loaded = load_recipe(support.recipe_file(recipe, engine=_engine("0.4.3")))
        text = " ".join(loaded.notes)
        for forbidden in ("/", "https://", recipe["recipe_id"], sources.HOST):
            assert forbidden not in text.replace("earthx-runner:", "")

    def test_a_file_of_version_2_has_no_note_even_with_an_old_reproject(self) -> None:
        recipe = support.band_math_recipe_v2()
        _with_reproject(recipe)
        assert load_recipe(support.recipe_file(recipe, engine=_engine("0.4.3"))).notes == ()

    def test_the_committed_file_of_the_ci_is_a_recipe_of_version_1_that_still_reads(self) -> None:
        committed = (Path(__file__).parents[2] / "fixtures" / "runner" / "recipe-ci.json").read_bytes()
        assert json.loads(committed)["recipe_version"] == 1
        loaded = load_recipe(committed)
        assert loaded.recipe.recipe_version == 2 and loaded.recipe.output.bands

    def test_conversion_notes_read_the_steps_of_the_document_not_the_recipe(self) -> None:
        document = {"steps": [{"op": "reproject", "op_version": 3, "params": {}}]}
        provenance = load_recipe(support.recipe_file(support.band_math_recipe(), engine=_engine("0.4.3"))).provenance
        assert conversion_notes(document, provenance) and not conversion_notes({"steps": []}, provenance)

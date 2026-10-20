"""``python -m earthx.runner``: refusals, failures and misuse, each with its exit code (adr/0016 §4.2, §7.2, §12b).

Run in this process through :func:`earthx.runner.cli.main`, with the synthetic registry
and the seams of `tests/earthx/processing/sources.py`; the comparison with the job runs
in fresh processes (``test_compare.py``).
"""

from __future__ import annotations

import json
import multiprocessing
import socket
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from earthx.catalog.registry import DatasetRegistry
from earthx.runner import output
from earthx.runner.cli import EXIT_HOST, EXIT_OK, EXIT_OTHER, EXIT_RECIPE, EXIT_SOURCE, exit_code, main
from earthx.runner.recipe_file import MAX_RECIPE_BYTES, HostRefused, check_hosts, load_recipe
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import crop_data
from tests.earthx.runner import support, targets

FORBIDDEN = (
    "psycopg",
    "psycopg_pool",
    "asyncpg",
    "botocore",
    "boto3",
    "earthx.objectstore",
    "earthx.jobs",
    "earthx.api",
)


@pytest.fixture(scope="module")
def cogs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("bands")
    return {
        sources.url("red"): sources.build_band_cog(root / "red.tif", sources.ramp(support.WIDTH, support.HEIGHT, 1200)),
        sources.url("nir"): sources.build_band_cog(root / "nir.tif", sources.ramp(support.WIDTH, support.HEIGHT, 3400)),
    }


@pytest.fixture
def served(cogs: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The addresses that passed ``check_url`` and were opened, in order."""
    return sources.serve(cogs, monkeypatch)


@pytest.fixture
def out(tmp_path: Path) -> Path:
    path = tmp_path / "out"
    path.mkdir()
    return path


def _file(tmp_path: Path, content: bytes | dict[str, Any]) -> str:
    path = tmp_path / "recipe.json"
    path.write_bytes(content if isinstance(content, bytes) else support.recipe_file(content))
    return str(path)


def _main(*args: str, registry: DatasetRegistry | None = None) -> int:
    return main(list(args), registry=support.registry() if registry is None else registry)


def _document(recipe: dict[str, Any] | None = None) -> dict[str, Any]:
    return json.loads(support.recipe_file(recipe or support.band_math_recipe()))


class TestARun:
    def test_it_leaves_result_mask_recipe_and_provenance_in_a_new_folder(
        self, tmp_path: Path, out: Path, served: list[str], capsys: pytest.CaptureFixture[str]
    ) -> None:
        recipe = _file(tmp_path, support.band_math_recipe())
        assert _main("run", recipe, "--out", str(out)) == EXIT_OK
        (folder,) = out.iterdir()
        assert sorted(path.name for path in folder.iterdir()) == [
            "mask.tif",
            "provenance.json",
            "recipe.json",
            "result.tif",
        ]
        assert capsys.readouterr().out.strip() == str(folder)
        assert (folder / "recipe.json").read_bytes() == Path(recipe).read_bytes()

    def test_its_provenance_says_local_and_self_attested_with_the_versions(
        self, tmp_path: Path, out: Path, served: list[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EARTHX_COMMIT", "1a2b3c4")
        assert _main("run", _file(tmp_path, support.band_math_recipe()), "--out", str(out)) == EXIT_OK
        (folder,) = out.iterdir()
        provenance = json.loads((folder / "provenance.json").read_text(encoding="utf-8"))
        assert (provenance["execution"], provenance["kind"], provenance["self_attested"]) == ("local", "job", True)
        assert provenance["runner_version"].endswith("+g1a2b3c4")
        assert set(provenance["engine"]) == {"earthx", "gdal", "rasterio", "numexpr", "numpy"}
        assert set(provenance["platform"]) == {"machine", "numpy_dispatch"}
        assert provenance["source_engine"] == provenance["engine"]
        assert provenance["attribution"] == support.ATTRIBUTION
        assert provenance["properties"]["processing:lineage"]

    def test_two_runs_never_share_a_folder(self, tmp_path: Path, out: Path, served: list[str]) -> None:
        recipe = _file(tmp_path, support.band_math_recipe())
        assert _main("run", recipe, "--out", str(out)) == EXIT_OK
        assert _main("run", recipe, "--out", str(out)) == EXIT_OK
        assert len(list(out.iterdir())) == 2

    def test_what_it_prints_and_keeps_names_no_address_no_coordinate_and_no_recipe_id(
        self, tmp_path: Path, out: Path, served: list[str], capsys: pytest.CaptureFixture[str]
    ) -> None:
        recipe = support.band_math_recipe()
        assert _main("run", _file(tmp_path, recipe), "--out", str(out)) == EXIT_OK
        (folder,) = out.iterdir()
        printed = capsys.readouterr()
        assert printed.err, "the run says something"
        text = printed.out + printed.err + (folder / "provenance.json").read_text(encoding="utf-8")
        assert "https://" not in text and "/products/" not in text
        assert recipe["recipe_id"] not in text
        for lon, lat in recipe["aoi"]["coordinates"][0]:
            assert f"{lon:.4f}" not in text and f"{lat:.4f}" not in text

    def test_a_folder_that_exists_is_never_overwritten(
        self, tmp_path: Path, out: Path, served: list[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(output.secrets, "token_urlsafe", lambda size: "taken")
        (out / "taken").mkdir()
        (out / "taken" / "result.tif").write_bytes(b"earlier")
        assert _main("run", _file(tmp_path, support.band_math_recipe()), "--out", str(out)) == EXIT_OTHER
        assert [path.name for path in (out / "taken").iterdir()] == ["result.tif"]
        assert (out / "taken" / "result.tif").read_bytes() == b"earlier"
        assert served == []

    def test_an_output_folder_that_is_missing(self, tmp_path: Path, served: list[str]) -> None:
        recipe = _file(tmp_path, support.band_math_recipe())
        assert _main("run", recipe, "--out", str(tmp_path / "missing")) == EXIT_OTHER

    def test_a_run_that_fails_leaves_no_provenance_and_no_work_files(
        self, tmp_path: Path, out: Path, cogs: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sources.serve({**cogs, sources.url("nir"): tmp_path / "gone.tif"}, monkeypatch)
        assert _main("run", _file(tmp_path, support.band_math_recipe()), "--out", str(out)) == EXIT_OTHER
        (folder,) = out.iterdir()
        assert list(folder.iterdir()) == []

    def test_a_folder_that_cannot_be_finished_is_named_and_left_without_provenance(
        self, tmp_path: Path, out: Path, served: list[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def full(*args: object, **kwargs: object) -> None:
            raise OSError("no space left on device")

        monkeypatch.setattr(output, "provenance_document", full)
        assert _main("run", _file(tmp_path, support.band_math_recipe()), "--out", str(out)) == EXIT_OTHER
        (folder,) = out.iterdir()
        assert sorted(path.name for path in folder.iterdir()) == ["mask.tif", "recipe.json", "result.tif"]


class TestRefusedBeforeReading:
    def test_check_names_the_hosts_and_reads_nothing(
        self, tmp_path: Path, served: list[str], capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert _main("check", _file(tmp_path, support.band_math_recipe())) == EXIT_OK
        assert capsys.readouterr().out.splitlines() == [support.HOST]
        assert served == []

    def test_a_host_the_dataset_does_not_declare(
        self, tmp_path: Path, out: Path, served: list[str], capsys: pytest.CaptureFixture[str]
    ) -> None:
        recipe = support.band_math_recipe()
        recipe["inputs"][0]["resolved"][1]["asset"]["href"] = "https://elsewhere.example.invalid/nir.tif"
        assert _main("run", _file(tmp_path, recipe), "--out", str(out)) == EXIT_HOST
        assert served == [] and list(out.iterdir()) == []
        assert "elsewhere" not in capsys.readouterr().err

    def test_a_dataset_this_image_does_not_know(self, tmp_path: Path, out: Path, served: list[str]) -> None:
        empty = DatasetRegistry(())
        assert _main("run", _file(tmp_path, support.band_math_recipe()), "--out", str(out), registry=empty) == EXIT_HOST
        assert served == []

    def test_the_hosts_are_checked_per_input_against_its_own_dataset(self, tmp_path: Path, served: list[str]) -> None:
        synthetic = support.registry().get("synthetic")
        other = replace(
            synthetic, dataset_id="other", source=replace(synthetic.source, asset_hosts=("other.example.invalid",))
        )
        recipe = support.band_math_recipe()
        second = json.loads(json.dumps(recipe["inputs"][0]))
        second["name"], second["dataset"] = "b", "other"
        for entry in second["resolved"]:
            entry["asset"]["dataset_id"] = "other"
        recipe["inputs"].append(second)
        registry = DatasetRegistry((synthetic, other))
        loaded = load_recipe(support.recipe_file(recipe))  # two inputs: the core refuses it later, the hosts first
        with pytest.raises(HostRefused, match="'other'"):
            check_hosts(loaded.recipe, registry)
        assert check_hosts(loaded.recipe, DatasetRegistry((synthetic, replace(other, source=synthetic.source)))) == (
            support.HOST,
        )

    @pytest.mark.parametrize(
        "href",
        [
            f"http://{support.HOST}/products/nir.tif",
            f"https://{support.HOST}:8443/products/nir.tif",
            f"https://user:secret@{support.HOST}/products/nir.tif",
        ],
        ids=["http", "port", "credentials"],
    )
    def test_an_address_on_a_declared_host_that_api_would_refuse(
        self, tmp_path: Path, out: Path, served: list[str], capsys: pytest.CaptureFixture[str], href: str
    ) -> None:
        """The same check as at acceptance in `api`: scheme, credentials and port too, before any read."""
        recipe = support.band_math_recipe()
        recipe["inputs"][0]["resolved"][1]["asset"]["href"] = href
        assert _main("run", _file(tmp_path, recipe), "--out", str(out)) == EXIT_HOST
        assert served == [] and list(out.iterdir()) == []
        assert "secret" not in capsys.readouterr().err

    def test_a_recipe_the_core_does_not_run_is_refused_before_any_folder(
        self, tmp_path: Path, out: Path, served: list[str]
    ) -> None:
        recipe = support.band_math_recipe()
        second = json.loads(json.dumps(recipe["inputs"][0]))
        second["name"] = "b"
        recipe["inputs"].append(second)
        assert _main("check", _file(tmp_path, recipe)) == EXIT_RECIPE
        assert _main("run", _file(tmp_path, recipe), "--out", str(out)) == EXIT_RECIPE
        assert served == [] and list(out.iterdir()) == []


class TestARecipeFileThatIsNotOne:
    @pytest.mark.parametrize(
        "content",
        [
            b"not json",
            b"[]",
            b'{"recipe_version": 1, "recipe_version": 1}',
            b'{"recipe_version": NaN}',
        ],
        ids=["not-json", "array", "duplicate-key", "nan"],
    )
    def test_text_that_is_no_recipe(self, tmp_path: Path, content: bytes) -> None:
        assert _main("check", _file(tmp_path, content)) == EXIT_RECIPE

    def test_a_file_too_large(self, tmp_path: Path) -> None:
        assert _main("check", _file(tmp_path, b" " * (MAX_RECIPE_BYTES + 1))) == EXIT_RECIPE

    def test_a_file_that_is_not_there(self, tmp_path: Path) -> None:
        assert _main("check", str(tmp_path / "missing.json")) == EXIT_RECIPE

    def test_a_recipe_without_resolved_addresses(self, tmp_path: Path) -> None:
        document = _document()
        del document["inputs"][0]["resolved"]
        assert _main("check", _file(tmp_path, json.dumps(document).encode())) == EXIT_RECIPE

    def test_an_unknown_recipe_version_names_the_one_this_runner_runs(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        document = _document()
        document["recipe_version"] = 2
        assert _main("check", _file(tmp_path, json.dumps(document).encode())) == EXIT_RECIPE
        error = capsys.readouterr().err
        assert "recipe_version 1" in error and output.runner_version() in error

    def test_an_unknown_op_version(self, tmp_path: Path) -> None:
        document = _document()
        document["steps"][0]["op_version"] = 9
        assert _main("check", _file(tmp_path, json.dumps(document).encode())) == EXIT_RECIPE

    @pytest.mark.parametrize("expression", ["log(red)", "red & 1", "nir ** 0.5", "__import__('os')"])
    def test_an_expression_outside_r5_never_reaches_numexpr(
        self, tmp_path: Path, out: Path, served: list[str], monkeypatch: pytest.MonkeyPatch, expression: str
    ) -> None:
        def never(*args: object, **kwargs: object) -> None:
            raise AssertionError("numexpr saw a refused expression")

        monkeypatch.setattr("numexpr.evaluate", never)
        recipe = _file(tmp_path, support.band_math_recipe(expression))
        assert _main("run", recipe, "--out", str(out)) == EXIT_RECIPE
        assert served == [] and list(out.iterdir()) == []

    def test_a_crop_comes_from_the_platform(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        recipe = crop_data()
        recipe["inputs"][0]["resolved"][0]["asset"]["href"] = sources.url("visual")
        assert _main("check", _file(tmp_path, recipe)) == EXIT_RECIPE
        assert "crop comes from the platform" in capsys.readouterr().err


class TestTheProvenanceBlock:
    def test_a_file_without_one_is_no_recipe_of_a_result(self, tmp_path: Path) -> None:
        document = _document()
        del document["provenance"]
        assert _main("check", _file(tmp_path, json.dumps(document).encode())) == EXIT_RECIPE

    def test_one_that_does_not_validate(self, tmp_path: Path) -> None:
        document = _document()
        document["provenance"]["execution"] = "elsewhere"
        assert _main("check", _file(tmp_path, json.dumps(document).encode())) == EXIT_RECIPE

    def test_one_of_a_local_run(self, tmp_path: Path) -> None:
        document = _document()
        document["provenance"].update(execution="local", self_attested=True, runner_version="0.4.1+unknown")
        assert _main("check", _file(tmp_path, json.dumps(document).encode())) == EXIT_RECIPE

    @pytest.mark.parametrize("field", ["execution", "runner_version", "self_attested"])
    def test_provenance_fields_beside_the_recipe(self, tmp_path: Path, field: str) -> None:
        document = _document()
        document[field] = document["provenance"][field]
        assert _main("check", _file(tmp_path, json.dumps(document).encode())) == EXIT_RECIPE

    def test_other_versions_of_the_platform_are_named_not_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        engine = {
            **json.loads(support.recipe_file(support.band_math_recipe()))["provenance"]["engine"],
            "earthx": "0.0.1",
        }
        assert (
            _main("check", _file(tmp_path, support.recipe_file(support.band_math_recipe(), engine=engine))) == EXIT_OK
        )
        error = capsys.readouterr().err
        assert "other versions of earthx" in error and "0.0.1" not in error


class TestReadingFails:
    def test_without_a_network_the_host_does_not_resolve_and_the_code_is_4(
        self, tmp_path: Path, out: Path, cogs: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """What `--network none` sees (adr/0016 §12b): the real resolver, no answer."""

        def no_network(*args: object, **kwargs: object) -> None:
            raise socket.gaierror("no network")

        monkeypatch.setattr("earthx.readers.cog.vsicurl_path", lambda checked: str(cogs[checked.url]))
        monkeypatch.setattr(socket, "getaddrinfo", no_network)
        assert _main("run", _file(tmp_path, support.band_math_recipe()), "--out", str(out)) == EXIT_SOURCE
        (folder,) = out.iterdir()
        assert list(folder.iterdir()) == []

    @pytest.mark.parametrize(
        ("kind", "code"),
        [
            ("recipe_invalid", EXIT_RECIPE),
            ("unsupported_recipe", EXIT_RECIPE),
            ("rejected", EXIT_SOURCE),
            ("source_timeout", EXIT_SOURCE),
            ("source_unreachable", EXIT_SOURCE),
            ("source_5xx", EXIT_SOURCE),
            ("source_4xx", EXIT_SOURCE),
            ("source_429", EXIT_SOURCE),
            ("scaling_mismatch", EXIT_OTHER),
            ("aoi_outside_inputs", EXIT_OTHER),
            ("out_of_memory", EXIT_OTHER),
            ("unknown", EXIT_OTHER),
        ],
    )
    def test_every_kind_of_failure_has_its_code(self, kind: str, code: int) -> None:
        assert exit_code(kind) == code


class TestTheCommandLine:
    @pytest.mark.parametrize("args", [[], ["compute"], ["run"], ["check", "a.json", "extra"]])
    def test_a_command_that_is_not_one(self, args: list[str]) -> None:
        assert main(args) == EXIT_RECIPE

    def test_help_is_no_failure(self) -> None:
        assert main(["--help"]) == EXIT_OK

    def test_versions_is_json_with_engine_runner_and_platform(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["versions"]) == EXIT_OK
        versions = json.loads(capsys.readouterr().out)
        assert set(versions) == {"runner_version", "engine", "platform"}

    @pytest.mark.parametrize(
        ("commit", "suffix"),
        [
            ("1a2b3c4", "+g1a2b3c4"),
            ("ABCDEF0", "+gabcdef0"),
            ("", "+unknown"),
            ("not-a-commit", "+unknown"),
            ("1a2", "+unknown"),
        ],
    )
    def test_the_runner_version_carries_a_valid_commit_only(
        self, monkeypatch: pytest.MonkeyPatch, commit: str, suffix: str
    ) -> None:
        monkeypatch.setenv("EARTHX_COMMIT", commit)
        assert output.runner_version().endswith(suffix)

    def test_numpy_says_its_dispatch_level_here(self) -> None:
        """K3: a private attribute of numpy; this test fails first when a new numpy drops it."""
        assert output.numpy_dispatch() in ("X86_V4", "X86_V3", "X86_V2", "ASIMD")


def test_importing_the_runner_loads_no_database_no_object_store_and_no_other_shell() -> None:
    """adr/0016 F2 with its condition: a fresh process, `boto3` hidden as in the image."""
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(target=targets.probe_modules, args=(child,))
    process.start()
    child.close()
    try:
        assert parent.poll(60), "the probe did not answer"
        loaded = parent.recv()
    finally:
        process.join(60)
        process.kill()
    assert "earthx.runner.cli" in loaded and "earthx.processing" in loaded
    assert [name for name in loaded if name.split(".")[0] in FORBIDDEN or name.startswith(FORBIDDEN)] == []

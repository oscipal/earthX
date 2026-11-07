"""Reading the registry from its directories, and the start check for prototype entries (M5-13 plan §3.1, §3.5).

The prototype entries are synthetic: a copy of a real entry with the prefix, ``unclear`` and a note, on the reserved
host of the runner's fixtures (adr/0024 R10). Every test that sets the variables clears the cache of ``registry()``
before and after, so no other test sees its registry.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from earthx.catalog import datasets, load
from earthx.catalog.datasets import (
    CATALOG_DIR,
    PROFILE_VARIABLE,
    PROTOTYPE_VARIABLE,
    InstanceSettingError,
    prototype_dir_from_env,
    read_registry,
    registry,
)
from earthx.catalog.entry_files import EntryFileError, to_plain
from earthx.catalog.registry import PROTOTYPE_PREFIX, DatasetConfig, LegalStatus, UnknownDatasetError
from earthx.discovery import materialize
from earthx.runner.recipe_file import HostRefused, check_hosts, load_recipe
from tests.catalog.entries import SENTINEL_2_L2A
from tests.earthx.runner import support

PROTOTYPE_ID = "proto-synthetic"
NOTE = "The terms of use of the source name no licence."


def _prototype() -> DatasetConfig:
    return replace(
        SENTINEL_2_L2A,
        dataset_id=PROTOTYPE_ID,
        legal_status=LegalStatus.UNCLEAR,
        legal_note=NOTE,
        source=replace(SENTINEL_2_L2A.source, asset_hosts=(support.HOST,)),
    )


def _write(directory: Path, entry: DatasetConfig) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{entry.dataset_id}.yaml"
    path.write_text(yaml.safe_dump(to_plain(entry), sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


@pytest.fixture
def catalog(tmp_path: Path) -> Path:
    """A copy of the real catalogue directory, to change one thing in."""
    copy = tmp_path / "catalog"
    shutil.copytree(CATALOG_DIR / "datasets", copy / "datasets")
    shutil.copy(CATALOG_DIR / "retired.yaml", copy / "retired.yaml")
    return copy


@pytest.fixture
def prototypes(tmp_path: Path) -> Path:
    directory = tmp_path / "prototype"
    _write(directory, _prototype())
    return directory


@pytest.fixture
def fresh_registry():
    registry.cache_clear()
    yield
    registry.cache_clear()


class TestTheDirectories:
    def test_the_registry_holds_exactly_the_files(self) -> None:
        names = sorted(path.stem for path in (CATALOG_DIR / "datasets").glob("*.yaml"))
        assert sorted(entry.dataset_id for entry in read_registry()) == names

    def test_the_registry_of_the_process_is_read_once(self) -> None:
        assert registry() is registry()

    def test_a_readme_is_allowed(self, catalog: Path) -> None:
        (catalog / "datasets" / "README.md").write_text("notes", encoding="utf-8")
        assert len(read_registry(catalog)) == len(read_registry())

    @pytest.mark.parametrize("name", ["cop-dem-glo-30.yml", "notes.txt", "README.yaml.bak"])
    def test_a_stray_file_is_an_error(self, catalog: Path, name: str) -> None:
        (catalog / "datasets" / name).write_text("x: 1", encoding="utf-8")
        with pytest.raises(EntryFileError, match="only <dataset_id>.yaml files and a README"):
            read_registry(catalog)

    def test_a_directory_inside_is_an_error(self, catalog: Path) -> None:
        (catalog / "datasets" / "nested.yaml").mkdir()
        with pytest.raises(EntryFileError, match="only <dataset_id>.yaml files"):
            read_registry(catalog)

    def test_an_unclear_entry_among_the_released_is_an_error(self, catalog: Path) -> None:
        _write(catalog / "datasets", _prototype())
        with pytest.raises(EntryFileError, match="datasets/proto-synthetic.yaml: an entry here has legal_status cleared"):
            read_registry(catalog)

    def test_a_cleared_entry_among_the_prototypes_is_an_error(self, catalog: Path, tmp_path: Path) -> None:
        _write(tmp_path / "prototype", replace(SENTINEL_2_L2A, dataset_id="released-copy"))
        with pytest.raises(EntryFileError, match="an entry here has legal_status unclear"):
            read_registry(catalog, tmp_path / "prototype")

    def test_prototype_entries_join_the_released_ones(self, catalog: Path, prototypes: Path) -> None:
        loaded = read_registry(catalog, prototypes)
        assert loaded.get(PROTOTYPE_ID) == _prototype()
        assert len(loaded) == len(read_registry()) + 1

    def test_a_retired_list_that_is_missing_is_an_error(self, catalog: Path) -> None:
        (catalog / "retired.yaml").unlink()
        with pytest.raises(EntryFileError, match="retired.yaml"):
            read_registry(catalog)


class TestTheStartCheck:
    """adr/0024 R5 and the table of the plan, §3.5."""

    @pytest.mark.parametrize(
        "environ",
        [{}, {PROTOTYPE_VARIABLE: ""}, {PROTOTYPE_VARIABLE: "  "}, {PROFILE_VARIABLE: "cloud"}, {"CI": "true"}],
        ids=["nothing", "empty-path", "blank-path", "profile-without-path", "ci-without-path"],
    )
    def test_without_a_path_no_prototype_is_read(self, environ: dict[str, str]) -> None:
        assert prototype_dir_from_env(environ) is None

    @pytest.mark.parametrize("profile", ["local", "ci", "cloud", ""])
    def test_every_known_profile_is_accepted_without_a_path(self, profile: str) -> None:
        assert prototype_dir_from_env({PROFILE_VARIABLE: profile}) is None

    def test_path_local_and_no_ci_reads_the_directory(self, prototypes: Path) -> None:
        environ = {PROTOTYPE_VARIABLE: str(prototypes), PROFILE_VARIABLE: "local"}
        assert prototype_dir_from_env(environ) == prototypes

    @pytest.mark.parametrize("profile", [None, "", "ci", "cloud"])
    def test_a_path_without_the_local_profile_stops_the_start(self, prototypes: Path, profile: str | None) -> None:
        environ = {PROTOTYPE_VARIABLE: str(prototypes)}
        if profile is not None:
            environ[PROFILE_VARIABLE] = profile
        with pytest.raises(InstanceSettingError, match="is not local"):
            prototype_dir_from_env(environ)

    @pytest.mark.parametrize("ci", ["true", "1", "false"])
    def test_a_path_in_ci_stops_the_start(self, prototypes: Path, ci: str) -> None:
        environ = {PROTOTYPE_VARIABLE: str(prototypes), PROFILE_VARIABLE: "local", "CI": ci}
        with pytest.raises(InstanceSettingError, match="is set in CI"):
            prototype_dir_from_env(environ)

    def test_a_path_that_is_no_directory_stops_the_start(self, tmp_path: Path) -> None:
        environ = {PROTOTYPE_VARIABLE: str(tmp_path / "missing"), PROFILE_VARIABLE: "local"}
        with pytest.raises(InstanceSettingError, match="names no directory"):
            prototype_dir_from_env(environ)

    @pytest.mark.parametrize("profile", ["production", "Local", "local ci"])
    def test_an_unknown_profile_stops_the_start(self, profile: str) -> None:
        with pytest.raises(InstanceSettingError, match="other than local, ci, cloud"):
            prototype_dir_from_env({PROFILE_VARIABLE: profile})

    def test_the_message_names_the_variables_and_not_the_path(self, tmp_path: Path) -> None:
        secret_place = tmp_path / "secret-place"
        with pytest.raises(InstanceSettingError) as raised:
            prototype_dir_from_env({PROTOTYPE_VARIABLE: str(secret_place), PROFILE_VARIABLE: "cloud"})
        assert PROTOTYPE_VARIABLE in str(raised.value)
        assert "secret-place" not in str(raised.value)


@pytest.mark.usefixtures("fresh_registry")
class TestTheProcessRegistry:
    def test_without_the_switch_no_prototype_is_loaded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(PROTOTYPE_VARIABLE, raising=False)
        loaded = registry()
        assert all(entry.legal_status is LegalStatus.CLEARED for entry in loaded)
        assert not any(entry.dataset_id.startswith(PROTOTYPE_PREFIX) for entry in loaded)

    def test_with_the_switch_in_a_local_instance_the_prototype_is_loaded(
        self, monkeypatch: pytest.MonkeyPatch, prototypes: Path
    ) -> None:
        monkeypatch.setenv(PROTOTYPE_VARIABLE, str(prototypes))
        monkeypatch.setenv(PROFILE_VARIABLE, "local")
        monkeypatch.delenv("CI", raising=False)
        assert registry().get(PROTOTYPE_ID).legal_status is LegalStatus.UNCLEAR

    def test_the_switch_in_ci_stops_the_process(self, monkeypatch: pytest.MonkeyPatch, prototypes: Path) -> None:
        monkeypatch.setenv(PROTOTYPE_VARIABLE, str(prototypes))
        monkeypatch.setenv(PROFILE_VARIABLE, "local")
        monkeypatch.setenv("CI", "true")
        with pytest.raises(InstanceSettingError):
            registry()

    @pytest.mark.parametrize("command", ["catalog-load", "materialize"])
    def test_the_commands_stop_with_the_reason(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], command: str
    ) -> None:
        monkeypatch.setenv(PROFILE_VARIABLE, "production")
        if command == "catalog-load":
            code = load.main()
        else:
            code = materialize.main([SENTINEL_2_L2A.dataset_id])
        assert code == 1
        assert f"{PROFILE_VARIABLE} is set to a profile other than" in capsys.readouterr().err


@pytest.mark.usefixtures("fresh_registry")
class TestTheRunner:
    """adr/0024 R5 and test 5: the runner never loads a prototype entry, the switch set or not."""

    @pytest.fixture
    def switched_on(self, monkeypatch: pytest.MonkeyPatch, prototypes: Path) -> None:
        monkeypatch.setenv(PROTOTYPE_VARIABLE, str(prototypes))
        monkeypatch.setenv(PROFILE_VARIABLE, "local")
        monkeypatch.delenv("CI", raising=False)

    @pytest.mark.usefixtures("switched_on")
    def test_its_registry_has_no_prototype_and_says_so(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger=datasets.__name__):
            released = registry(prototype=False)
        with pytest.raises(UnknownDatasetError):
            released.get(PROTOTYPE_ID)
        assert PROTOTYPE_VARIABLE in caplog.text
        assert registry().get(PROTOTYPE_ID)

    @pytest.mark.usefixtures("switched_on")
    def test_a_recipe_of_a_prototype_dataset_is_unknown_to_it(self) -> None:
        recipe = support.band_math_recipe()
        for entry in recipe["inputs"]:
            entry["dataset"] = PROTOTYPE_ID
            for resolved in entry["resolved"]:
                resolved["asset"]["dataset_id"] = PROTOTYPE_ID
        loaded = load_recipe(support.recipe_file(recipe))
        with pytest.raises(HostRefused, match="not known to this runner"):
            check_hosts(loaded.recipe)

    def test_without_the_switch_it_warns_nothing(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.delenv(PROTOTYPE_VARIABLE, raising=False)
        with caplog.at_level(logging.WARNING, logger=datasets.__name__):
            registry(prototype=False)
        assert PROTOTYPE_VARIABLE not in caplog.text


def test_the_prototype_entries_in_the_repo_are_well_formed() -> None:
    """adr/0024 R10: CI parses and checks them like every entry, without a registry and without the network."""
    directory = CATALOG_DIR / "prototype"
    assert (directory / "README.md").is_file()
    for entry in datasets._entries(directory, LegalStatus.UNCLEAR):
        assert entry.dataset_id.startswith(PROTOTYPE_PREFIX)

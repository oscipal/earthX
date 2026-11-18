"""The limits per host in ``backend/catalog/hosts.yaml`` (M5-36 §3.1, G1 = 1, G2 = 1).

Read as strictly as the entries; every host the registry reads from has an entry and every entry a host. Files with
mistakes are written to ``tmp_path``; the prototype hosts live on the reserved host of the runner's fixtures.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from earthx.catalog.datasets import CATALOG_DIR, read_registry
from earthx.catalog.entry_files import EntryFileError
from earthx.catalog.hosts import HostLimit, load_host_limits
from earthx.catalog.registry import ConfigError, DatasetRegistry, source_hosts
from earthx.catalog.sources import read_sources
from earthx.gateway.policy import MAX_INTERVAL_S
from tests.catalog.entries import COP_DEM_GLO_30, SENTINEL_2_L2A
from tests.catalog.test_registry_loading import PROTOTYPE_HOSTS, _prototype, _write

BUCKET = "copernicus-dem-30m.s3.amazonaws.com"


def _hosts(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "hosts.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def _one(body: str, host: str = BUCKET) -> str:
    return f"hosts:\n  {host}:\n{body}"


@pytest.fixture
def catalog(tmp_path: Path) -> Path:
    copy = tmp_path / "catalog"
    shutil.copytree(CATALOG_DIR / "datasets", copy / "datasets")
    for name in ("retired.yaml", "categories.yaml", "hosts.yaml"):
        shutil.copy(CATALOG_DIR / name, copy / name)
    shutil.copytree(CATALOG_DIR / "sources", copy / "sources")
    return copy


class TestTheReleasedFile:
    def test_every_host_of_the_registry_and_the_seed_has_limits_and_no_more(self) -> None:
        loaded = read_registry()
        seed = {source.host for source in read_sources(CATALOG_DIR / "sources").values()}
        assert set(loaded.host_limits) == {host for entry in loaded for host in source_hosts(entry)} | seed

    def test_a_source_whose_host_has_no_limits_is_an_error(self, catalog: Path) -> None:
        # M5-19 F6: the hosts of the harvest seed have their limits in the same file.
        text = (catalog / "hosts.yaml").read_text(encoding="utf-8")
        (catalog / "hosts.yaml").write_text(text.split("  ckan.govdata.de:")[0], encoding="utf-8")
        with pytest.raises(ConfigError, match="no limits for ckan.govdata.de, ckan.opendata.swiss, www.data.gv.at"):
            read_registry(catalog)

    def test_limits_of_a_catalogue_host_without_its_source_are_an_error(self, catalog: Path) -> None:
        (catalog / "sources" / "govdata.yaml").unlink()
        with pytest.raises(ConfigError, match="no entry or source reads from: ckan.govdata.de"):
            read_registry(catalog)

    def test_the_catalogue_hosts_otto_chose(self) -> None:
        # M5-19 F6 = 1: two connections, one second apart.
        limits = read_registry().host_limits
        for host in ("ckan.govdata.de", "ckan.opendata.swiss", "www.data.gv.at"):
            assert (limits[host].connections, limits[host].interval_s) == (2, 1.0)

    def test_the_values_otto_chose(self) -> None:
        limits = read_registry().host_limits
        assert (limits["data.geo.admin.ch"].connections, limits["data.geo.admin.ch"].interval_s) == (6, 1.0)
        assert (
            limits["earth-search.aws.element84.com"].connections,
            limits["earth-search.aws.element84.com"].interval_s,
        ) == (6, None)
        buckets = [host for host in limits if ".s3." in host]
        assert len(buckets) == 4 and all(
            limits[host].connections == 32 and limits[host].interval_s is None for host in buckets
        )

    def test_a_missing_file_stops_the_registry_and_names_it(self, catalog: Path) -> None:
        (catalog / "hosts.yaml").unlink()
        with pytest.raises(EntryFileError, match="hosts.yaml"):
            read_registry(catalog)


class TestTheShapeOfTheFile:
    def test_a_well_formed_entry(self, tmp_path: Path) -> None:
        loaded = load_host_limits(_hosts(tmp_path, _one("    connections: 4\n    interval_s: 0.5\n    reason: why\n")))
        assert loaded == {BUCKET: HostLimit(4, 0.5, "why")}

    def test_an_interval_is_optional_and_a_whole_number_of_seconds_is_a_float(self, tmp_path: Path) -> None:
        loaded = load_host_limits(_hosts(tmp_path, _one("    connections: 1\n    interval_s: 2\n    reason: why\n")))
        assert loaded[BUCKET].interval_s == 2.0 and isinstance(loaded[BUCKET].interval_s, float)
        assert (
            load_host_limits(_hosts(tmp_path, _one("    connections: 1\n    reason: why\n")))[BUCKET].interval_s is None
        )

    @pytest.mark.parametrize(
        "text",
        [
            "[]\n",
            "hosts: []\n",
            "hosts: {}\n",
            "other: 1\n",
            f"hosts:\n  {BUCKET}:\n    connections: 1\n    reason: x\nmore: 1\n",
        ],
    )
    def test_anything_but_one_mapping_of_hosts_is_refused(self, tmp_path: Path, text: str) -> None:
        with pytest.raises(EntryFileError, match="one key 'hosts'"):
            load_host_limits(_hosts(tmp_path, text))

    @pytest.mark.parametrize(
        ("host", "message"),
        [
            ("127.0.0.1", "not a host name"),
            ("no-dot", "not a host name"),
            ("Bucket.Example.org", "write the host as bucket.example.org"),
        ],
    )
    def test_a_host_in_another_spelling_or_no_name_is_refused(self, tmp_path: Path, host: str, message: str) -> None:
        with pytest.raises(EntryFileError, match=message):
            load_host_limits(_hosts(tmp_path, _one("    connections: 1\n    reason: x\n", host=f"'{host}'")))

    @pytest.mark.parametrize(
        "body",
        ["    connections: 1\n", "    reason: x\n", "    connections: 1\n    reason: x\n    burst: 3\n", "    7\n"],
    )
    def test_a_missing_or_unknown_field_is_refused(self, tmp_path: Path, body: str) -> None:
        with pytest.raises(EntryFileError, match="needs connections and reason"):
            load_host_limits(_hosts(tmp_path, _one(body)))

    @pytest.mark.parametrize("value", ["0", "-1", "257", "true", "1.5", "'6'", "null"])
    def test_connections_outside_1_to_256_are_refused(self, tmp_path: Path, value: str) -> None:
        with pytest.raises(EntryFileError, match="connections is a whole number from 1 to 256"):
            load_host_limits(_hosts(tmp_path, _one(f"    connections: {value}\n    reason: x\n")))

    @pytest.mark.parametrize("value", ["-0.1", str(MAX_INTERVAL_S + 1), "true", "'1'", ".nan"])
    def test_an_interval_outside_0_to_300_seconds_is_refused(self, tmp_path: Path, value: str) -> None:
        with pytest.raises(EntryFileError, match="interval_s is a number of seconds"):
            load_host_limits(_hosts(tmp_path, _one(f"    connections: 1\n    interval_s: {value}\n    reason: x\n")))

    @pytest.mark.parametrize("value", ["''", "'  '", "3", "null"])
    def test_a_reason_is_text(self, tmp_path: Path, value: str) -> None:
        with pytest.raises(EntryFileError, match="reason is text"):
            load_host_limits(_hosts(tmp_path, _one(f"    connections: 1\n    reason: {value}\n")))

    def test_a_host_named_twice_is_refused(self, tmp_path: Path) -> None:
        entry = f"  {BUCKET}:\n    connections: 1\n    reason: x\n"
        with pytest.raises(EntryFileError, match="duplicate key"):
            load_host_limits(_hosts(tmp_path, "hosts:\n" + entry + entry))


class TestWhereTheRegistryMeetsTheFile:
    def test_a_host_without_limits_is_refused(self) -> None:
        with pytest.raises(ConfigError, match=f"no limits for {BUCKET}"):
            DatasetRegistry((COP_DEM_GLO_30,), hosts={})

    def test_limits_for_a_host_no_entry_reads_from_are_refused(self) -> None:
        hosts = {BUCKET: HostLimit(1, None, "x"), "spare.example.org": HostLimit(1, None, "x")}
        with pytest.raises(ConfigError, match="no entry or source reads from: spare.example.org"):
            DatasetRegistry((COP_DEM_GLO_30,), hosts=hosts)

    def test_a_registry_built_without_the_file_has_none(self) -> None:
        assert DatasetRegistry((SENTINEL_2_L2A,)).host_limits == {}


class TestPrototypeHosts:
    def test_the_prototype_directory_adds_the_limits_of_its_own_hosts(self, catalog: Path, tmp_path: Path) -> None:
        directory = tmp_path / "prototype"
        _write(directory, _prototype())
        (directory / "hosts.yaml").write_text(PROTOTYPE_HOSTS, encoding="utf-8")
        loaded = read_registry(catalog, directory)
        assert len(loaded.host_limits) == len(read_registry().host_limits) + 1

    def test_a_prototype_host_without_limits_stops_the_registry(self, catalog: Path, tmp_path: Path) -> None:
        directory = tmp_path / "prototype"
        _write(directory, _prototype())
        with pytest.raises(ConfigError, match="no limits for"):
            read_registry(catalog, directory)

    def test_a_host_with_limits_in_both_files_is_refused(self, catalog: Path, tmp_path: Path) -> None:
        directory = tmp_path / "prototype"
        _write(directory, _prototype())
        (directory / "hosts.yaml").write_text(
            PROTOTYPE_HOSTS + _one("    connections: 1\n    reason: x\n").removeprefix("hosts:\n"), encoding="utf-8"
        )
        with pytest.raises(EntryFileError, match=f"limits in the released file already: {BUCKET}"):
            read_registry(catalog, directory)

    def test_a_hosts_file_among_the_released_entries_is_a_stray_file(self, catalog: Path) -> None:
        shutil.copy(catalog / "hosts.yaml", catalog / "datasets" / "hosts.yaml")
        with pytest.raises(EntryFileError, match="hosts.yaml"):
            read_registry(catalog)

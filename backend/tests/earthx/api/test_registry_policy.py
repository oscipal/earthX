"""The policy `api` and `tiler` build from the registry carries the caps of hosts.yaml, and no spacing (M5-36, G3)."""

from __future__ import annotations

from earthx.api.dependencies import policy_from_registry
from earthx.catalog.datasets import read_registry
from earthx.catalog.registry import DatasetRegistry
from tests.catalog.entries import COP_DEM_GLO_30


def test_each_host_gets_its_cap_from_hosts_yaml() -> None:
    policy = policy_from_registry(read_registry())
    assert policy.connections_for("data.geo.admin.ch") == 6
    assert policy.connections_for("earth-search.aws.element84.com") == 6
    assert policy.connections_for("copernicus-dem-30m.s3.amazonaws.com") == 32


def test_tiles_and_search_keep_no_spacing_even_where_the_source_sets_one() -> None:
    policy = policy_from_registry(read_registry())
    assert policy.interval_for("data.geo.admin.ch") == 0.0
    assert policy.host_intervals == {}


def test_a_registry_without_hosts_yaml_keeps_the_default_cap() -> None:
    policy = policy_from_registry(DatasetRegistry((COP_DEM_GLO_30,)))
    assert policy.connections_for("copernicus-dem-30m.s3.amazonaws.com") == 6

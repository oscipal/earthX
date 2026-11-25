"""Every file a harvest service names is in its container (M5-67 fix 2, 24.11.2026).

Otto's second trial run stopped at ``flags.yaml: cannot be read as UTF-8 text (FileNotFoundError)``: the warning signs
were in the checkout and in no ``COPY`` of ``backend/Dockerfile`` and no mount of the service. The tests of the harvest
ran on the checkout and could not see it. Here the tree of each service is rebuilt from the Dockerfile and the compose
file (``tests/container_tree.py``) and the code is asked what it expects there: every path of ``catalog/`` that a
module the service loads names must exist in the tree. Docker itself is not needed; the real image is built and
started by the job ``compose-topology`` (`.github/` is Otto's).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.container_tree import BACKEND, COMPOSE, REPO, build_container, copy_instructions, harvest_services

SERVICES = sorted(harvest_services())

#: Printed by the process in the tree: the paths under ``catalog/`` that the loaded modules of ``earthx`` name as module
#: constants, and the ``catalog`` the package itself resolves to.
SCAN = """
import importlib, json, pathlib, sys
module = sys.argv[1]
importlib.import_module(module)
from earthx.catalog.datasets import CATALOG_DIR
named = {}
for name, loaded in list(sys.modules.items()):
    if name != "earthx" and not name.startswith("earthx."):
        continue
    for constant, value in vars(loaded).items():
        if isinstance(value, pathlib.Path) and CATALOG_DIR in value.parents:
            named.setdefault(str(value.relative_to(CATALOG_DIR)), []).append(f"{name}.{constant}")
print(json.dumps({"catalog": str(CATALOG_DIR), "named": named}))
"""


def test_the_services_of_the_harvest_are_found() -> None:
    # A rename in docker-compose.yml must not leave the tests below with nothing to check.
    assert {"harvest", "harvest-report", "harvest-grants", "harvest-cycle", "harvest-linkcheck", "harvest-spellings"} <= set(
        SERVICES
    )


@pytest.mark.parametrize("service", SERVICES)
def test_every_catalog_file_a_loaded_module_names_is_in_the_container(service: str, tmp_path: Path) -> None:
    container = build_container(service, tmp_path)
    module = container.entrypoint[2]
    done = container.python(SCAN, module)
    assert done.returncode == 0, done.stderr[-2000:]
    scanned = json.loads(done.stdout.strip().splitlines()[-1])
    # The process resolved its paths in the tree, not in the checkout (`resolve()` follows links).
    assert Path(scanned["catalog"]) == container.catalog
    missing = {path: users for path, users in scanned["named"].items() if not (container.catalog / path).exists()}
    assert not missing, (
        f"{service}: not in the container (add a COPY to backend/Dockerfile, or a mount to the service in "
        f"docker-compose.yml, for each of these): {missing}"
    )


@pytest.mark.parametrize("service", SERVICES)
def test_every_mount_of_a_harvest_service_has_its_source_in_the_checkout(service: str, tmp_path: Path) -> None:
    # `build_container` raises for a mount without a source: Docker would make a folder of it and the code would find
    # an empty one where it reads a file.
    container = build_container(service, tmp_path)
    assert container.app.is_dir()


def test_the_rules_of_the_harvest_are_mounts_of_the_checkout_and_not_copies_of_the_image() -> None:
    # Otto, 24.11.2026: what the run reads from the checkout comes by a mount. The image keeps carrying what the
    # platform needs; a rule that only a harvest service reads is no part of it.
    copied = {source for source, _ in copy_instructions((BACKEND / "Dockerfile").read_text(encoding="utf-8"))}
    services = harvest_services()
    mounted = {
        "harvest-report": "flags.yaml",
        "harvest-cycle": "approval_rules.yaml",
        "harvest-linkcheck": "linkcheck.yaml",
    }
    for service, name in mounted.items():
        assert f"catalog/{name}" not in copied
        volumes = [text.split(":") for text in services[service]["volumes"]]
        assert [f"./backend/catalog/{name}", f"/app/catalog/{name}", "ro"] in volumes, service
    assert (REPO / "backend" / "catalog" / "flags.yaml").is_file() and COMPOSE.is_file()


def test_a_missing_rule_file_names_the_file_and_not_a_text_encoding(tmp_path: Path) -> None:
    from earthx.catalog.entry_files import EntryFileError, read_yaml

    with pytest.raises(EntryFileError, match=r"flags.yaml: file not found"):
        read_yaml(tmp_path / "flags.yaml")

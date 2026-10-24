"""An applied migration is never edited: its checksum is pinned here (DOC-01, #183).

`apply_migrations` records a checksum per migration and refuses a file whose bytes no
longer match. A sweep over the repository that touches one comment line in an applied
`.sql` file therefore breaks `catalog-load` on every existing database, while a fresh
test database never notices. This test fails in CI instead.

New migrations are allowed; changing or deleting a pinned one is not. A new migration
is added to `PINNED` in the commit that creates it.
"""

from __future__ import annotations

import pytest

from earthx.catalog.schema import Migration, discover_migrations

PINNED = {
    "002_search_cache": "0f99adb09d65e015c87eeb1b7758f6c1804c73c52893d18b0b5bdfaa80d6c5e2",
    "003_stats_cache": "d893cd6f459681dad40aa77f43c8c39729782c0eaa6dbab79c64b8b2d363c864",
    "004_materialize_runs": "7ad38eaa6d920000539253bf95432b871e5864ac91994a3b1ce1625c39569e74",
    "005_geocode": "751f0c12be68f0e0442adb00332f433aafc46c1d0905b4fbaae93c609fd70f69",
    "006_jobs": "5671fc738a43d512745bd50518abf5993af00a25f62177e8fa9eedf1ca466b3b",
    "007_run_attachments": "c1b501cc67f184e8e4d007f24a65e4631f9d35787d630367dd21ce62becbced7",
    "008_run_disk": "d44b8ed453cde42fe18d32cb47be9018997194ad3dc59d0c442ababf3812e2fa",
    "009_job_acquired_on": "8a0f8fc86cd599c9a357ef9ad1eaad52b038a0aee7986ce0766aee9c920f1eea",
    "010_job_scene_aoi": "2d20a597e668c476b084a1b3e671332f26b4aa106e249a98f5d1568d74f3d3d0",
    "011_job_aoi_provenance": "598b0259b8840a3062dac3bc3d914edf2855ba5de251ac5afef1c46f495e126c",
    "012_permalink": "37e16cea89f782b4760d1fec9de154f912aa067b9c1498faec29de848e7588c0",
}


def _current() -> dict[str, str]:
    return {f"{m.version}_{m.name}": m.checksum for m in discover_migrations()}


def _changed(current: dict[str, str]) -> list[str]:
    return sorted(name for name, checksum in PINNED.items() if current.get(name) != checksum)


def test_no_applied_migration_was_changed_or_removed() -> None:
    changed = _changed(_current())
    assert not changed, (
        f"Applied migrations changed or missing: {changed}. catalog-load would refuse "
        "every existing database. Restore the file and write a new migration instead."
    )


def test_a_new_migration_is_allowed_next_to_the_pinned_ones() -> None:
    assert _changed({**_current(), "999_new": "0" * 64}) == []


@pytest.mark.parametrize("name", sorted(PINNED))
def test_an_edited_comment_line_is_caught(name: str) -> None:
    version, _, rest = name.partition("_")
    original = next(m for m in discover_migrations() if m.version == version)
    edited = Migration(version=version, name=rest, sql=original.sql.replace("--", "-- x", 1))
    assert _changed({**_current(), name: edited.checksum}) == [name]


def test_a_removed_migration_is_caught() -> None:
    current = _current()
    del current["006_jobs"]
    assert _changed(current) == ["006_jobs"]


def test_crlf_checkout_is_not_a_change() -> None:
    original = next(m for m in discover_migrations() if m.version == "002")
    crlf = Migration(version="002", name="search_cache", sql=original.sql.replace("\n", "\r\n"))
    assert crlf.checksum == PINNED["002_search_cache"]

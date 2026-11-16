"""Synthetic listed entries for the tests of M5-40: invented ids, titles and hosts under ``example.org``.

``listed_entry`` builds one through the dataclass (so every check of ``ListedEntry.__post_init__`` runs), ``write_entry``
puts it into a directory as the YAML file ``catalog-load`` would read, and ``sha_of`` gives the hash of that file.
Nothing here is a real dataset.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from earthx.catalog.entry_files import to_plain
from earthx.catalog.listed import DataKind, DeliveryKind, ListedAccess, ListedEntry, file_sha256
from earthx.catalog.registry import (
    AccountKind,
    LegalStatus,
    LicenseInfo,
    LicenseTier,
    Maturity,
    Provider,
    ProviderRole,
    SpatialExtent,
    TemporalExtent,
)

APPROVED_ON = date(2026, 11, 10)
PUBLISHER = "Example Geodata Office"


def utc(year: int, month: int = 1, day: int = 1) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


def listed_entry(dataset_id: str = "example-atlas", **changes: Any) -> ListedEntry:
    """A valid hand entry; ``changes`` replace fields (``replace`` runs the checks of the entry again)."""
    entry = ListedEntry(
        dataset_id=dataset_id,
        title="Example atlas",
        description="Synthetic listed entry, used only by the tests.",
        keywords=("synthetic", "atlas"),
        providers=(Provider("Example Geodata Office", (ProviderRole.PRODUCER,), "https://example.org"),),
        publisher=PUBLISHER,
        doi=None,
        citation=None,
        data_kind=DataKind.RASTER,
        category="water",
        spatial_extent=SpatialExtent(bbox=(11.2, 48.2, 11.6, 48.4)),
        coverage_states=None,
        temporal_extent=TemporalExtent(start=utc(2000), end=utc(2020, 12, 31)),
        license=LicenseInfo(
            spdx_id="CC-BY-4.0",
            name="Creative Commons Attribution 4.0",
            url="https://example.org/license",
            commercial_use=True,
            distribution=True,
            derivatives=True,
            share_alike=False,
            attribution_required=True,
            tier=LicenseTier.CATALOG,
            attribution_modified=None,
            attribution_unmodified=None,
            terms=None,
        ),
        legal_status=LegalStatus.CLEARED,
        access=ListedAccess(account=AccountKind.NONE, account_provider=None, delivery=DeliveryKind.DOWNLOAD),
        source_url=f"https://data.example.org/{dataset_id}",
        maturity=Maturity.STABLE,
        approved_on=APPROVED_ON,
    )
    return replace(entry, **changes) if changes else entry


def plain_entry(entry: ListedEntry | None = None) -> dict[str, Any]:
    """The plain data of an entry: what its YAML file holds."""
    return to_plain(entry or listed_entry())


def write_entry(directory: Path, entry: ListedEntry | None = None, name: str | None = None) -> Path:
    entry = entry or listed_entry()
    return write_plain(directory, plain_entry(entry), name or f"{entry.dataset_id}.yaml")


def write_plain(directory: Path, data: object, name: str) -> Path:
    path = directory / name
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def with_hash(entry: ListedEntry, directory: Path) -> tuple[ListedEntry, str]:
    """``entry`` with the SHA-256 of its file in ``directory``, as ``load_listed`` gives it to the writer."""
    return entry, file_sha256(write_entry(directory, entry))

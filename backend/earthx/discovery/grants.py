"""The grants of a source, built from the publishers of its harvested finds (M5-20 plan §13f).

Otto, 20.11.2026: the licences K1 to K5 for every publisher of every source, built from the data; he keeps no lists of
publishers. The rule stays per publisher (adr/0033 §6.2, L2; L3 was rejected): this command reads the publishers of a
source's finds from ``earthx_record_state`` and writes ``grants/<source>.yaml`` with every licence of
``backend/catalog/licenses/grant-to-all.yaml``. What it wrote is a file in Git like every grant, which Otto commits and
merges.

A publisher already in the file keeps its line when it is no longer in the database, and its day when its licences
stay the same, so a second run changes only what is new. A find without a publisher, or with blanks at the edges of
it, cannot be granted (``Grant``); the command counts those finds.

    python -m earthx.discovery.grants govdata opendata-swiss fsdi-stac [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import psycopg

from earthx.catalog.entry_files import EntryFileError, _validate, read_yaml
from earthx.catalog.licences import LICENSES_DIR, Grant, load_licences
from earthx.catalog.registry import ENTRY_FILE_CONFIG, ConfigError
from earthx.catalog.sources import read_sources
from earthx.logging import configure_logging

__all__ = [
    "GRANT_TO_ALL_FILE",
    "GrantToAll",
    "PublisherCount",
    "build_grants",
    "dump_grants",
    "publishers_of",
    "read_grant_to_all",
    "read_grants",
]

GRANT_TO_ALL_FILE = LICENSES_DIR / "grant-to-all.yaml"
_HEADER = (
    "# Written by `discovery grants` from the publishers of the harvested finds (M5-20 plan §13f): every licence of\n"
    "# ../grant-to-all.yaml for each publisher. Commit and merge it like every grant; a later run keeps these lines.\n"
)


@dataclass(frozen=True, slots=True)
class GrantToAll:
    """The licences granted to every publisher of a source, and the day Otto decided it."""

    licenses: tuple[str, ...]
    approved_on: date


GrantToAll.__pydantic_config__ = ENTRY_FILE_CONFIG  # type: ignore[attr-defined]


@dataclass(frozen=True, slots=True)
class PublisherCount:
    """The publishers of a source's finds, and how many finds have none that a grant can name."""

    publishers: tuple[str, ...]
    without: int


def read_grant_to_all(known_refs: Collection[str], path: Path = GRANT_TO_ALL_FILE) -> GrantToAll:
    """``grant-to-all.yaml``, checked: each licence once and in ``terms.yaml``, the day not in the future."""
    name = path.name
    data = read_yaml(path)
    grant: GrantToAll = _validate(GrantToAll, data, name)
    if not grant.licenses or len(set(grant.licenses)) != len(grant.licenses):
        raise EntryFileError(f"{name}: licenses names at least one licence, each once")
    if unknown := sorted(set(grant.licenses) - set(known_refs)):
        raise EntryFileError(f"{name}: licenses not in terms.yaml: {', '.join(unknown)}")
    if grant.approved_on > date.today():
        raise EntryFileError(f"{name}: approved_on lies in the future")
    return grant


def read_grants(path: Path) -> tuple[Grant, ...]:
    """The lines of a grants file as they stand; none where it does not exist yet."""
    data = read_yaml(path) if path.exists() else None
    if data is None:
        return ()
    if not isinstance(data, list):
        raise EntryFileError(f"{path.name}: the grants of a source are a list")
    return tuple(_validate(Grant, item, f"{path.name}[{index}]") for index, item in enumerate(data))


def publishers_of(conn: psycopg.Connection, source_id: str) -> PublisherCount:
    """The publishers of the extracted finds of ``source_id``, each as the report reads it from the find."""
    rows = conn.execute(
        "SELECT extracted->>'publisher', count(*) FROM public.earthx_record_state"
        " WHERE source_id = %s AND state = 'extracted' GROUP BY 1",
        (source_id,),
    ).fetchall()
    names, without = [], 0
    for publisher, count in rows:
        if publisher and publisher.strip() and publisher == publisher.strip():
            names.append(publisher)
        else:
            without += count
    return PublisherCount(tuple(sorted(names)), without)


def build_grants(
    publishers: Iterable[str], to_all: GrantToAll, existing: Iterable[Grant], today: date
) -> tuple[Grant, ...]:
    """A line for every publisher with the licences of ``to_all``; lines of ``existing`` stay where nothing changed."""
    before: Mapping[str, Grant] = {grant.publisher: grant for grant in existing}
    licences = to_all.licenses
    lines = dict(before)
    for publisher in publishers:
        old = before.get(publisher)
        if old is None or set(old.licenses) != set(licences):
            lines[publisher] = Grant(publisher=publisher, licenses=licences, approved_on=today)
    return tuple(lines[name] for name in sorted(lines))


def dump_grants(grants: Iterable[Grant]) -> str:
    """The file text: one line of YAML per field, each text quoted as JSON (a subset of YAML), no anchors."""
    parts = [_HEADER]
    for grant in grants:
        parts.append(f"- publisher: {json.dumps(grant.publisher, ensure_ascii=False)}\n")
        parts.append(f"  licenses: [{', '.join(grant.licenses)}]\n")
        parts.append(f"  approved_on: {grant.approved_on.isoformat()}\n")
    return "".join(parts) if len(parts) > 1 else _HEADER + "[]\n"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Grant the licences of grant-to-all.yaml to every publisher (M5-20).")
    parser.add_argument("source_ids", nargs="+", metavar="source_id")
    parser.add_argument("--out", type=Path, default=LICENSES_DIR / "grants", help="where the grants files go")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    configure_logging()
    try:
        sources = read_sources()
        catalogue = load_licences(sources)
        to_all = read_grant_to_all(catalogue.terms)
        if unknown := [source_id for source_id in args.source_ids if source_id not in sources]:
            raise ConfigError(f"no source {', '.join(unknown)} in backend/catalog/sources/")
        existing = {source_id: read_grants(args.out / f"{source_id}.yaml") for source_id in args.source_ids}
    except (ConfigError, EntryFileError) as error:
        print(f"grants failed: {error}", file=sys.stderr)
        return 1
    today = date.today()
    try:
        with psycopg.connect(autocommit=True) as conn:
            for source_id in args.source_ids:
                found = publishers_of(conn, source_id)
                lines = build_grants(found.publishers, to_all, existing[source_id], today)
                (args.out / f"{source_id}.yaml").write_text(dump_grants(lines), encoding="utf-8")
                new = sum(1 for line in lines if line.approved_on == today and line not in existing[source_id])
                print(
                    f"{source_id}: {len(found.publishers)} Herausgeber in der Datenbank, {len(lines)} Zeilen"
                    f" ({new} neu oder geändert), je {len(to_all.licenses)} Lizenzen;"
                    f" Funde ohne Herausgeber: {found.without}"
                )
    except psycopg.Error as error:
        print(f"grants failed: database error {type(error).__name__} ({error.sqlstate or 'no state'})", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"grants failed: the grants file cannot be written ({type(error).__name__})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

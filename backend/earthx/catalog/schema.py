"""Applying this package's own migrations.

pgstac brings its own schema and its own tool (``pypgstac migrate``); this runner is
only for what EarthX adds next to it. It is deliberately small: numbered ``.sql``
files in ``migrations/``, applied in order, each recorded in ``earthx_migrations``.

The bookkeeping table belongs to the runner and is created by it, not shipped as the
first migration: otherwise every migrations directory would have to carry a copy of
it. ``migrations/`` is empty in M1-04 — the first real migration is the application
cache of E4, in M1-06 (see the README there).

Two properties it has to have, because a migration that half-runs is worse than one
that does not run at all:

* A file and its bookkeeping row are written in **one** transaction.
* A file that was edited after it was applied is an error, not a silent no-op — the
  recorded checksum would no longer match what is on disk.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

# 001_name.sql — the number orders them, the name says what it does.
_FILENAME = re.compile(r"^(?P<version>\d{3})_(?P<name>[a-z0-9_]+)\.sql$")


_BOOKKEEPING_TABLE = """
CREATE TABLE IF NOT EXISTS earthx_migrations (
    version     text        PRIMARY KEY,
    checksum    text        NOT NULL,
    applied_at  timestamptz NOT NULL DEFAULT now()
)
"""


class MigrationError(RuntimeError):
    """A migration cannot be applied, or what was applied no longer matches the file."""


@dataclass(frozen=True, slots=True)
class Migration:
    version: str
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql.encode("utf-8")).hexdigest()


def discover_migrations(directory: Path = MIGRATIONS_DIR) -> tuple[Migration, ...]:
    """Every ``.sql`` file in order. A file that does not fit the pattern is an error.

    Not skipped: a migration nobody notices is the failure mode this guards against.
    """
    migrations: list[Migration] = []
    for path in sorted(directory.glob("*.sql")):
        match = _FILENAME.match(path.name)
        if match is None:
            raise MigrationError(f"{path.name} is not named <nnn>_<name>.sql")
        migrations.append(
            Migration(version=match["version"], name=match["name"], sql=path.read_text(encoding="utf-8"))
        )
    versions = [migration.version for migration in migrations]
    if len(set(versions)) != len(versions):
        raise MigrationError(f"duplicate migration version in {directory}")
    return tuple(migrations)


def applied_migrations(conn: psycopg.Connection) -> dict[str, str]:
    """Version to checksum, empty while the bookkeeping table does not exist yet."""
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('earthx_migrations')")
        row = cur.fetchone()
        if row is None or row[0] is None:
            return {}
        cur.execute("SELECT version, checksum FROM earthx_migrations")
        return {version: checksum for version, checksum in cur.fetchall()}


def ensure_bookkeeping(conn: psycopg.Connection) -> None:
    """Create ``earthx_migrations`` if it is not there. Safe to call every time."""
    conn.execute(_BOOKKEEPING_TABLE)


def apply_migrations(conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR) -> tuple[str, ...]:
    """Apply what is not applied yet. Returns the versions applied by this call.

    Idempotent: a second call over an unchanged directory applies nothing.
    """
    migrations = discover_migrations(directory)
    ensure_bookkeeping(conn)
    applied = applied_migrations(conn)

    for migration in migrations:
        recorded = applied.get(migration.version)
        if recorded is not None and recorded != migration.checksum:
            raise MigrationError(
                f"migration {migration.version}_{migration.name} was changed after it was applied "
                f"(recorded {recorded[:12]}, file {migration.checksum[:12]}). "
                "Write a new migration instead of editing an applied one."
            )

    pending = [migration for migration in migrations if migration.version not in applied]
    for migration in pending:
        with conn.transaction():
            conn.execute(migration.sql)
            conn.execute(
                "INSERT INTO earthx_migrations (version, checksum) VALUES (%s, %s)",
                (migration.version, migration.checksum),
            )
    return tuple(migration.version for migration in pending)

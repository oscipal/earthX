"""T-C fixtures: a real Postgres, in the cloud session and in CI (adr/0002 §2).

Two decisions here are deliberate and worth keeping:

* **No skipping.** A T-C test that skips itself when the database is missing would be
  green in both places it is supposed to run and would never be noticed. adr/0002 §6
  says every test runs in at least two places or is marked ``local_only``; a test that
  quietly runs nowhere is the third case, which is an error. Missing connection
  details fail with a message that says what to set.
* **No mocking.** The point of T-C is that pgstac really answers (CLAUDE.md: nothing
  is mocked, nothing replaced).

Every test runs in a transaction that is rolled back afterwards, so tests do not see
each other's collections and the developer's database is left as it was found.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from dotenv import load_dotenv

# Written by scripts/setup-cloud-session.sh. Reading it here is what lets a session
# run the same bare `pytest` that CI runs (adr/0002 §6); CI sets the variables on the
# job instead, and real environment variables win over the file either way.
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env.test"

# libpq reads these itself; PGHOST is the one that decides whether anything was set up
# at all. scripts/setup-cloud-session.sh writes them, CI sets them on the job.
_REQUIRED_ENV = ("PGHOST", "PGUSER", "PGDATABASE")

_MISSING_DB = """\
No Postgres for the T-C tests. They run in the cloud session and in CI
(docs/adr/0002-testaufteilung.md §2) and are not skipped, because a test that skips
itself in both places is a test that never runs.

Missing: {missing}

In a cloud session: scripts/setup-cloud-session.sh sets these up and writes .env.test,
which these tests read.
Locally: point PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE at a Postgres with PostGIS
and run `pypgstac migrate` against it.
"""


@pytest.fixture(scope="session", autouse=True)
def _postgres_env() -> None:
    if _ENV_FILE.exists():
        load_dotenv(_ENV_FILE, override=False)


@pytest.fixture(scope="session")
def postgres_dsn(_postgres_env: None) -> str:
    missing = [name for name in _REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        pytest.fail(_MISSING_DB.format(missing=", ".join(missing)), pytrace=False)
    return ""  # libpq takes the rest from the environment


@pytest.fixture
def conn(postgres_dsn: str) -> Iterator[psycopg.Connection]:
    """A connection whose work is rolled back when the test ends."""
    try:
        connection = psycopg.connect(postgres_dsn, autocommit=False)
    except psycopg.OperationalError as error:
        pytest.fail(
            f"Postgres is configured but not reachable: {error}\n"
            "In a cloud session: `service postgresql start`, or re-run "
            "scripts/setup-cloud-session.sh.",
            pytrace=False,
        )
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()

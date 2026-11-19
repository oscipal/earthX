"""The approval files of the runs and what they publish (adr/0033 §8.3, §8.4; M5-20 plan §12).

``discovery report`` writes ``backend/catalog/approvals/<day>-<source>.yaml`` with ``decision: pending`` for the stack
of one source; Otto checks the sample, sets ``decision: approved`` (or ``rejected``) and merges. ``catalog-load`` reads
every file of the image and calls :func:`publish`: a stack becomes visible only where its file is approved and its
fingerprint is that of the stack in Postgres. A changed entry since the stack was formed stays in review; a file with
``revoked_on`` hides again what it published. Idempotent: a second run writes nothing.

Nothing here reads the content of an entry or logs one; the file names no person (``ENTSCHEIDUNGEN`` §4).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import psycopg

from earthx.catalog.datasets import CATALOG_DIR
from earthx.catalog.entry_files import EntryFileError, _validate, read_yaml
from earthx.catalog.registry import ENTRY_FILE_CONFIG

__all__ = ["APPROVALS_DIR", "Approval", "Published", "SampleCheck", "load_approvals", "publish"]

APPROVALS_DIR = CATALOG_DIR / "approvals"
_README = "README.md"
_NAME = re.compile(r"\d{4}-\d{2}-\d{2}-[a-z][a-z0-9-]{1,62}(?:-\d+)?\.yaml")
_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class SampleCheck:
    """One entry of the sample and Otto's tick: ``ok`` ``None`` until he checked it."""

    dataset_id: str
    why: str
    title: str
    source_url: str
    license_rule: str | None
    ok: bool | None


@dataclass(frozen=True, slots=True)
class Approval:
    source_id: str
    batch_id: int
    fingerprint: str
    created_on: date
    entries: int
    decision: str
    decided_on: date | None
    excluded_rules: tuple[str, ...]
    revoked_on: date | None
    sample: tuple[SampleCheck, ...]


for _part in (SampleCheck, Approval):
    _part.__pydantic_config__ = ENTRY_FILE_CONFIG  # type: ignore[attr-defined]
del _part


def _check(approval: Approval, name: str) -> None:
    if not _SHA256.fullmatch(approval.fingerprint):
        raise EntryFileError(f"{name}: fingerprint is a SHA-256 in lower-case hex")
    if approval.decision not in ("pending", "approved", "rejected"):
        raise EntryFileError(f"{name}: decision is pending, approved or rejected")
    if (approval.decision == "pending") != (approval.decided_on is None):
        raise EntryFileError(f"{name}: decided_on is the day of an approved or rejected decision, null while pending")
    if approval.decision == "approved" and any(check.ok is None for check in approval.sample):
        # Prinzip 12: never without the sample checked.
        raise EntryFileError(f"{name}: an approved file has every entry of its sample checked (ok true or false)")
    if approval.revoked_on is not None and approval.decision != "approved":
        raise EntryFileError(f"{name}: only an approved file can be revoked")
    today = date.today()
    for day in (approval.decided_on, approval.revoked_on):
        if day is not None and day > today:
            raise EntryFileError(f"{name}: a day lies in the future")


def load_approvals(directory: Path = APPROVALS_DIR) -> tuple[tuple[Approval, str, str], ...]:
    """Every approval file of ``directory`` as (approval, ``approvals/<name>``, SHA-256 of the file), checked."""
    if not directory.is_dir():
        return ()
    found = []
    for path in sorted(directory.iterdir()):
        if path.name == _README or path.suffix == ".md":
            continue
        name = f"approvals/{path.name}"
        if not path.is_file() or not _NAME.fullmatch(path.name):
            raise EntryFileError(f"{name}: only <day>-<source_id>.yaml files, their reports and a README belong here")
        data = read_yaml(path)
        if not isinstance(data, dict):
            raise EntryFileError(f"{name}: an approval is a mapping of its fields")
        approval: Approval = _validate(Approval, data, name)
        _check(approval, name)
        found.append((approval, name, hashlib.sha256(path.read_bytes()).hexdigest()))
    return tuple(found)


@dataclass(frozen=True, slots=True)
class Published:
    """What one call of :func:`publish` did, by approval file."""

    published: dict[str, int]
    revoked: dict[str, int]
    #: Approved files whose stack is no longer the open one of its source (a later report took it over).
    stale: tuple[str, ...]


def publish(conn: psycopg.Connection, approvals: Sequence[tuple[Approval, str, str]]) -> Published:
    """Publish the stacks of the approved files and hide again what revoked ones published (adr/0033 §8.3)."""
    published: dict[str, int] = {}
    revoked: dict[str, int] = {}
    stale: list[str] = []
    with conn.cursor() as cur:
        for approval, name, file_sha256 in approvals:
            if approval.decision != "approved":
                continue
            cur.execute(
                "SELECT state FROM public.earthx_listing_batch WHERE batch_id = %s AND source_id = %s"
                " AND fingerprint = %s",
                (approval.batch_id, approval.source_id, approval.fingerprint),
            )
            row = cur.fetchone()
            if row is None:
                # Another database, or a stack this one never formed: nothing to publish here.
                continue
            state = row[0]
            if approval.revoked_on is not None:
                if state == "published":
                    cur.execute(
                        "UPDATE public.earthx_listed_entry SET state = 'in_review', approval_file = NULL,"
                        " approval_sha256 = NULL, approved_on = NULL, published_at = NULL"
                        " WHERE approval_file = %s AND state = 'published'",
                        (name,),
                    )
                    revoked[name] = cur.rowcount
                    cur.execute(
                        "UPDATE public.earthx_listing_batch SET state = 'revoked' WHERE batch_id = %s",
                        (approval.batch_id,),
                    )
                continue
            if state == "expired":
                stale.append(name)
            if state != "open":
                continue
            cur.execute(
                """
                UPDATE public.earthx_listed_entry e SET state = 'published', approval_file = %(name)s,
                    approval_sha256 = %(sha)s, approved_on = %(day)s, published_at = now(),
                    content = jsonb_set(e.content, '{earthx:listing,approved_on}', to_jsonb(%(day)s::text))
                FROM public.earthx_listing_batch_entry b
                WHERE b.batch_id = %(batch)s AND e.dataset_id = b.dataset_id AND e.state = 'in_review'
                  AND e.content_sha256 = b.content_sha256 AND NOT (b.license_rule = ANY(%(excluded)s))
                """,
                {
                    "name": name,
                    "sha": file_sha256,
                    "day": approval.decided_on,
                    "batch": approval.batch_id,
                    "excluded": list(approval.excluded_rules),
                },
            )
            published[name] = cur.rowcount
            cur.execute(
                "UPDATE public.earthx_listing_batch SET state = 'published', approval_file = %s, approval_sha256 = %s,"
                " published_at = now() WHERE batch_id = %s",
                (name, file_sha256, approval.batch_id),
            )
    return Published(published, revoked, tuple(stale))

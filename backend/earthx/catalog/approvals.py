"""The approval files of the runs and what they publish (adr/0033 §8.3, §8.4; M5-20 plan §12).

``discovery report`` writes ``backend/catalog/approvals/<day>-<source>.yaml`` with ``decision: pending`` for the stack
of one source; Otto checks the sample, sets ``decision: approved`` (or ``rejected``) and merges. ``catalog-load`` reads
every file of the image and calls :func:`publish`: a stack becomes visible only where its file is approved and its
fingerprint is that of the stack in Postgres, and of its entries only those whose own link passed the automatic check
(M5-67, ``link_checks``). A changed entry since the stack was formed stays in review, as does one without a pass; a
file with ``revoked_on`` hides again what it published, also what a failed link hid since. Idempotent: a second run
writes nothing.

Nothing here reads the content of an entry or logs one; the file names no person (``ENTSCHEIDUNGEN`` §4).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import psycopg

from earthx.catalog.datasets import CATALOG_DIR
from earthx.catalog.entry_files import EntryFileError, _validate, read_yaml
from earthx.catalog.link_checks import PASSED
from earthx.catalog.registry import ENTRY_FILE_CONFIG

__all__ = ["APPROVALS_DIR", "DECIDERS", "Approval", "LinkNote", "Published", "SampleCheck", "load_approvals", "publish"]

APPROVALS_DIR = CATALOG_DIR / "approvals"
_README = "README.md"
_NAME = re.compile(r"\d{4}-\d{2}-\d{2}-[a-z][a-z0-9-]{1,62}(?:-\d+)?\.yaml")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_DATASET_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}")
_REASON = re.compile(r"[a-z0-9_]{2,40}")
#: Who decided a run (M5-67, adr/0033 §8.5): a role, never a name.
DECIDERS = ("rules", "otto")


@dataclass(frozen=True, slots=True)
class LinkNote:
    """The automatic check of an entry's link (M5-67 plan §4): an outcome and a code, never page text."""

    outcome: str
    reason: str
    status: int | None = None
    final_host: str | None = None
    licence_seen: bool | None = None


@dataclass(frozen=True, slots=True)
class SampleCheck:
    """One entry of the sample and its tick: ``ok`` ``None`` until Otto or the rules checked it."""

    dataset_id: str
    why: str
    title: str
    source_url: str
    license_rule: str | None
    ok: bool | None
    check: LinkNote | None = None


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
    #: ``rules`` or ``otto``; absent in files decided by hand before M5-67.
    decided_by: str | None = None
    #: Entries of the stack that stay out for a warning sign (M5-67 plan §5); they stay in review.
    excluded_entries: tuple[str, ...] = ()


for _part in (LinkNote, SampleCheck, Approval):
    _part.__pydantic_config__ = ENTRY_FILE_CONFIG  # type: ignore[attr-defined]
del _part


def _check(approval: Approval, name: str) -> None:
    if not _SHA256.fullmatch(approval.fingerprint):
        raise EntryFileError(f"{name}: fingerprint is a SHA-256 in lower-case hex")
    if approval.decision not in ("pending", "approved", "rejected"):
        raise EntryFileError(f"{name}: decision is pending, approved or rejected")
    if (approval.decision == "pending") != (approval.decided_on is None):
        raise EntryFileError(f"{name}: decided_on is the day of an approved or rejected decision, null while pending")
    if approval.decision == "approved" and (not approval.sample or any(c.ok is None for c in approval.sample)):
        # Prinzip 12: never without the sample checked.
        raise EntryFileError(f"{name}: an approved file has every entry of its sample checked (ok true or false)")
    if approval.revoked_on is not None and approval.decision != "approved":
        raise EntryFileError(f"{name}: only an approved file can be revoked")
    if approval.decided_by is not None:
        if approval.decided_by not in DECIDERS:
            raise EntryFileError(f"{name}: decided_by is rules or otto")
        if approval.decision == "pending":
            raise EntryFileError(f"{name}: decided_by names who decided; a pending file has none")
    if approval.decided_by == "rules" and any(c.check is None for c in approval.sample):
        # Prinzip 12: the rules tick the sample only with the automatic check of each of its entries.
        raise EntryFileError(f"{name}: a file decided by the rules has the link check of every entry of its sample")
    for item in approval.sample:
        note = item.check
        if note is not None and (
            note.outcome not in ("passed", "failed", "unchecked")
            or not _REASON.fullmatch(note.reason)
            or (note.outcome == "passed") != (note.reason == "ok")
        ):
            raise EntryFileError(
                f"{name}: the link check of {item.dataset_id} is passed with reason ok, else failed or unchecked"
                " with a reason code"
            )
    ids = approval.excluded_entries
    if len(set(ids)) != len(ids) or not all(_DATASET_ID.fullmatch(i) for i in ids):
        raise EntryFileError(f"{name}: excluded_entries lists dataset ids, each once")
    # One day of slack: the container counts days in UTC, Otto in his own zone.
    latest = date.today() + timedelta(days=1)
    for day in (approval.decided_on, approval.revoked_on):
        if day is not None and day > latest:
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


#: The entries an approved file publishes: those of its stack still unchanged, not excluded by a rule or by id, and
#: with a pass of their own current link (M5-67).
_PUBLISH = (
    """
    UPDATE public.earthx_listed_entry e SET state = 'published', approval_file = %(name)s,
        approval_sha256 = %(sha)s, approved_on = %(day)s, published_at = now(),
        content = jsonb_set(e.content, '{earthx:listing,approved_on}', to_jsonb(%(day)s::text))
    FROM public.earthx_listing_batch_entry b
    WHERE b.batch_id = %(batch)s AND e.dataset_id = b.dataset_id AND e.state = 'in_review'
      AND e.content_sha256 = b.content_sha256 AND NOT (b.license_rule = ANY(%(excluded)s))
      AND NOT (e.dataset_id = ANY(%(excluded_entries)s))
      AND EXISTS (SELECT 1 FROM public.earthx_link_check c WHERE c.dataset_id = e.dataset_id AND """
    + PASSED
    + ")"
)


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
                        " WHERE approval_file = %s AND state IN ('published', 'link_hidden')",
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
                _PUBLISH,
                {
                    "name": name,
                    "sha": file_sha256,
                    "day": approval.decided_on,
                    "batch": approval.batch_id,
                    "excluded": list(approval.excluded_rules),
                    "excluded_entries": list(approval.excluded_entries),
                },
            )
            published[name] = cur.rowcount
            cur.execute(
                "UPDATE public.earthx_listing_batch SET state = 'published', approval_file = %s, approval_sha256 = %s,"
                " published_at = now() WHERE batch_id = %s",
                (name, file_sha256, approval.batch_id),
            )
    return Published(published, revoked, tuple(stale))

"""The results of the automatic link check of harvested listed entries and what they hide or bring back (M5-67;
docs/plans/m5/m5-67-harvest-automatisch.md §4a, §4c; adr/0033 §8.5; migration ``037``).

An entry is visible only while its own current link has passed (``approvals.publish`` asks this table). A published
entry without that pass (its link failed, could not be checked, or was never checked with this address) becomes
``link_hidden``, hidden and never deleted; a later pass with the same link brings it back (Otto, 24.11.2026, also for
unchecked links). Where a host or a pattern failed or did not answer for a large share in one run, its results are
``guarded``: they hide nothing and publish nothing, since the check is then more likely wrong than the data.

Nothing here fetches; ``discovery.linkcheck`` does, through ``gateway``. Hand entries (source ``listed``) are not
checked. No page text is stored, only codes.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

import psycopg

from earthx.catalog.listed import HAND_SOURCE

__all__ = [
    "LINK",
    "Applied",
    "DueLink",
    "GroupCount",
    "LinkResult",
    "apply_results",
    "due_links",
    "guard_results",
    "record_results",
]

#: The link "Source" of a listed entry, as the report writes it into the content.
LINK = "e.content -> 'earthx:listing' ->> 'source_url'"
#: A check that counts: passed with the entry's current link and not guarded.
PASSED = f"c.outcome = 'passed' AND NOT c.guarded AND c.url = {LINK}"
#: What keeps a published entry visible: a pass of its current link, or a guarded result of it (plan §4c).
_KEEPS = f"c.url = {LINK} AND (c.outcome = 'passed' OR c.guarded)"
#: Reasons of ``unchecked`` that pass (no answer, too many requests, a server error): they count for the guard like a
#: failure, so that a host that is down hides nothing (plan A18). ``robots``, an unconfirmed form of a catalogue page
#: or a page too large do not pass and do not count.
TRANSIENT = "(reason IN ('unreachable', 'host_resting', 'gateway', 'api_shape') OR reason ~ '^http_(429|5[0-9][0-9])$')"


@dataclass(frozen=True, slots=True)
class DueLink:
    """A link to check, with what the page has to show: the title and the identifiers of the dataset."""

    dataset_id: str
    source_id: str
    state: str
    url: str
    title: str
    identifiers: tuple[str, ...]
    #: 0 new or presented again, 1 published and never checked with this link, 2 last check unchecked, 3 rotation.
    priority: int


@dataclass(frozen=True, slots=True)
class LinkResult:
    dataset_id: str
    url: str
    host: str
    pattern: str
    outcome: str
    reason: str
    status: int | None
    final_host: str | None


def _identifiers(source_key: str, keys: Sequence[str] | None) -> tuple[str, ...]:
    """The key at the source, the DCAT identifier, the DOI and the id of a collection; the check ignores short ones."""
    found = [source_key]
    for key in keys or ():
        kind, _, value = key.partition(":")
        if kind in ("id", "doi"):
            found.append(value)
        elif kind == "coll":
            found.append(value.rsplit("/", 1)[-1])
    return tuple(dict.fromkeys(v for v in found if v))


def due_links(
    conn: psycopg.Connection, *, recheck_days: int, now: datetime | None = None, only: Sequence[str] | None = None
) -> list[DueLink]:
    """Every harvested link that is due, most urgent first (plan §4a): new and presented-again entries without a pass
    of their current link; published or hidden ones never checked with their current link; those whose last check
    was ``unchecked``; and every check older than ``recheck_days``, the oldest first."""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT * FROM (
                SELECT e.dataset_id, e.source_id, e.state, {LINK} AS url, e.content ->> 'title' AS title,
                       e.source_key, e.dedupe_keys,
                       CASE WHEN e.state = 'in_review' THEN 0
                            WHEN c.dataset_id IS NULL OR c.url IS DISTINCT FROM {LINK} THEN 1
                            WHEN c.outcome = 'unchecked' THEN 2
                            ELSE 3 END AS priority,
                       c.checked_at
                FROM public.earthx_listed_entry e
                LEFT JOIN public.earthx_link_check c ON c.dataset_id = e.dataset_id
                WHERE e.source_id <> %(hand)s AND e.state IN ('in_review', 'published', 'link_hidden')
                  AND (%(only)s::text[] IS NULL OR e.source_id = ANY(%(only)s))
                  AND {LINK} IS NOT NULL
                  AND (c.dataset_id IS NULL OR c.url IS DISTINCT FROM {LINK} OR c.outcome = 'unchecked'
                       OR c.checked_at < coalesce(%(now)s, now()) - make_interval(days => %(days)s)
                       OR (e.state = 'in_review' AND NOT ({PASSED})))
            ) due
            ORDER BY priority, checked_at NULLS FIRST, dataset_id
            """,
            {"hand": HAND_SOURCE, "now": now, "days": recheck_days, "only": None if only is None else list(only)},
        )
        rows = cur.fetchall()
    return [
        DueLink(
            dataset_id=row[0],
            source_id=row[1],
            state=row[2],
            url=row[3],
            title=row[4] or "",
            identifiers=_identifiers(row[5], row[6]),
            priority=row[7],
        )
        for row in rows
    ]


def record_results(conn: psycopg.Connection, results: Iterable[LinkResult], checked_at: datetime) -> int:
    """Keep the latest result per entry; a new result is never guarded until :func:`guard_results` says so."""
    rows = [
        (r.dataset_id, r.url, r.host, r.pattern, r.outcome, r.reason, r.status, r.final_host, checked_at)
        for r in results
    ]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO public.earthx_link_check AS c
                (dataset_id, url, host, pattern, outcome, reason, status, final_host, guarded, checked_at)
            SELECT %s, %s, %s, %s, %s, %s, %s, %s, false, %s
            WHERE EXISTS (SELECT 1 FROM public.earthx_listed_entry e WHERE e.dataset_id = %s)
            ON CONFLICT (dataset_id) DO UPDATE SET url = EXCLUDED.url, host = EXCLUDED.host,
                pattern = EXCLUDED.pattern, outcome = EXCLUDED.outcome, reason = EXCLUDED.reason,
                status = EXCLUDED.status, final_host = EXCLUDED.final_host, guarded = false,
                checked_at = EXCLUDED.checked_at
            """,
            [(*row, row[0]) for row in rows],
        )
    return len(rows)


@dataclass(frozen=True, slots=True)
class GroupCount:
    """The results of one run for one host or one pattern (``kind`` ``host`` or ``pattern``): ``transient`` are the
    ``unchecked`` that may pass next time, ``unchecked`` the others (``robots``, an unconfirmed form)."""

    kind: str
    key: str
    passed: int
    failed: int
    unchecked: int
    guarded: bool
    transient: int = 0

    @property
    def checked(self) -> int:
        """Links asked: passed, failed, or without an answer that may come next time."""
        return self.passed + self.failed + self.transient


def guard_results(
    conn: psycopg.Connection, since: datetime, *, min_checked: int, failed_share: float
) -> list[GroupCount]:
    """Count the results checked since ``since`` per host and per pattern, and guard every result of a group where at
    least ``min_checked`` links were asked (passed, failed or without an answer) and at least ``failed_share`` of them
    failed or got no answer (plan §4c, A18). Returns every group, the guarded ones first, then by size."""
    groups: list[GroupCount] = []
    with conn.cursor() as cur:
        for kind in ("host", "pattern"):
            cur.execute(
                f"""
                SELECT {kind}, count(*) FILTER (WHERE outcome = 'passed'), count(*) FILTER (WHERE outcome = 'failed'),
                       count(*) FILTER (WHERE outcome = 'unchecked' AND NOT {TRANSIENT}),
                       count(*) FILTER (WHERE outcome = 'unchecked' AND {TRANSIENT})
                FROM public.earthx_link_check WHERE checked_at >= %s GROUP BY {kind}
                """,
                (since,),
            )
            for key, passed, failed, unchecked, transient in cur.fetchall():
                asked = passed + failed + transient
                guarded = asked >= min_checked and failed + transient >= failed_share * asked
                groups.append(GroupCount(kind, key, passed, failed, unchecked, guarded, transient))
        hosts = [g.key for g in groups if g.guarded and g.kind == "host"]
        patterns = [g.key for g in groups if g.guarded and g.kind == "pattern"]
        if hosts or patterns:
            cur.execute(
                "UPDATE public.earthx_link_check SET guarded = true WHERE checked_at >= %s"
                " AND (host = ANY(%s) OR pattern = ANY(%s))",
                (since, hosts, patterns),
            )
    groups.sort(key=lambda g: (not g.guarded, -(g.checked + g.unchecked), g.kind, g.key))
    return groups


@dataclass(frozen=True, slots=True)
class Applied:
    """Published entries hidden for a link without a pass, hidden ones brought back, and new ones that could now be
    published by an approved file (in review with a pass)."""

    hidden: int
    restored: int
    publishable: int


_HIDE = f"""
    WHERE e.state = 'published' AND e.source_id <> %(hand)s AND (%(only)s::text[] IS NULL OR e.source_id = ANY(%(only)s))
      AND NOT EXISTS (SELECT 1 FROM public.earthx_link_check c WHERE c.dataset_id = e.dataset_id AND {_KEEPS})
"""
_RESTORE = f"""
    FROM public.earthx_link_check c
    WHERE c.dataset_id = e.dataset_id AND e.state = 'link_hidden' AND e.source_id <> %(hand)s
      AND (%(only)s::text[] IS NULL OR e.source_id = ANY(%(only)s)) AND {PASSED}
"""


def apply_results(conn: psycopg.Connection, *, dry_run: bool, only: Sequence[str] | None = None) -> Applied:
    """Hide published entries without a pass of their current link (``link_hidden``): failed, unchecked or never
    checked, but not guarded; bring back hidden ones whose current link passed again. With ``dry_run`` only count
    (the trial run, plan §18a). ``only`` keeps it to these sources; every source where it is ``None``."""
    params = {"hand": HAND_SOURCE, "only": None if only is None else list(only)}
    with conn.cursor() as cur:
        if dry_run:
            cur.execute(f"SELECT count(*) FROM public.earthx_listed_entry e {_HIDE}", params)
            hidden = cur.fetchone()[0]
            cur.execute(f"SELECT count(*) FROM public.earthx_listed_entry e WHERE EXISTS (SELECT 1 {_RESTORE})", params)
            restored = cur.fetchone()[0]
        else:
            cur.execute(f"UPDATE public.earthx_listed_entry e SET state = 'link_hidden' {_HIDE}", params)
            hidden = cur.rowcount
            cur.execute(f"UPDATE public.earthx_listed_entry e SET state = 'published' {_RESTORE}", params)
            restored = cur.rowcount
        cur.execute(
            "SELECT count(*) FROM public.earthx_listed_entry e JOIN public.earthx_link_check c"
            f" ON c.dataset_id = e.dataset_id WHERE e.state = 'in_review' AND {PASSED}"
        )
        publishable = cur.fetchone()[0]
    return Applied(hidden, restored, publishable)

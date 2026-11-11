"""Overview pyramids in the object store: where they live and how long (M5-30b part 8b, adr/0032 §5.2, §5.3, §8.4).

Objects live at ``overviews/{dataset_id}/{version}/{z}/{x}/{y}.tif``. ``version`` is the name of a source version
(`earthx_overview_version` in the database); a new version is a new path and the old one is never read again.

**How long.** Every object carries ``checked-at``, the time its content was last confirmed at the source, and goes
30 days after it (:data:`OVERVIEW_TTL`); a confirmed version is extended, an unconfirmed one runs out. The bucket rule is
the net under that and has 31 days (:data:`OVERVIEW_RULE_DAYS`): an extension rewrites the object, so the rule counts
from the extension. A dataset whose id starts with ``proto-`` (adr/0024) lives 7 days and is never extended
(:data:`PROTOTYPE_TTL`).
"""

from __future__ import annotations

from datetime import timedelta

from earthx.objectstore.results import Store, is_expiry_rule

__all__ = [
    "OVERVIEW_PREFIX",
    "OVERVIEW_RULE_DAYS",
    "OVERVIEW_TTL",
    "PROTOTYPE_PREFIX",
    "PROTOTYPE_TTL",
    "overviews_lifecycle_ok",
    "term_of",
]

OVERVIEW_PREFIX = "overviews/"
#: From the last confirmation of a version at the source (adr/0032 §5.2, F3).
OVERVIEW_TTL = timedelta(days=30)
#: The bucket rule, one day over the term so that it only catches what the cleanup did not.
OVERVIEW_RULE_DAYS = 31
#: A prototype source (adr/0024): 7 days like a result, and no extension (adr/0032 §8.4).
PROTOTYPE_PREFIX = "proto-"
PROTOTYPE_TTL = timedelta(days=7)


def term_of(dataset_id: str) -> timedelta:
    """How long a pyramid of this dataset lives from its ``checked-at``."""
    return PROTOTYPE_TTL if dataset_id.startswith(PROTOTYPE_PREFIX) else OVERVIEW_TTL


def overviews_lifecycle_ok(store: Store) -> bool:
    """Whether the bucket carries the rule for ``overviews/``, read only; recognised by content like the one for results."""
    return any(
        is_expiry_rule(rule, prefix=OVERVIEW_PREFIX, days=OVERVIEW_RULE_DAYS) for rule in store.s3.lifecycle_rules()
    )

"""The link "Source" of a harvested find: as directly as possible to the data (Otto, 17.11.2026; M5-19 plan §6, F1 = 1).

First a viewer or download page at the provider, where the data can be loaded; else the page of the dataset at the
provider; else its page in the catalogue. Never a single file, never a service (a capabilities answer is no page for
people), never only the start page of the provider. A link from a foreign catalogue is not trusted (Prinzip 15): only
``https``, no user part, a host name, no control characters, at most 2 048 characters; an ``http`` link is skipped,
not rewritten. Pure: the extractors gather the candidates, this module ranks and checks them.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from enum import IntEnum

from earthx.gateway import UrlRejected, normalize_host

__all__ = ["MAX_LINK_CHARS", "LinkRank", "checked_link", "choose_link"]

MAX_LINK_CHARS = 2048
_URL = re.compile(
    r"https://(?P<host>[^/?#:@\[\]\s]+)(?::(?P<port>[0-9]{1,5}))?"
    r"(?P<path>/[^?#\s]*)?(?P<query>\?[^#\s]*)?(?P<fragment>#\S*)?"
)
_CONTROL = re.compile(r"[\x00-\x20\x7f-\x9f]")
# A language prefix alone is still the start page: /de, /fr/, /en-gb/.
_START_PATH = re.compile(r"/?|/[a-z]{2}(?:[-_][a-z]{2})?/?", re.IGNORECASE)


class LinkRank(IntEnum):
    """Lower wins (plan §6)."""

    VIEWER_OR_DOWNLOAD_PAGE = 1
    DATASET_PAGE = 2
    CATALOGUE_PAGE = 3


def checked_link(url: object) -> str | None:
    """``url`` if it may be the link "Source", else ``None``."""
    if not isinstance(url, str) or len(url) > MAX_LINK_CHARS or _CONTROL.search(url):
        return None
    match = _URL.fullmatch(url)
    if match is None or match["port"] not in (None, "443"):
        return None
    try:
        normalize_host(match["host"])
    except UrlRejected:
        return None
    if _START_PATH.fullmatch(match["path"] or "") and not match["query"] and len(match["fragment"] or "") <= 2:
        return None
    return url


def choose_link(candidates: Iterable[tuple[LinkRank, object]]) -> tuple[str, LinkRank] | None:
    """The first valid candidate of the best rank, in the order given within a rank; ``None`` if there is none."""
    best: tuple[str, LinkRank] | None = None
    for rank, url in candidates:
        link = checked_link(url)
        if link is not None and (best is None or rank < best[1]):
            best = (link, rank)
    return best

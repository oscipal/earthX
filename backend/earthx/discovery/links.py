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

__all__ = ["MAX_LINK_CHARS", "LinkRank", "checked_link", "choose_link", "link_problem"]

MAX_LINK_CHARS = 2048
_URL = re.compile(
    r"https://(?P<host>[^/?#:@\[\]\s]+)(?::(?P<port>[0-9]{1,5}))?"
    r"(?P<path>/[^?#\s]*)?(?P<query>\?[^#\s]*)?(?P<fragment>#\S*)?"
)
_CONTROL = re.compile(r"[\x00-\x20\x7f-\x9f]")
# Still the start page: a language prefix, an index file, a query that only picks the language (/de, /fr/index.html,
# ?lang=de).
_LANGUAGE = re.compile(r"[a-z]{2}(?:[-_][a-z]{2})?", re.IGNORECASE)
_INDEX = re.compile(r"(?:index|default|home)\.(?:html?|php|aspx?|jsp)", re.IGNORECASE)
_LANGUAGE_KEYS = frozenset({"lang", "language", "locale", "l", "hl"})


class LinkRank(IntEnum):
    """Lower wins (plan §6)."""

    VIEWER_OR_DOWNLOAD_PAGE = 1
    DATASET_PAGE = 2
    CATALOGUE_PAGE = 3


def link_problem(url: object) -> str | None:
    """Why ``url`` may not be the link "Source", as a code (``empty``, ``http``, ``scheme``, ``long``, ``control``,
    ``port``, ``host``, ``start_page``, ``invalid``); ``None`` where it may."""
    if not isinstance(url, str) or not url.strip():
        return "empty"
    if len(url) > MAX_LINK_CHARS:
        return "long"
    if _CONTROL.search(url):
        return "control"
    if url[:7].lower() == "http://":
        return "http"
    if url[:8].lower() != "https://":
        return "scheme"
    match = _URL.fullmatch(url)
    if match is None:
        return "invalid"
    if match["port"] not in (None, "443"):
        return "port"
    try:
        normalize_host(match["host"])
    except UrlRejected:
        return "host"
    try:
        url.encode("utf-8")
    except UnicodeEncodeError:
        return "invalid"
    if _is_start_page(match["path"] or "", match["query"] or "", match["fragment"] or ""):
        return "start_page"
    return None


def checked_link(url: object) -> str | None:
    """``url`` if it may be the link "Source", else ``None``."""
    return url if isinstance(url, str) and link_problem(url) is None else None


def _is_start_page(path: str, query: str, fragment: str) -> bool:
    segments = [segment for segment in path.split("/") if segment]
    if segments and _LANGUAGE.fullmatch(segments[0]):
        segments = segments[1:]
    if segments and _INDEX.fullmatch(segments[-1]):
        segments = segments[:-1]
    keys = {pair.split("=", 1)[0].lower() for pair in query.lstrip("?").split("&") if pair}
    return not segments and keys <= _LANGUAGE_KEYS and len(fragment) <= 2


def choose_link(candidates: Iterable[tuple[LinkRank, object]]) -> tuple[str, LinkRank] | None:
    """The first valid candidate of the best rank, in the order given within a rank; ``None`` if there is none."""
    best: tuple[str, LinkRank] | None = None
    for rank, url in candidates:
        link = checked_link(url)
        if link is not None and (best is None or rank < best[1]):
            best = (link, rank)
    return best

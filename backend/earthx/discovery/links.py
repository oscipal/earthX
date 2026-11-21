"""The link "Source" of a harvested find: as directly as possible to the data (Otto, 17.11.2026; M5-19 plan §6, F1 = 1).

First a viewer or download page at the provider, where the data can be loaded; else the page of the dataset at the
provider; else its page in the catalogue. Never a single file, never a service (a capabilities answer is no page for
people), never only the start page of the provider. A link from a foreign catalogue is not trusted (Prinzip 15): only
``https``, no user part, a host name, no control characters, at most 2 048 characters; an ``http`` link is skipped,
not rewritten.

Never a collective page either (Otto, 21.11.2026): the page of an office or a project that many finds name, not the
dataset. An address is one if (a) it would be chosen as the link by more than one find of the same source, or (b) it
consists of the host and at most one part of the path. Query and fragment belong to the address and make it specific.
A collective page is skipped and the next rank counts, the page of the dataset in the catalogue last (it is never
skipped: it names the dataset). (b) is judged here from the address alone, (a) from every find of the source by
:class:`LinkIndex`. Pure: the extractors gather the candidates, this module ranks and checks them.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Collection, Iterable
from enum import IntEnum

from earthx.gateway import UrlRejected, normalize_host

__all__ = [
    "MAX_LINK_CHARS",
    "LinkIndex",
    "LinkRank",
    "address_key",
    "checked_link",
    "choose_link",
    "first_link",
    "is_collection_page",
    "link_problem",
]

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
#: A leading part of the path that names the language is no part of the page for the rule on collective pages (Otto,
#: 21.11.2026: /de/agi is a collective page like /agi): the languages of Switzerland and English.
_PATH_LANGUAGES = frozenset({"de", "fr", "it", "en", "rm"})


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


def _is_specific(query: str, fragment: str) -> bool:
    """Whether a query or a fragment tells the page from its siblings: a query that does more than pick the language, a
    fragment that is more than ``#`` or ``#/``."""
    keys = {pair.split("=", 1)[0].lower() for pair in query.lstrip("?").split("&") if pair}
    return not keys <= _LANGUAGE_KEYS or len(fragment) > 2


def is_collection_page(url: object) -> bool:
    """(b) The host and at most one part of the path, not counting a leading language (``/de/agi`` is one), without a
    query or fragment that makes it specific: the start page of an office or the page of a department, not of a
    dataset. A text that is no address is none."""
    match = _URL.fullmatch(url) if isinstance(url, str) else None
    if match is None:
        return False
    parts = [part for part in (match["path"] or "").split("/") if part]
    if parts and parts[0].lower() in _PATH_LANGUAGES:
        parts = parts[1:]
    return len(parts) <= 1 and not _is_specific(match["query"] or "", match["fragment"] or "")


def address_key(url: str) -> str:
    """The address as two finds would have to agree on it to name the same page: scheme and host in lower case, no
    ``:443``, no closing ``/`` of the path; query and fragment as they are."""
    match = _URL.fullmatch(url)
    if match is None:
        return url
    path = (match["path"] or "").rstrip("/")
    return f"https://{match['host'].lower()}{path}{match['query'] or ''}{match['fragment'] or ''}"


def _choose(
    candidates: Iterable[tuple[LinkRank, object]], skipped: Callable[[LinkRank, str], bool]
) -> tuple[str, LinkRank] | None:
    best: tuple[str, LinkRank] | None = None
    for rank, url in candidates:
        link = checked_link(url)
        if link is not None and (best is None or rank < best[1]) and not skipped(rank, link):
            best = (link, rank)
    return best


def first_link(candidates: Iterable[tuple[LinkRank, object]]) -> tuple[str, LinkRank] | None:
    """The first valid candidate of the best rank, in the order given within a rank, collective pages included; ``None``
    if there is none. What the link would be without the rule on collective pages."""
    return _choose(candidates, lambda rank, link: False)


def choose_link(
    candidates: Iterable[tuple[LinkRank, object]], shared: frozenset[str] = frozenset()
) -> tuple[str, LinkRank] | None:
    """The first valid candidate of the best rank that is no collective page, in the order given within a rank; ``None``
    if there is none. ``shared`` are the addresses (:func:`address_key`) that more than one find of the source would
    choose (a, :meth:`LinkIndex.shared`); the page in the catalogue is never skipped."""
    return _choose(
        candidates,
        lambda rank, link: rank is not LinkRank.CATALOGUE_PAGE
        and (is_collection_page(link) or address_key(link) in shared),
    )


class LinkIndex:
    """The links every find of one source could be (rank 1 and 2, valid, no page by (b)), for the rule (a): an address
    that more than one find would choose is a collective page.

    Which find chooses an address depends on which addresses are skipped, so :meth:`shared` settles it step by step: the
    addresses chosen more than once are skipped, the finds that chose them choose again, until no further address is
    chosen more than once. Once an address is shared it stays so. Memory: the addresses of the finds of one source.
    """

    def __init__(self) -> None:
        self._links: dict[str, tuple[tuple[LinkRank, str], ...]] = {}

    def __contains__(self, key: object) -> bool:
        return key in self._links

    def __len__(self) -> int:
        return len(self._links)

    def set(self, key: str, candidates: Iterable[tuple[LinkRank, object]]) -> None:
        """What the find ``key`` could link to; no candidate at all forgets it."""
        links = tuple(
            (rank, link)
            for rank, url in candidates
            if rank is not LinkRank.CATALOGUE_PAGE
            and (link := checked_link(url)) is not None
            and not is_collection_page(link)
        )
        if links:
            self._links[key] = links
        else:
            self._links.pop(key, None)

    def discard(self, key: str) -> None:
        self._links.pop(key, None)

    def retain(self, keys: Collection[str]) -> None:
        """Forget every find but ``keys`` (the finds that are gone)."""
        for key in self._links.keys() - set(keys):
            del self._links[key]

    def shared(self) -> frozenset[str]:
        """The collective pages by (a), as :func:`address_key`."""
        shared: set[str] = set()
        while True:
            chosen = Counter(
                address_key(link)
                for links in self._links.values()
                if (link := _first_not_in(links, shared)) is not None
            )
            more = {address for address, count in chosen.items() if count > 1} - shared
            if not more:
                return frozenset(shared)
            shared |= more

    def link_of(self, key: str, shared: frozenset[str]) -> str | None:
        """The address a find chooses at rank 1 or 2 given the collective pages; ``None`` where only the catalogue is
        left."""
        links = self._links.get(key)
        return None if links is None else _first_not_in(links, shared)


def _first_not_in(links: tuple[tuple[LinkRank, str], ...], shared: set[str] | frozenset[str]) -> str | None:
    best: tuple[str, LinkRank] | None = None
    for rank, link in links:
        if (best is None or rank < best[1]) and address_key(link) not in shared:
            best = (link, rank)
    return None if best is None else best[0]

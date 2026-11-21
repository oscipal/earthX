"""Fetch and extract for a STAC API (M5-19 plan §4.2, §5): the collections of ``/collections``, one find per collection.

The listing is paged by ``rel=next``; the gateway's allowlist keeps every page on the source's host, and an address
asked twice in one run ends it (a loop). A listing that fit on one page is asked with its stored validators the next
time: a ``304`` means the whole listing is unchanged (Earth Search, adr/0025 §3). A longer listing has no such shortcut
and is decided by the hash of each collection (FSDI).
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from earthx.catalog.categories import Evidence, category_of
from earthx.catalog.harvest_store import ListValidators
from earthx.catalog.listed import listed_keywords
from earthx.catalog.sources import SourceConfig, StacFilter
from earthx.discovery.extract import (
    Distribution,
    Extracted,
    Invalid,
    ShapeError,
    bbox_of,
    data_kind_of,
    text_of,
)
from earthx.discovery.links import LinkRank, checked_link, choose_link, first_link, link_candidates
from earthx.gateway import GatewayResponse

__all__ = [
    "PAGE_LIMIT",
    "Fetch",
    "StacListing",
    "collection_key",
    "extract_collection",
    "stac_pages",
]

PAGE_LIMIT = 100
MAX_DISTRIBUTIONS = 50
_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}")
# Only these name the publisher (plan §5.1): a processor or a provider without a role may be a person.
_PROVIDER_ROLES = ("licensor", "producer")

Fetch = Callable[..., Awaitable[GatewayResponse]]


@dataclass(slots=True)
class StacListing:
    """How the listing ended: unchanged as a whole, or complete with the validators to keep for the next run."""

    not_modified: bool = False
    complete: bool = False
    validators: ListValidators | None = None


#: Values of STAC `license` that point at the link `rel=license` instead of naming a licence.
_SEE_LINK = frozenset({"proprietary", "other", "various"})


def collection_key(collection: object) -> str | None:
    """The id of a collection if it can be a key at the source."""
    if not isinstance(collection, dict):
        return None
    key = collection.get("id")
    return key if isinstance(key, str) and _KEY.fullmatch(key) else None


def _next(body: Mapping[str, Any]) -> str | None:
    links = body.get("links")
    for link in links if isinstance(links, list) else ():
        if isinstance(link, dict) and link.get("rel") == "next":
            if link.get("method", "GET") != "GET" or not isinstance(link.get("href"), str):
                raise ShapeError("a next link that is no GET with an address")
            return link["href"]
    return None


async def stac_pages(
    fetch: Fetch, source: SourceConfig, known: ListValidators | None, listing: StacListing
) -> AsyncIterator[list[tuple[str | None, Any]]]:
    """The collections of each page as ``(key, collection)``; a key ``None`` marks one that cannot be a find."""
    assert isinstance(source.filter, StacFilter)
    prefixes = source.filter.collection_prefixes
    url: str | None = f"{source.endpoint}/collections?limit={PAGE_LIMIT}"
    headers: dict[str, str] = {}
    if known is not None and known.etag:
        headers["if-none-match"] = known.etag
    elif known is not None and known.last_modified:
        headers["if-modified-since"] = known.last_modified
    asked: set[str] = set()
    first = True
    while url is not None:
        if url in asked:
            raise ShapeError("the listing points back to a page it gave already")
        asked.add(url)
        response = await fetch(url, headers=headers if first else None)
        if response.status_code == 304 and first and headers:
            listing.not_modified = True
            return
        if response.status_code != 200:
            raise ShapeError(f"the listing answered {response.status_code}")
        try:
            body = response.json()
        except ValueError:
            raise ShapeError("a page of the listing is no JSON") from None
        if not isinstance(body, dict) or not isinstance(body.get("collections"), list):
            raise ShapeError("a page of the listing has no list of collections")
        next_url = _next(body)
        if first:
            single = next_url is None
            listing.validators = ListValidators(
                response.headers.get("etag") if single else None,
                response.headers.get("last-modified") if single else None,
            )
        yield [
            (key, collection)
            for collection in body["collections"]
            if (key := collection_key(collection)) is None or not prefixes or key.startswith(prefixes)
        ]
        url, first = next_url, False
    listing.complete = True


def _publisher(providers: object) -> str | None:
    named = (
        [p for p in providers if isinstance(p, dict) and text_of(p.get("name"))] if isinstance(providers, list) else []
    )
    for role in _PROVIDER_ROLES:
        for provider in named:
            roles = provider.get("roles")
            if isinstance(roles, list) and role in roles:
                return text_of(provider["name"])
    return None


def _links(collection: Mapping[str, Any]) -> list[dict[str, Any]]:
    links = collection.get("links")
    return [link for link in links if isinstance(link, dict)] if isinstance(links, list) else []


def _html(link: Mapping[str, Any]) -> bool:
    return str(link.get("type") or "").split(";")[0].strip().lower() == "text/html"


def _data_media_types(collection: Mapping[str, Any]) -> list[str | None]:
    assets = []
    for field in ("item_assets", "assets"):
        value = collection.get(field)
        if isinstance(value, dict):
            assets += [asset for asset in value.values() if isinstance(asset, dict)]
    return [
        asset.get("type") if isinstance(asset.get("type"), str) else None
        for asset in assets
        if "data" in (asset.get("roles") if isinstance(asset.get("roles"), list) else ("data",))
    ]


def _requester_pays(collection: Mapping[str, Any]) -> bool:
    """Whether the storage extension says the reader pays (Earth Search's Landsat, adr/0027)."""
    holders: list[Any] = [collection]
    for field in ("item_assets", "storage:schemes"):
        value = collection.get(field)
        if isinstance(value, dict):
            holders += list(value.values())
    summaries = collection.get("summaries")
    summary = summaries.get("storage:requester_pays") if isinstance(summaries, dict) else None
    return any(isinstance(h, dict) and h.get("storage:requester_pays") is True for h in holders) or (
        isinstance(summary, list) and True in summary
    )


def _temporal(collection: Mapping[str, Any]) -> tuple[str | None, str | None] | None:
    try:
        interval = collection["extent"]["temporal"]["interval"][0]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(interval, list) or len(interval) != 2:
        return None
    start, end = (text if (text := text_of(value)) is not None and len(text) <= 40 else None for value in interval)
    return None if start is None and end is None else (start, end)


def _bbox(collection: Mapping[str, Any]) -> tuple[float, float, float, float] | None:
    try:
        return bbox_of(collection["extent"]["spatial"]["bbox"][0])
    except (KeyError, IndexError, TypeError):
        return None


def _distributions(collection: Mapping[str, Any]) -> tuple[Distribution, ...]:
    assets = collection.get("assets")
    found = []
    for asset in assets.values() if isinstance(assets, dict) else ():
        if isinstance(asset, dict) and (href := checked_link(asset.get("href"))) is not None:
            roles = asset.get("roles")
            found.append(
                Distribution(
                    href=href,
                    format=None,
                    media_type=text_of(asset.get("type")),
                    title=text_of(asset.get("title")),
                    roles=tuple(r for r in roles if isinstance(r, str)) if isinstance(roles, list) else (),
                )
            )
    return tuple(found[:MAX_DISTRIBUTIONS])


def _link_candidates(key: str, links: list[Mapping[str, Any]], source: SourceConfig) -> list[tuple[LinkRank, object]]:
    catalog_page = source.catalog_page.replace("{id}", key) if source.catalog_page else None
    return [
        *(
            (LinkRank.VIEWER_OR_DOWNLOAD_PAGE, link.get("href"))
            for link in links
            if link.get("rel") in ("via", "alternate") and _html(link)
        ),
        *((LinkRank.DATASET_PAGE, link.get("href")) for link in links if link.get("rel") == "about" and _html(link)),
        (LinkRank.CATALOGUE_PAGE, catalog_page),
    ]


def extract_collection(
    key: str, collection: Mapping[str, Any], source: SourceConfig, shared: frozenset[str] = frozenset()
) -> Extracted:
    """The intermediate form of one collection, or :class:`Invalid` with its reason. ``shared`` are the collective pages
    of the source (:meth:`~earthx.discovery.links.LinkIndex.shared`), which the link "Source" never is."""
    title = text_of(collection.get("title"))
    if title is None:
        raise Invalid("no_title")
    keywords = collection.get("keywords")
    raw_keywords = [text for k in keywords if (text := text_of(k))] if isinstance(keywords, list) else []
    category = category_of(Evidence(keywords=tuple(raw_keywords)))
    links = _links(collection)
    candidates = _link_candidates(key, links, source)
    chosen = choose_link(candidates, shared)
    if chosen is None:
        raise Invalid("no_link", link_candidates(candidates))
    plain = first_link(candidates)
    skipped = plain if plain is not None and plain[1] < chosen[1] else None
    landing = choose_link((c for c in candidates if c[0] is not LinkRank.VIEWER_OR_DOWNLOAD_PAGE), shared)
    licence_links = [link.get("href") for link in links if link.get("rel") == "license"]
    licence = collection.get("license")
    # "proprietary" (and "other", "various") only say "see the link rel=license": the link is the statement, and
    # without one the word alone states no licence (Otto, 20.11.2026).
    if isinstance(licence, str) and licence.strip().lower() in _SEE_LINK:
        licence = None
    statements = [licence, *licence_links]
    bbox = _bbox(collection)
    return Extracted(
        source_key=key,
        title=title,
        description=text_of(collection.get("description")) or "",
        publisher=_publisher(collection.get("providers")),
        doi=text_of(collection.get("sci:doi")),
        # Wording, never a link: an href of `rel=license` is kept as text for the rule of M5-20, unchecked.
        licence_statements=tuple(dict.fromkeys(text for s in statements if (text := text_of(s)))),
        bbox=bbox,
        geometry=None,
        spatial_text=None,
        extent_known=bbox is not None,
        temporal=_temporal(collection),
        data_kind=data_kind_of(_data_media_types(collection), default="raster"),
        delivery="download",
        account="requester_pays" if _requester_pays(collection) else "none",
        category=category,
        keywords=listed_keywords(raw_keywords, category),
        # A collection is known by its id at its host (M5-20 plan §8); STAC names no themes.
        themes=(),
        identifier=None,
        source_url=chosen[0],
        source_rank=int(chosen[1]),
        landing_url=None if landing is None else landing[0],
        skipped_url=None if skipped is None else skipped[0],
        skipped_rank=None if skipped is None else int(skipped[1]),
        link_candidates=link_candidates(candidates),
        distributions=_distributions(collection),
    )

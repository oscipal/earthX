"""Fetch and extract for CKAN (M5-19 plan §4.2, §5): the packages of ``package_search``, one find per package.

The listing is read in pages of :data:`PAGE_ROWS` packages sorted by id, with ``start`` as the offset; each page starts
with the last package of the one before. CKAN answers without ``ETag`` (adr/0025 §3), so nothing is asked
conditionally: the hash of each package decides. An incremental run asks only for packages whose
``metadata_modified`` lies after the start of the last done run less an hour, as ckanext-harvest does (adr/0025
§3a); a full one asks for all. Packages that come or go while the listing is read shift the offsets, and one can be
skipped: a page that does not hold the last package of the one before, or a count that changes, marks the listing as
moved (A8). Only a full listing that held still and named at least one package can mark finds ``gone`` (A3).

Which field names the publisher is a setting of the source (``publisher_field``, adr/0025 §5.2). Texts given per
language (opendata.swiss [S]) are read in the order of :func:`~earthx.discovery.extract.localized` (plan A7).
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from earthx.catalog.categories import EU_DATA_THEMES, Evidence, category_of
from earthx.catalog.listed import listed_keywords
from earthx.catalog.sources import CkanFilter, SourceConfig
from earthx.discovery.extract import (
    FILE_KINDS,
    LANGUAGES,
    Distribution,
    Extracted,
    Invalid,
    ShapeError,
    geometry_of,
    kind_of,
    localized,
    resource_kind,
    text_of,
)
from earthx.discovery.links import LinkRank, checked_link, choose_link
from earthx.discovery.stac import Fetch

__all__ = ["INCREMENTAL_OVERLAP", "PAGE_ROWS", "CkanListing", "ckan_pages", "extract_package", "package_key"]

PAGE_ROWS = 100
MAX_DISTRIBUTIONS = 50
MAX_SPATIAL_TEXT_CHARS = 500
#: The overlap of an incremental run with the last one (ckanext-harvest, adr/0025 §3a).
INCREMENTAL_OVERLAP = timedelta(hours=1)
_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}")
# The name of a package as CKAN allows it; it fills the catalogue page.
_NAME = re.compile(r"[a-z0-9_-]{2,100}")
_DOI = re.compile(r"(?:https://(?:dx\.)?doi\.org/|doi:)?(10\.[0-9]{4,9}/\S{1,200})", re.IGNORECASE)
_INSPIRE_THEME = re.compile(r"https?://inspire\.ec\.europa\.eu/theme/([a-z]{2})/?")
# Resources that describe the data instead of showing it are no viewer (plan §6, rank 1).
_DOCUMENTATION = re.compile(
    r"dokumentation|documentation|documentazione|metadaten|metadata|métadonnées|metadati|beschreibung|description"
    r"|descrizione",
    re.IGNORECASE,
)
# A capabilities address is no page for people, whatever format the catalogue gives it (plan §6).
_SERVICE_QUERY = re.compile(r"[?&](?:service=(?:wms|wmts|wfs|wcs)|request=getcapabilities)(?:&|$)", re.IGNORECASE)
_PUBLIC = "PUBLIC"
_NOT_PUBLIC = frozenset({"RESTRICTED", "NON_PUBLIC", "NONPUBLIC", "NON-PUBLIC"})


@dataclass(slots=True)
class CkanListing:
    """How the listing ended. ``complete`` only for a full listing read to its end whose count held still."""

    full: bool
    not_modified: bool = False
    complete: bool = False
    #: CKAN has no validators of its listing (adr/0025 §3).
    validators: None = None
    #: The listing shifted while it was read (count changed, or a page lost its overlap): a package may be skipped.
    moved: bool = False
    #: The listing named no package at all; a full one of them is no evidence that every find is gone.
    empty: bool = False


def package_key(package: object) -> str | None:
    """The id of a package if it can be a key at the source."""
    if not isinstance(package, dict):
        return None
    key = package.get("id")
    return key if isinstance(key, str) and _KEY.fullmatch(key) else None


def _search_params(source: SourceConfig, start: int, since: datetime | None) -> dict[str, str | int]:
    """The query of one page; the gateway assembles it into the address."""
    assert isinstance(source.filter, CkanFilter)
    clauses = [] if source.filter.fq is None else [f"({source.filter.fq})"]
    if since is not None:
        clauses.append(f"metadata_modified:[{since.astimezone(UTC):%Y-%m-%dT%H:%M:%SZ} TO *]")
    params: dict[str, str | int] = {"rows": PAGE_ROWS, "start": start, "sort": "id asc"}
    if clauses:
        params["fq"] = " AND ".join(clauses)
    return params


async def ckan_pages(
    fetch: Fetch, source: SourceConfig, since: datetime | None, listing: CkanListing
) -> AsyncIterator[list[tuple[str | None, Any]]]:
    """The packages of each page as ``(key, package)``; a key ``None`` marks one that cannot be a find. ``since`` is the
    lower bound of ``metadata_modified`` of an incremental listing (aware, asked in UTC), ``None`` for a full one.

    :class:`ShapeError` where the source answers no listing, or a page of several packages names none that is new: it
    does not page (``start`` ignored) and would run until the budget is spent."""
    start, total, last_key, read = 0, None, None, 0
    keys: set[str] = set()
    while True:
        response = await fetch(f"{source.endpoint}/package_search", params=_search_params(source, start, since))
        if response.status_code != 200:
            raise ShapeError(f"the listing answered {response.status_code}")
        try:
            body = response.json()
        except (ValueError, RecursionError):
            raise ShapeError("a page of the listing is no JSON") from None
        result = body.get("result") if isinstance(body, dict) and body.get("success") is True else None
        count = result.get("count") if isinstance(result, dict) else None
        packages = result.get("results") if isinstance(result, dict) else None
        if isinstance(count, bool) or not isinstance(count, int) or count < 0 or not isinstance(packages, list):
            raise ShapeError("a page of the listing has no count and no list of packages")
        if total is None:
            total = count
        elif count != total:
            listing.moved = True
        page = [(package_key(package), package) for package in packages]
        if last_key is not None and (not page or page[0][0] != last_key):
            listing.moved = True
        read += len(page) - (1 if last_key is not None and page and page[0][0] == last_key else 0)
        new = {key for key, _ in page if key is not None} - keys
        if len(page) > 1 and not new:
            raise ShapeError("a page of the listing names no new package")
        keys |= new
        yield page
        end = start + len(page)
        if not page or end >= count:
            break
        # The next page starts with the last package of this one, so that a shift of the listing shows.
        last_key = page[-1][0] if len(page) > 1 else None
        start = end - 1 if last_key is not None else end
    if read != total:
        listing.moved = True
    listing.empty = total == 0
    listing.complete = listing.full and not listing.moved and not listing.empty


def _extras(package: Mapping[str, Any]) -> dict[str, Any]:
    """The extras of a package by key; the first of a key counts."""
    extras = package.get("extras")
    found: dict[str, Any] = {}
    for extra in extras if isinstance(extras, list) else ():
        if isinstance(extra, dict) and isinstance(extra.get("key"), str):
            found.setdefault(extra["key"], extra.get("value"))
    return found


def _field(package: Mapping[str, Any], extras: Mapping[str, Any], name: str) -> Any:
    """A field the source keeps either on the package or among its extras (DCAT-AP profiles differ)."""
    value = package.get(name)
    return value if value not in (None, "", [], {}) else extras.get(name)


def _publisher(package: Mapping[str, Any], extras: Mapping[str, Any], field: str) -> str | None:
    if field == "publisher_name":
        return localized(_field(package, extras, "publisher_name"))
    organization = package.get("organization")
    return localized(organization.get("title")) if isinstance(organization, dict) else None


def _doi(package: Mapping[str, Any], extras: Mapping[str, Any]) -> str | None:
    text = text_of(_field(package, extras, "doi"))
    match = _DOI.fullmatch(text) if text else None
    return match[1] if match else None


def _texts(value: object) -> list[str]:
    """Every text of a value that is a text, a list of texts, or the JSON text of such a list (ckanext-dcat ``theme``)."""
    if isinstance(value, str) and value.lstrip().startswith("["):
        try:
            value = json.loads(value)
        except (ValueError, RecursionError):
            return []
    values = value if isinstance(value, list) else [value]
    return [text for item in values if (text := text_of(item)) is not None]


def _keywords(package: Mapping[str, Any]) -> list[str]:
    """Tags, and keywords per language where the source has them (opendata.swiss [S]), in the order of the source."""
    tags = package.get("tags")
    found = [
        text
        for tag in (tags if isinstance(tags, list) else ())
        if (text := localized(tag.get("display_name") or tag.get("name")) if isinstance(tag, dict) else text_of(tag))
    ]
    keywords = package.get("keywords")
    if isinstance(keywords, dict):
        order = [*LANGUAGES, *sorted(k for k in keywords if isinstance(k, str))]
        language = next((k for k in order if isinstance(keywords.get(k), list) and keywords[k]), None)
        if language is not None:
            found += [text for item in keywords[language] if (text := text_of(item)) is not None]
    return found


def _evidence(package: Mapping[str, Any], extras: Mapping[str, Any], keywords: list[str]) -> Evidence:
    groups = package.get("groups")
    group_terms, eu_themes = [], []
    for group in groups if isinstance(groups, list) else ():
        if not isinstance(group, dict):
            continue
        name = text_of(group.get("name"))
        if name is not None and name.upper() in EU_DATA_THEMES:
            # GovData names its groups after the EU data themes [S].
            eu_themes.append(name.upper())
        group_terms += [t for t in (name, localized(group.get("title")), localized(group.get("display_name"))) if t]
    themes = _texts(_field(package, extras, "theme"))
    return Evidence(
        inspire_themes=tuple(m[1] for value in (*themes, *keywords) if (m := _INSPIRE_THEME.fullmatch(value))),
        eu_data_themes=(*eu_themes, *(t for t in themes if "/data-theme/" in t)),
        groups=tuple(dict.fromkeys(group_terms)),
        keywords=tuple(keywords),
    )


def _spatial(package: Mapping[str, Any], extras: Mapping[str, Any]) -> tuple[Any, Any, str | None]:
    """Box, geometry and place text: a GeoJSON geometry where the source gives one, else its text (a place name)."""
    text = None
    for value in (extras.get("spatial"), package.get("spatial")):
        found = geometry_of(value)
        if found is not None:
            return found[0], found[1], None
        if text is None and isinstance(value, str) and not value.lstrip().startswith(("{", "[")):
            text = localized(value)
    return None, None, None if text is None else text[:MAX_SPATIAL_TEXT_CHARS]


def _temporal(package: Mapping[str, Any], extras: Mapping[str, Any]) -> tuple[str | None, str | None] | None:
    temporals = package.get("temporals")
    if isinstance(temporals, list) and temporals and isinstance(temporals[0], dict):
        pair = (temporals[0].get("start_date"), temporals[0].get("end_date"))
    else:
        pair = (_field(package, extras, "temporal_start"), _field(package, extras, "temporal_end"))
    start, end = (text if (text := text_of(value)) is not None and len(text) <= 40 else None for value in pair)
    return None if start is None and end is None else (start, end)


def _account(package: Mapping[str, Any], extras: Mapping[str, Any], reachable: bool) -> str | None:
    """``none`` for public data (DCAT ``access_rights``) or, without a statement, where a file or service is named;
    restricted or unknown statements stay empty for M5-20 (plan §5.2), never guessed."""
    statement = text_of(_field(package, extras, "access_rights"))
    if statement is None:
        return "none" if reachable else None
    code = statement.rstrip("/").rsplit("/", 1)[-1].upper()
    return "none" if code == _PUBLIC else None


@dataclass(frozen=True, slots=True)
class _Resource:
    kind: str | None
    download: str | None
    access: str | None
    distribution: Distribution | None
    documentation: bool

    @property
    def is_file(self) -> bool:
        """A file to load: by its format, or by a download address where the format says no service or page."""
        return self.kind in FILE_KINDS or (self.download is not None and self.kind not in ("service", "page"))


def _resource(resource: Mapping[str, Any]) -> _Resource:
    format_ = text_of(resource.get("format"))
    media = text_of(resource.get("mimetype")) or text_of(resource.get("media_type"))
    download = text_of(resource.get("download_url"))
    addresses = [a for a in (text_of(resource.get("access_url")), text_of(resource.get("url"))) if a is not None]
    # The first address that may be a link: an `http` access_url must not hide an `https` url.
    access = next((a for a in addresses if checked_link(a) is not None), addresses[0] if addresses else None)
    title = localized(resource.get("name")) or localized(resource.get("title"))
    kind_label = text_of(resource.get("resource_type"))
    href = checked_link(download) or checked_link(access)
    return _Resource(
        kind=resource_kind(format_, media),
        download=download,
        access=access,
        distribution=None
        if href is None
        else Distribution(
            href=href,
            format=format_,
            media_type=media,
            title=title,
            roles=() if kind_label is None else (kind_label,),
        ),
        documentation=(kind_label or "").lower() == "documentation" or bool(title and _DOCUMENTATION.search(title)),
    )


def _viewer_pages(resources: Iterable[_Resource]) -> list[str | None]:
    """Rank 1: a page for people at the provider (accessURL without downloadURL), not its documentation, no service."""
    return [
        r.access
        for r in resources
        if r.kind == "page" and r.download is None and not r.documentation and not _SERVICE_QUERY.search(r.access or "")
    ]


def _page_or_none(url: object) -> object:
    """``url`` unless it is a capabilities address or names a file by its ending (plan §6: never a service or a file)."""
    if not isinstance(url, str) or _SERVICE_QUERY.search(url):
        return None
    name = url.split("#")[0].split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    ending = name.rsplit(".", 1)[-1] if "." in name else ""
    return None if resource_kind(ending, None) in FILE_KINDS | {"service"} else url


def extract_package(key: str, package: Mapping[str, Any], source: SourceConfig) -> Extracted:
    """The intermediate form of one package, or :class:`Invalid` with its reason."""
    assert isinstance(source.filter, CkanFilter)
    title = localized(package.get("title"))
    if title is None:
        raise Invalid("no_title")
    extras = _extras(package)
    raw_resources = package.get("resources")
    resource_documents = [r for r in raw_resources if isinstance(r, dict)] if isinstance(raw_resources, list) else []
    resources = [_resource(r) for r in resource_documents]
    name = package.get("name")
    catalog_page = (
        source.catalog_page.replace("{name}", name)
        if source.catalog_page and isinstance(name, str) and _NAME.fullmatch(name)
        else None
    )
    candidates = [
        *((LinkRank.VIEWER_OR_DOWNLOAD_PAGE, url) for url in _viewer_pages(resources)),
        (LinkRank.DATASET_PAGE, _page_or_none(package.get("url"))),
        (LinkRank.CATALOGUE_PAGE, catalog_page),
    ]
    chosen = choose_link(candidates)
    if chosen is None:
        raise Invalid("no_link")
    landing = choose_link(c for c in candidates if c[0] is not LinkRank.VIEWER_OR_DOWNLOAD_PAGE)
    keywords = _keywords(package)
    category = category_of(_evidence(package, extras, keywords))
    kinds = [r.kind for r in resources]
    if any(r.is_file for r in resources):
        delivery: str | None = "download"
    elif "service" in kinds:
        delivery = "service"
    else:
        delivery = None
    # `rights` of a resource holds the terms of use at opendata.swiss [S].
    statements = [
        package.get("license_id"),
        package.get("license_url"),
        *(value for r in resource_documents for value in (r.get("license"), r.get("rights"))),
    ]
    bbox, geometry, spatial_text = _spatial(package, extras)
    return Extracted(
        source_key=key,
        title=title,
        description=localized(package.get("notes")) or localized(package.get("description")) or "",
        publisher=_publisher(package, extras, source.filter.publisher_field),
        doi=_doi(package, extras),
        licence_statements=tuple(dict.fromkeys(text for s in statements if (text := localized(s)))),
        bbox=bbox,
        geometry=geometry,
        spatial_text=spatial_text,
        extent_known=bbox is not None or spatial_text is not None,
        temporal=_temporal(package, extras),
        data_kind=kind_of(kinds, default="other"),
        delivery=delivery,
        account=_account(package, extras, delivery is not None),
        category=category,
        keywords=listed_keywords(keywords, category),
        source_url=chosen[0],
        source_rank=int(chosen[1]),
        landing_url=None if landing is None else landing[0],
        distributions=tuple(r.distribution for r in resources if r.distribution is not None)[:MAX_DISTRIBUTIONS],
    )

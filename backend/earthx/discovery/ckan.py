"""Fetch and extract for CKAN (M5-19 plan §4.2, §5): the packages of ``package_search``, one find per package.

The listing is read by key (keyset paging, plan §12.7): packages sorted by ``id``, each page asked with ``start=0``
and a filter for the ids after the last one read (``id:{"<last>" TO *]``). No offset grows, so no limit on deep
offsets is reached (opendata.swiss answers 429 from offset ~10 100 on, Otto 19.11.2026), and packages that come or
go while the listing is read move no page: every package that exists from before the pass reached its id until after
is read once. CKAN answers without ``ETag`` (adr/0025 §3), so the hash of each package decides. An incremental run
asks only for packages whose ``metadata_modified`` lies after the start of the last pass less an hour, as
ckanext-harvest does (adr/0025 §3a); a full one asks for all. Only a full listing that named at least one package can
mark finds ``gone`` (A3).

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
from earthx.discovery.links import LinkRank, checked_link, choose_link, link_problem
from earthx.discovery.stac import Fetch

__all__ = [
    "INCREMENTAL_OVERLAP",
    "PAGE_ROWS",
    "CkanListing",
    "ckan_pages",
    "extract_package",
    "link_reasons",
    "package_key",
    "search_params",
    "stable_package",
]

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
# The page of a resource in CKAN itself: it is named after the resource's id, which a portal that re-creates its
# resources on every harvest changes (Otto, 19.11.2026), so it is no stable link "Source".
_RESOURCE_PAGE = re.compile(r"/resource/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?:[/?#]|$)", re.I)
_PUBLIC = "PUBLIC"
_NOT_PUBLIC = frozenset({"RESTRICTED", "NON_PUBLIC", "NONPUBLIC", "NON-PUBLIC"})


@dataclass(slots=True)
class CkanListing:
    """How the listing stands and ended. Before a page is handed out, ``last_key`` already is its last package, so a
    run that stops after it keeps it, and the next run goes on after it (Otto, 18./19.11.2026)."""

    full: bool
    #: The id of the last package read: the next page asks for the ids after it. ``None`` at the start of a pass.
    last_key: str | None = None
    #: The packages the pass has read so far, over all its runs.
    read: int = 0
    not_modified: bool = False
    #: The last page was read.
    exhausted: bool = False
    complete: bool = False
    #: CKAN has no validators of its listing (adr/0025 §3).
    validators: None = None
    #: The pass read no package at all; a full one of them is no evidence that every find is gone.
    empty: bool = False


#: Bookkeeping of CKAN that the extract never reads and that changes when nothing else does (a re-harvest by the
#: portal touches ``metadata_modified``): left out of the hash of the raw answer, kept in the answer itself.
VOLATILE_FIELDS = frozenset({"metadata_modified", "revision_id"})
VOLATILE_RESOURCE_FIELDS = frozenset({"metadata_modified", "revision_id", "cache_last_updated"})


def stable_package(package: Any) -> Any:
    """``package`` without :data:`VOLATILE_FIELDS` and its resources without :data:`VOLATILE_RESOURCE_FIELDS`: what the
    hash that decides whether a package is extracted again is taken over (Otto, 19.11.2026)."""
    if not isinstance(package, dict):
        return package
    stable = {key: value for key, value in package.items() if key not in VOLATILE_FIELDS}
    resources = stable.get("resources")
    if isinstance(resources, list):
        stable["resources"] = [
            {k: v for k, v in r.items() if k not in VOLATILE_RESOURCE_FIELDS} if isinstance(r, dict) else r
            for r in resources
        ]
    return stable


def package_key(package: object) -> str | None:
    """The id of a package if it can be a key at the source."""
    if not isinstance(package, dict):
        return None
    key = package.get("id")
    return key if isinstance(key, str) and _KEY.fullmatch(key) else None


def _quoted(key: str) -> str:
    """A key as a quoted term of the Solr query syntax; :func:`package_key` admits no quote or backslash anyway."""
    return '"' + key.replace("\\", "\\\\").replace('"', '\\"') + '"'


def search_params(source: SourceConfig, after: str | None, since: datetime | None) -> dict[str, str | int]:
    """The query of one page; the gateway assembles it into the address. ``start`` is always 0 (keyset paging)."""
    assert isinstance(source.filter, CkanFilter)
    clauses = [] if source.filter.fq is None else [f"({source.filter.fq})"]
    if since is not None:
        clauses.append(f"metadata_modified:[{since.astimezone(UTC):%Y-%m-%dT%H:%M:%SZ} TO *]")
    if after is not None:
        # Exclusive lower bound on the sort key: the ids after the last one read.
        clauses.append(f"id:{{{_quoted(after)} TO *]")
    params: dict[str, str | int] = {"rows": source.rows_per_page or PAGE_ROWS, "start": 0, "sort": "id asc"}
    if clauses:
        params["fq"] = " AND ".join(clauses)
    return params


async def ckan_pages(
    fetch: Fetch, source: SourceConfig, since: datetime | None, listing: CkanListing
) -> AsyncIterator[list[tuple[str | None, Any]]]:
    """The packages of each page as ``(key, package)`` after where ``listing`` stands; a key ``None`` marks one that
    cannot be a find. ``since`` is the lower bound of ``metadata_modified`` of an incremental listing (aware, asked in
    UTC), ``None`` for a full one.

    :class:`ShapeError` where the source answers no listing, or does not honour the order and the filter by key: a page
    that names an id at or before the last one read, or a page without a key to go on from."""
    while True:
        response = await fetch(
            f"{source.endpoint}/package_search", params=search_params(source, listing.last_key, since)
        )
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
        page = [(package_key(package), package) for package in packages]
        keys = [key for key, _ in page if key is not None]
        if keys != sorted(keys) or (listing.last_key is not None and keys and keys[0] <= listing.last_key):
            raise ShapeError("the listing does not keep the order by id after the last key")
        listing.read += len(page)
        listing.exhausted = not page or len(page) >= count
        if keys:
            listing.last_key = keys[-1]
        elif not listing.exhausted:
            raise ShapeError("a page of the listing names no key to go on from")
        yield page
        if listing.exhausted:
            break
    listing.empty = listing.read == 0
    listing.complete = listing.full and not listing.empty


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
    #: The page address depends on the resource's id: a CKAN resource page, or the id in its path or query.
    by_id: bool = False

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
    resource_id = text_of(resource.get("id"))
    by_id = bool(access) and (
        bool(_RESOURCE_PAGE.search(access or ""))
        or (resource_id is not None and len(resource_id) >= 8 and resource_id.lower() in (access or "").lower())
    )
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
        by_id=by_id,
    )


def _viewer_pages(resources: Iterable[_Resource]) -> list[str]:
    """Rank 1: a page for people at the provider (accessURL without downloadURL), not its documentation, no service,
    not an address made of the resource's id. Sorted by address, so that several such pages give the same link
    whichever order the source lists its resources in (Otto, 19.11.2026)."""
    return sorted(
        r.access
        for r in resources
        if r.access is not None
        and r.kind == "page"
        and r.download is None
        and not r.documentation
        and not r.by_id
        and not _SERVICE_QUERY.search(r.access)
    )


def _page_or_none(url: object) -> object:
    """``url`` unless it is a capabilities address or names a file by its ending (plan §6: never a service or a file)."""
    if not isinstance(url, str) or _SERVICE_QUERY.search(url):
        return None
    name = url.split("#")[0].split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    ending = name.rsplit(".", 1)[-1] if "." in name else ""
    return None if resource_kind(ending, None) in FILE_KINDS | {"service"} else url


# Fields of a package that name a person: never read for a report (adr/0033 §5).
_PERSON_FIELD = re.compile(r"author|maintainer|contact|email|e-mail|person|name$", re.IGNORECASE)
_ADDRESS = re.compile(r"https?://\S+", re.IGNORECASE)


def link_reasons(package: Mapping[str, Any]) -> list[tuple[str, str | None]]:
    """Why a package reaches neither rank 1 nor rank 2 of the link "Source" (plan §6): codes with the address each is
    about, for ``--explain-links`` (Otto, 19.11.2026). Rank 2, the field ``url`` of the package: ``url_<problem>``
    (``url_empty``, ``url_http``, ``url_file``, ``url_service``, ``url_start_page`` …). Rank 1, the resources:
    ``no_resources``, ``no_html_resource``, ``html_<problem>`` per rejected page (``html_with_download``,
    ``html_documentation``, ``html_by_id``, ``html_service``, ``html_http`` …), and ``resource_without_format`` where
    a resource has an address but neither a format nor a media type. Other fields that hold an address, where the
    extract does not look: ``field:<name>`` and ``extras:<key>``; person fields are never named."""
    reasons: list[tuple[str, str | None]] = []
    url = text_of(package.get("url"))
    problem = link_problem(url)
    if problem is None and url is not None:
        if _SERVICE_QUERY.search(url):
            problem = "service"
        elif _page_or_none(url) is None:
            problem = "file"
    if problem is not None:
        reasons.append((f"url_{problem}", url))
    raw_resources = package.get("resources")
    documents = [r for r in raw_resources if isinstance(r, dict)] if isinstance(raw_resources, list) else []
    if not documents:
        reasons.append(("no_resources", None))
    resources = [_resource(r) for r in documents]
    if documents and not any(r.kind == "page" for r in resources):
        reasons.append(("no_html_resource", None))
    for resource in resources:
        if resource.kind is None and resource.download is None and resource.access is not None:
            reasons.append(("resource_without_format", resource.access))
        if resource.kind != "page":
            continue
        problem = link_problem(resource.access)
        if resource.download is not None:
            problem = "with_download"
        elif resource.documentation:
            problem = "documentation"
        elif resource.by_id:
            problem = "by_id"
        elif _SERVICE_QUERY.search(resource.access or ""):
            problem = "service"
        if problem is not None:
            reasons.append((f"html_{problem}", resource.access))
    for name, value in package.items():
        if name in ("url", "resources", "extras") or not isinstance(name, str) or _PERSON_FIELD.search(name):
            continue
        if isinstance(value, str) and _ADDRESS.fullmatch(value.strip()):
            reasons.append((f"field:{name}", value.strip()))
    for key, value in _extras(package).items():
        if _PERSON_FIELD.search(key):
            continue
        if isinstance(value, str) and _ADDRESS.fullmatch(value.strip()):
            reasons.append((f"extras:{key}", value.strip()))
    return reasons


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

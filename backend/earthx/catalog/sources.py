"""The seed of the harvest: one YAML file per source under ``backend/catalog/sources/`` (adr/0025 §5.2, M5-19 plan §4.1).

A file is Otto's release of a source (adr/0033 §4, level "Quelle"). Read as strictly as the entries: every field is
named, none has a default, an unknown one is an error (KLAERUNGEN B10). The limits per host do not live here but in
``hosts.yaml`` (M5-36, plan F6): the registry checks that every host a source reads from has limits there.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from types import MappingProxyType

from earthx.catalog.entry_files import EntryFileError, read_yaml
from earthx.catalog.registry import PROTOTYPE_PREFIX, Maturity
from earthx.gateway import UrlRejected, check_robots_exception_path, host_of

__all__ = [
    "SOURCES_DIR",
    "CatalogPageCheck",
    "CkanFilter",
    "RobotsException",
    "SourceConfig",
    "SourceProtocol",
    "StacFilter",
    "read_source",
    "read_sources",
]

SOURCES_DIR = Path(__file__).resolve().parents[2] / "catalog" / "sources"
_README = "README.md"
# Reserved for the hand entries of the listed path (M5-40 A10): `catalog-load` would tombstone harvested rows of it.
_HAND_SOURCE = "listed"
_ID = re.compile(r"[a-z][a-z0-9-]{1,62}")
_HTTPS = re.compile(r"https://[^\s/?#@]+(?:/[^\s?#]*)?")
_EXTRA_KEY = re.compile(r"[A-Za-z][A-Za-z0-9_:.-]{0,63}")
_PREFIX = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_FIELDS = frozenset(
    {
        "source_id",
        "protocol",
        "endpoint",
        "catalog_page",
        "filter",
        "max_requests_per_run",
        "max_pages_per_run",
        "rows_per_page",
        "full_every_days",
        "robots_exception",
        "maturity",
        "enabled",
        "country",
        "dedupe_rank",
    }
)
#: Fields a seed file may leave out (the default holds).
_OPTIONAL_FIELDS = frozenset({"dedupe_collection_links", "catalog_page_check"})
#: The lowest precedence a source may have among duplicates (M5-20 plan §8): 1 wins over 2.
MAX_DEDUPE_RANK = 9
_COUNTRY = re.compile(r"[A-Z]{2}")
MAX_REQUESTS_PER_RUN = 10_000


class SourceProtocol(Enum):
    STAC_API = "stac-api"
    CKAN = "ckan"


@dataclass(frozen=True, slots=True)
class StacFilter:
    """The collections of a STAC API to harvest: those whose id starts with one of the prefixes, all where none."""

    collection_prefixes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CkanFilter:
    """``fq`` of ``package_search`` as written, or none; ``publisher_field`` names where the source keeps the publisher
    (GovData ``publisher_name``, opendata.swiss ``organization``, adr/0025 §5.2); ``page_extras`` the keys of extras
    that may hold the page of a dataset at the provider, read in order after the field ``url`` (rank 2 of the link
    "Source"; GovData ``uri``, ``guid``, F12 = 1, Otto 19.11.2026)."""

    fq: str | None
    publisher_field: str
    page_extras: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RobotsException:
    """The one path of a source's host whose Disallow in robots.txt the harvest waives, with the provider's documentation
    of it (Otto, 18.11.2026; adr/0025 §6.2). The path is the endpoint's own: the metadata API, nothing else of the
    host. robots.txt is still read and its Crawl-delay kept."""

    path: str
    evidence: str


@dataclass(frozen=True, slots=True)
class CatalogPageCheck:
    """How the link check verifies a link to this catalogue's own page of a dataset (M5-67 F12 = 2, Otto 24.11.2026).

    ``via``: ``page`` asks the page itself; ``api`` asks the catalogue's API whether a dataset of the name in the link
    exists (a CKAN source with ``catalog_page``, under its robots exception). ``form_confirmed_on``: the day Otto opened
    the form of ``catalog_page`` in a browser and found the page of the dataset; without it, the API proves only that
    the dataset exists, not that the address leads to it, so such links stay unchecked."""

    via: str = "page"
    form_confirmed_on: date | None = None


@dataclass(frozen=True, slots=True)
class SourceConfig:
    source_id: str
    protocol: SourceProtocol
    endpoint: str
    #: The page of a dataset in the catalogue, with ``{id}`` (STAC) or ``{name}`` (CKAN); the last rank of the link
    #: "Source" (plan §6). ``None`` where the catalogue has no page per dataset.
    catalog_page: str | None
    filter: StacFilter | CkanFilter
    max_requests_per_run: int
    #: The pages of a CKAN listing one run reads at most; ``None`` without a cap. A pass larger than it goes on in the
    #: next run (Otto, 18.11.2026: a source that keeps a quota, opendata.swiss).
    max_pages_per_run: int | None
    #: The packages a page of a CKAN listing asks for; ``None`` for the harvest's default (100). Fewer rows, less work
    #: for a slow catalogue per request (Otto, 19.11.2026).
    rows_per_page: int | None
    full_every_days: int
    #: ``None``: robots.txt is obeyed as written.
    robots_exception: RobotsException | None
    maturity: Maturity
    enabled: bool
    #: The state (ISO 3166-1) a catalogue's datasets lie in, the last step of the spatial extent (M5-20 plan §6.1,
    #: F1 = 1): a find with nothing better is in this state, without a footprint. ``None`` for a catalogue of the world.
    country: str | None
    #: Precedence among duplicates of the same dataset (M5-20 plan §8, F4 = 1): the provider's own catalogue before a
    #: portal that harvests it. 1 wins over 2.
    dedupe_rank: int
    #: A collection of the FSDI named by a viewer link in the files, references or skipped pages of a find is a dedupe
    #: key (Otto, 24.11.2026): opendata.swiss names the collections it lists in the links of its resources. Off for
    #: every other source.
    dedupe_collection_links: bool = False
    #: How the link check verifies the links to ``catalog_page`` (M5-67 F12 = 2); by default the page itself.
    catalog_page_check: CatalogPageCheck = CatalogPageCheck()

    @property
    def host(self) -> str:
        """The one host the harvest of this source asks."""
        return host_of(self.endpoint)


def _bad(name: str, problem: str) -> EntryFileError:
    return EntryFileError(f"sources/{name}: {problem}")


def _count(name: str, data: Mapping[str, object], field: str, high: int) -> int:
    value = data[field]
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= high:
        raise _bad(name, f"{field} is a whole number from 1 to {high}")
    return value


def _pages(name: str, protocol: SourceProtocol, value: object) -> int | None:
    if value is None:
        return None
    if protocol is not SourceProtocol.CKAN:
        raise _bad(name, "max_pages_per_run is for a ckan source; a stac-api source has null")
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_REQUESTS_PER_RUN:
        raise _bad(name, f"max_pages_per_run is null or a whole number from 1 to {MAX_REQUESTS_PER_RUN}")
    return value


#: The most rows a CKAN page may ask for; ``package_search`` caps them at ``ckan.search.rows_max`` (1 000 by default).
MAX_ROWS_PER_PAGE = 1000


def _rows(name: str, protocol: SourceProtocol, value: object) -> int | None:
    if value is None:
        return None
    if protocol is not SourceProtocol.CKAN:
        raise _bad(name, "rows_per_page is for a ckan source; a stac-api source has null")
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_ROWS_PER_PAGE:
        raise _bad(name, f"rows_per_page is null or a whole number from 1 to {MAX_ROWS_PER_PAGE}")
    return value


def _filter(name: str, protocol: SourceProtocol, value: object) -> StacFilter | CkanFilter:
    if protocol is SourceProtocol.STAC_API:
        if not isinstance(value, dict) or set(value) != {"collection_prefixes"}:
            raise _bad(name, "filter of a stac-api source has collection_prefixes, nothing else")
        prefixes = value["collection_prefixes"]
        if not isinstance(prefixes, list) or not all(isinstance(p, str) and _PREFIX.fullmatch(p) for p in prefixes):
            raise _bad(name, "collection_prefixes is a list of collection id prefixes")
        return StacFilter(tuple(prefixes))
    if not isinstance(value, dict) or set(value) != {"fq", "publisher_field", "page_extras"}:
        raise _bad(name, "filter of a ckan source has fq, publisher_field and page_extras, nothing else")
    fq, field, extras = value["fq"], value["publisher_field"], value["page_extras"]
    if not isinstance(extras, list) or not all(isinstance(k, str) and _EXTRA_KEY.fullmatch(k) for k in extras):
        raise _bad(name, "page_extras is a list of keys of extras")
    if len(set(extras)) != len(extras):
        raise _bad(name, "page_extras names each key once")
    if fq is not None and (not isinstance(fq, str) or not fq.strip() or len(fq) > 1000):
        raise _bad(name, "fq is null or a non-blank text of at most 1000 characters")
    if field not in ("publisher_name", "organization"):
        raise _bad(name, "publisher_field is publisher_name or organization")
    return CkanFilter(fq, field, tuple(extras))


def _catalog_page(name: str, protocol: SourceProtocol, value: object) -> str | None:
    if value is None:
        return None
    placeholder = "{id}" if protocol is SourceProtocol.STAC_API else "{name}"
    if not isinstance(value, str) or not _HTTPS.fullmatch(value.split("#")[0].replace(placeholder, "x")):
        raise _bad(name, "catalog_page is null or an https address")
    if value.count(placeholder) != 1 or value.replace(placeholder, "").count("{"):
        raise _bad(name, f"catalog_page names {placeholder} once and no other placeholder")
    return value


def _robots_exception(name: str, endpoint: str, value: object) -> RobotsException | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"path", "evidence"}:
        raise _bad(name, "robots_exception is null or has path and evidence, nothing else")
    try:
        path = check_robots_exception_path(value["path"])
    except ValueError as error:
        raise _bad(name, f"robots_exception.path: {error}") from None
    endpoint_path = "/" + endpoint.split("://", 1)[1].partition("/")[2]
    if path != endpoint_path.rstrip("/") + "/":
        raise _bad(name, "robots_exception.path is the path of endpoint with a trailing '/', the metadata API only")
    evidence = value["evidence"]
    if not isinstance(evidence, str) or not _HTTPS.fullmatch(evidence.split("#")[0]):
        raise _bad(name, "robots_exception.evidence is the https address of the provider's documentation of its API")
    return RobotsException(path, evidence)


def _catalog_page_check(
    name: str, protocol: SourceProtocol, catalog_page: str | None, value: object
) -> CatalogPageCheck:
    if value is None:
        return CatalogPageCheck()
    if not isinstance(value, dict) or set(value) != {"via", "form_confirmed_on"}:
        raise _bad(name, "catalog_page_check has via and form_confirmed_on, nothing else")
    via, day = value["via"], value["form_confirmed_on"]
    if via not in ("page", "api"):
        raise _bad(name, "catalog_page_check.via is page or api")
    if via == "api" and (protocol is not SourceProtocol.CKAN or catalog_page is None):
        raise _bad(name, "catalog_page_check.via api needs a ckan source with a catalog_page")
    if isinstance(day, str):
        try:
            day = date.fromisoformat(day)
        except ValueError:
            raise _bad(name, "catalog_page_check.form_confirmed_on is null or a day") from None
    if day is not None and (not isinstance(day, date) or day > date.today()):
        raise _bad(name, "catalog_page_check.form_confirmed_on is null or a day, not in the future")
    return CatalogPageCheck(via, day)


def read_source(path: Path) -> SourceConfig:
    """One seed file, checked; :class:`EntryFileError` names the file and the field, never a value."""
    name = path.name
    data = read_yaml(path)
    if not isinstance(data, dict) or not _FIELDS <= set(data) <= _FIELDS | _OPTIONAL_FIELDS:
        optional = ", ".join(sorted(_OPTIONAL_FIELDS))
        raise _bad(name, f"needs exactly the fields {', '.join(sorted(_FIELDS))} (and may have {optional})")
    source_id = data["source_id"]
    if not isinstance(source_id, str) or not _ID.fullmatch(source_id) or f"{source_id}.yaml" != name:
        raise _bad(name, "source_id is lower case, digits and '-', and the file is named after it")
    if source_id == _HAND_SOURCE or source_id.startswith(PROTOTYPE_PREFIX):
        raise _bad(name, f"the source id {_HAND_SOURCE!r} and the prefix {PROTOTYPE_PREFIX!r} are reserved")
    try:
        protocol = SourceProtocol(data["protocol"])
    except ValueError:
        raise _bad(name, f"protocol is one of {', '.join(p.value for p in SourceProtocol)}") from None
    endpoint = data["endpoint"]
    if not isinstance(endpoint, str) or not _HTTPS.fullmatch(endpoint) or endpoint.endswith("/"):
        raise _bad(name, "endpoint is an https address without query and without a trailing '/'")
    try:
        host_of(endpoint)
    except UrlRejected:
        raise _bad(name, "the host of endpoint is not a host name") from None
    try:
        maturity = Maturity(data["maturity"])
    except ValueError:
        raise _bad(name, "maturity is a maturity of the registry") from None
    if not isinstance(data["enabled"], bool):
        raise _bad(name, "enabled is true or false")
    country = data["country"]
    if country is not None and (not isinstance(country, str) or not _COUNTRY.fullmatch(country)):
        raise _bad(name, "country is null or an ISO 3166-1 code of two capital letters")
    collection_links = data.get("dedupe_collection_links", False)
    if not isinstance(collection_links, bool):
        raise _bad(name, "dedupe_collection_links is true or false")
    catalog_page = _catalog_page(name, protocol, data["catalog_page"])
    return SourceConfig(
        source_id=source_id,
        protocol=protocol,
        endpoint=endpoint,
        catalog_page=catalog_page,
        filter=_filter(name, protocol, data["filter"]),
        max_requests_per_run=_count(name, data, "max_requests_per_run", MAX_REQUESTS_PER_RUN),
        max_pages_per_run=_pages(name, protocol, data["max_pages_per_run"]),
        rows_per_page=_rows(name, protocol, data["rows_per_page"]),
        full_every_days=_count(name, data, "full_every_days", 365),
        robots_exception=_robots_exception(name, endpoint, data["robots_exception"]),
        maturity=maturity,
        enabled=data["enabled"],
        country=country,
        dedupe_rank=_count(name, data, "dedupe_rank", MAX_DEDUPE_RANK),
        dedupe_collection_links=collection_links,
        catalog_page_check=_catalog_page_check(name, protocol, catalog_page, data.get("catalog_page_check")),
    )


def read_sources(directory: Path = SOURCES_DIR) -> Mapping[str, SourceConfig]:
    """Every seed file of ``directory`` by source id; an empty mapping where the directory does not exist."""
    if not directory.is_dir():
        return MappingProxyType({})
    sources: dict[str, SourceConfig] = {}
    for path in sorted(directory.iterdir()):
        if path.name == _README:
            continue
        if path.suffix != ".yaml" or not path.is_file():
            raise _bad(path.name, "only <source_id>.yaml files and a README.md belong here")
        source = read_source(path)
        sources[source.source_id] = source
    return MappingProxyType(sources)

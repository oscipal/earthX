"""The licence rules of harvested listed entries: a licence catalogue and the grants per source (adr/0033 §6.2, L2).

``backend/catalog/licenses/terms.yaml`` grades every licence once: the statements of sources that mean it, each
verbatim (``matches``), and the result as for a full entry (``license``). ``backend/catalog/licenses/grants/<source>.yaml``
says which publisher of a source may be listed with which of them. The rule stays "publisher + licence statement →
grade", both verbatim (adr/0025 §6.7): only blanks at the edges and a trailing ``/`` of a statement are ignored, never
case or spelling. Every file is a decision of Otto's in Git, merged like an entry; Postgres keeps no copy of it.

Read by ``discovery`` (the report) and ``catalog-load`` (which checks them like every other file of the image).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from types import MappingProxyType

from earthx.catalog.datasets import CATALOG_DIR
from earthx.catalog.entry_files import EntryFileError, _validate, read_yaml
from earthx.catalog.registry import ENTRY_FILE_CONFIG, LicenseInfo, LicenseTier

__all__ = [
    "CLASSES_ABOVE_CATALOG",
    "LICENCE_CLASSES",
    "LICENSES_DIR",
    "LICENSOR_HOSTS",
    "SPELLINGS_FILE",
    "SPELLING_RULES",
    "Grant",
    "LicenceCatalogue",
    "LicenceMatch",
    "LicenceTerm",
    "Spelling",
    "is_standard_term",
    "load_licences",
    "normal_statement",
]

LICENSES_DIR = CATALOG_DIR / "licenses"
_README = "README.md"
_REF = re.compile(r"[a-z0-9][a-z0-9.-]{0,63}")
_SOURCE_ID = re.compile(r"[a-z][a-z0-9-]{1,62}")
#: The order of the tiers from narrowest to widest (KLAERUNGEN B11).
_TIER_ORDER = (LicenseTier.CATALOG, LicenseTier.DISPLAY, LicenseTier.PROCESSING)
#: The classes of the licence list (docs/plans/m5/m5-20-lizenzliste.md); K7 is no licence and never in the catalogue.
LICENCE_CLASSES = ("K1", "K2", "K3", "K4", "K5", "K6")
#: The classes whose licences may be graded above the catalogue tier (Otto, 25.11.2026): sharing and changing allowed,
#: at most attribution. Share alike (K3) stays in the catalogue, as EarthX cannot pass a licence on to its results.
CLASSES_ABOVE_CATALOG = frozenset({"K1", "K2"})


def normal_statement(value: str) -> str:
    """A licence statement as it is compared: blanks at the edges and one trailing ``/`` dropped, nothing else."""
    text = value.strip()
    return text[:-1] if text.endswith("/") else text


@dataclass(frozen=True, slots=True)
class LicenceTerm:
    """One licence of the catalogue: what it means, graded once (adr/0033 §6.2)."""

    license_ref: str
    #: The class of the licence list (K1-K6); it bounds the tier (:data:`CLASSES_ABOVE_CATALOG`).
    licence_class: str
    matches: tuple[str, ...]
    license: LicenseInfo
    approved_on: date


@dataclass(frozen=True, slots=True)
class Grant:
    """One publisher of one source and the licences it may be listed with."""

    publisher: str
    licenses: tuple[str, ...]
    approved_on: date


@dataclass(frozen=True, slots=True)
class Spelling:
    """A further spelling of a graded standard licence that the pipeline added (M5-67 plan §7): never a grade."""

    license_ref: str
    statement: str
    #: S1 an address, S2 an identifier, S3 a text that differs only in typography.
    rule: str
    added_on: date
    #: Set by Otto to take the spelling back; the line stays, so that no later run adds it again.
    withdrawn_on: date | None = None


for _part in (LicenceTerm, Grant, Spelling):
    _part.__pydantic_config__ = ENTRY_FILE_CONFIG  # type: ignore[attr-defined]
del _part


@dataclass(frozen=True, slots=True)
class LicenceMatch:
    """The outcome for one find: the licence its entry carries and the rule, or why it waits (adr/0033 §7).

    ``reason`` is ``no_licence`` (the source states none), ``unknown_licence`` (a statement the catalogue does not
    know) or ``not_granted`` (known, but not granted to this publisher of this source); ``None`` for a match.
    """

    license: LicenseInfo | None
    rule: str | None
    refs: tuple[str, ...]
    reason: str | None


@dataclass(frozen=True, slots=True)
class LicenceCatalogue:
    terms: Mapping[str, LicenceTerm]
    #: Normal statement → licence ref, from ``matches`` and from ``spellings.yaml``.
    by_statement: Mapping[str, str]
    #: Source → publisher → granted licence refs.
    grants: Mapping[str, Mapping[str, frozenset[str]]]
    #: Normal statement → licence ref, only those of ``spellings.yaml``.
    spellings: Mapping[str, str] = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        """A hash of every grade, spelling and grant: a report derives its rows anew when one changes."""
        terms = sorted((ref, term.matches, repr(term.license)) for ref, term in self.terms.items())
        grants = sorted((source, sorted((p, sorted(r)) for p, r in by.items())) for source, by in self.grants.items())
        spellings = sorted(self.spellings.items())
        return hashlib.sha256(repr((terms, grants, spellings)).encode("utf-8")).hexdigest()

    def granted(self, source_id: str, publisher: str | None, refs: tuple[str, ...]) -> bool:
        """Whether every licence of ``refs`` is still in the catalogue and granted to this publisher of this source."""
        allowed = self.grants.get(source_id, {}).get(publisher or "", frozenset())
        return all(ref in self.terms and ref in allowed for ref in refs)

    def match(self, source_id: str, publisher: str | None, statements: Iterable[str]) -> LicenceMatch:
        """The licence of a find of ``source_id`` by ``publisher`` with these statements (adr/0033 §6, §7).

        Every statement must mean a licence of the catalogue that is granted to this publisher of this source; the
        entry then carries the narrowest of them (plan A10): the lowest tier, every flag only where all allow it.
        """
        normal = sorted({text for value in statements if (text := normal_statement(value))})
        if not normal:
            return LicenceMatch(None, None, (), "no_licence")
        refs = []
        for statement in normal:
            ref = self.by_statement.get(statement)
            if ref is None:
                return LicenceMatch(None, None, (), "unknown_licence")
            refs.append(ref)
        unique = tuple(sorted(set(refs)))
        granted = self.grants.get(source_id, {}).get(publisher or "", frozenset())
        if not set(unique) <= granted:
            return LicenceMatch(None, None, unique, "not_granted")
        rule = f"{source_id}/{publisher}/{'+'.join(unique)}"
        return LicenceMatch(_narrowest([self.terms[ref].license for ref in unique]), rule, unique, None)


def _narrowest(licences: list[LicenseInfo]) -> LicenseInfo:
    """The licence whose tier is lowest (ties: the one with fewest rights) with every flag only where all allow it."""
    base = min(
        licences,
        key=lambda lic: (
            _TIER_ORDER.index(lic.tier),
            sum((lic.commercial_use, lic.distribution, lic.derivatives, not lic.share_alike)),
        ),
    )
    if len(licences) == 1:
        return base
    return LicenseInfo(
        spdx_id=base.spdx_id,
        name=base.name,
        url=base.url,
        commercial_use=all(lic.commercial_use for lic in licences),
        distribution=all(lic.distribution for lic in licences),
        derivatives=all(lic.derivatives for lic in licences),
        share_alike=any(lic.share_alike for lic in licences),
        attribution_required=any(lic.attribution_required for lic in licences),
        tier=base.tier,
        attribution_modified=base.attribution_modified,
        attribution_unmodified=base.attribution_unmodified,
        terms=base.terms,
    )


def _check_term(term: LicenceTerm, where: str) -> None:
    lic = term.license
    if not _REF.fullmatch(term.license_ref):
        raise EntryFileError(f"{where}: license_ref is lower case, digits, '.' and '-'")
    if not term.matches or not all(normal_statement(text) for text in term.matches):
        raise EntryFileError(f"{where}: matches names at least one statement, each a non-blank text")
    if term.licence_class not in LICENCE_CLASSES:
        raise EntryFileError(f"{where}: licence_class is one of {', '.join(LICENCE_CLASSES)}")
    if lic.tier is not LicenseTier.CATALOG and not (lic.derivatives and lic.distribution):
        # KLAERUNGEN B11: display and processing need both; without one of them only the catalogue.
        raise EntryFileError(f"{where}: tier above catalog needs derivatives and distribution")
    if lic.tier is not LicenseTier.CATALOG and term.licence_class not in CLASSES_ABOVE_CATALOG:
        raise EntryFileError(f"{where}: tier above catalog only for the classes K1 and K2 (Otto, 25.11.2026)")
    if term.licence_class in CLASSES_ABOVE_CATALOG and (lic.share_alike or not lic.commercial_use):
        # A K1 or K2 licence allows commercial use and asks for no share alike: else its class is wrong.
        raise EntryFileError(f"{where}: a licence of class {term.licence_class} allows commercial use and no share alike")
    if not (lic.spdx_id or (lic.name and lic.url)):
        raise EntryFileError(f"{where}: the licence needs an SPDX identifier or a name and a URL")
    if term.approved_on > date.today():
        raise EntryFileError(f"{where}: approved_on lies in the future")


def _read_terms(path: Path) -> tuple[LicenceTerm, ...]:
    data = read_yaml(path) if path.exists() else None
    if data is None:
        return ()
    if not isinstance(data, list):
        raise EntryFileError(f"{path.name}: the licence catalogue is a list")
    terms = tuple(_validate(LicenceTerm, item, f"{path.name}[{index}]") for index, item in enumerate(data))
    for index, term in enumerate(terms):
        _check_term(term, f"{path.name}[{index}]")
    return terms


def _read_grants(directory: Path, known_refs: Collection[str], known_sources: Collection[str]) -> dict[str, dict]:
    grants: dict[str, dict[str, frozenset[str]]] = {}
    if not directory.is_dir():
        return grants
    for path in sorted(directory.iterdir()):
        if path.name == _README:
            continue
        name = f"grants/{path.name}"
        source_id = path.stem
        if path.suffix != ".yaml" or not path.is_file() or not _SOURCE_ID.fullmatch(source_id):
            raise EntryFileError(f"{name}: only <source_id>.yaml files and a README.md belong here")
        if source_id not in known_sources:
            raise EntryFileError(f"{name}: no source of that id in sources/")
        data = read_yaml(path)
        if data is None:
            data = []
        if not isinstance(data, list):
            raise EntryFileError(f"{name}: the grants of a source are a list")
        by_publisher: dict[str, frozenset[str]] = {}
        for index, item in enumerate(data):
            grant: Grant = _validate(Grant, item, f"{name}[{index}]")
            where = f"{name}[{index}]"
            if not grant.publisher.strip() or grant.publisher != grant.publisher.strip():
                raise EntryFileError(f"{where}: publisher is the value of the source's publisher field, exactly")
            if grant.publisher in by_publisher:
                raise EntryFileError(f"{where}: the publisher stands twice")
            if not grant.licenses or len(set(grant.licenses)) != len(grant.licenses):
                raise EntryFileError(f"{where}: licenses names at least one licence, each once")
            if unknown := sorted(set(grant.licenses) - set(known_refs)):
                raise EntryFileError(f"{where}: licenses not in terms.yaml: {', '.join(unknown)}")
            if grant.approved_on > date.today():
                raise EntryFileError(f"{where}: approved_on lies in the future")
            by_publisher[grant.publisher] = frozenset(grant.licenses)
        grants[source_id] = by_publisher
    return grants


SPELLINGS_FILE = "spellings.yaml"
SPELLING_RULES = ("S1", "S2", "S3")
#: Hosts of licensors whose terms are standard licences without an SPDX identifier (the terms of opendata.swiss, the
#: licence pages of GovData; M5-67 plan §7).
LICENSOR_HOSTS = frozenset({"opendata.swiss", "govdata.de"})
_HOST = re.compile(r"(?i)https?://(?:www\.)?([^/?#\s:]+)")


def is_standard_term(term: LicenceTerm) -> bool:
    """A licence named by an SPDX identifier of the SPDX list or by the address of a licensor of
    :data:`LICENSOR_HOSTS`: only such a licence may get spellings the pipeline adds."""
    spdx = term.license.spdx_id or ""
    host = _HOST.match(term.license.url or "")
    if spdx and not spdx.startswith("LicenseRef-"):
        return True
    return host is not None and host[1].lower() in LICENSOR_HOSTS


def _read_spellings(path: Path, by_ref: Mapping[str, LicenceTerm], by_statement: dict[str, str]) -> dict[str, str]:
    """The spellings the pipeline added, each a statement no other licence means (M5-67 plan §7)."""
    data = read_yaml(path) if path.exists() else None
    if data is None:
        return {}
    if not isinstance(data, list):
        raise EntryFileError(f"{path.name}: the spellings are a list")
    found: dict[str, str] = {}
    for index, item in enumerate(data):
        where = f"{path.name}[{index}]"
        spelling: Spelling = _validate(Spelling, item, where)
        normal = normal_statement(spelling.statement)
        if spelling.license_ref not in by_ref:
            raise EntryFileError(f"{where}: license_ref not in terms.yaml")
        if not is_standard_term(by_ref[spelling.license_ref]):
            raise EntryFileError(f"{where}: a spelling belongs to a standard licence (SPDX or a licensor's address)")
        if spelling.rule not in SPELLING_RULES:
            raise EntryFileError(f"{where}: rule is S1, S2 or S3")
        if not normal:
            raise EntryFileError(f"{where}: statement is a non-blank text")
        if normal in by_statement:
            raise EntryFileError(f"{where}: the statement already means {by_statement[normal]}")
        if spelling.added_on > date.today():
            raise EntryFileError(f"{where}: added_on lies in the future")
        if spelling.withdrawn_on is not None:
            if spelling.withdrawn_on < spelling.added_on:
                raise EntryFileError(f"{where}: withdrawn_on lies before added_on")
            continue
        by_statement[normal] = found[normal] = spelling.license_ref
    return found


def load_licences(known_sources: Collection[str], directory: Path = LICENSES_DIR) -> LicenceCatalogue:
    """The licence catalogue, the spellings and the grants under ``directory``, checked (adr/0033 §6.2): a statement
    means at most one licence, every granted licence is in the catalogue, every source of a grant is one of
    ``known_sources``."""
    terms = _read_terms(directory / "terms.yaml")
    by_ref: dict[str, LicenceTerm] = {}
    by_statement: dict[str, str] = {}
    for index, term in enumerate(terms):
        where = f"terms.yaml[{index}]"
        if term.license_ref in by_ref:
            raise EntryFileError(f"{where}: license_ref {term.license_ref} stands twice")
        by_ref[term.license_ref] = term
        for statement in term.matches:
            normal = normal_statement(statement)
            if normal in by_statement:
                raise EntryFileError(f"{where}: a statement of matches already means {by_statement[normal]}")
            by_statement[normal] = term.license_ref
    spellings = _read_spellings(directory / SPELLINGS_FILE, by_ref, by_statement)
    grants = _read_grants(directory / "grants", by_ref, known_sources)
    return LicenceCatalogue(
        terms=MappingProxyType(by_ref),
        by_statement=MappingProxyType(by_statement),
        grants=MappingProxyType({key: MappingProxyType(value) for key, value in grants.items()}),
        spellings=MappingProxyType(spellings),
    )

"""New spellings of a licence Otto graded (M5-67; docs/plans/m5/m5-67-harvest-automatisch.md §7; adr/0033 §8.5).

    python -m earthx.discovery.spellings --out backend/catalog/licenses

Licences are never graded automatically (Otto, 24.11.2026). A statement of a waiting find may become a further spelling
of a graded **standard licence** (granted to every publisher by ``grant-to-all.yaml`` and named by an SPDX identifier or
by the fixed address of its licensor) only where exactly one such licence fits by one of three rules:

- **S1 address:** equal to an address of the licence's ``matches`` after ``http``/``https``, ``www.``, the case of the
  host, a trailing ``/``, ``/legalcode``, ``/deed.<language>``, ``.html``, ``/index.html`` and a leading language part
  of the path; query and fragment stay (``#terms_by`` is the meaning at opendata.swiss).
- **S2 identifier:** a short text (at most 30 characters, 4 words) with a version number, equal to the SPDX identifier or
  to a short form of the vocabulary ``dcat-ap.de/def/licenses/`` (``dl-by-de/2.0``), without regard to case, blanks,
  ``-``, ``_``, ``/`` and ``.``.
- **S3 typography:** a text equal to one of the licence's ``matches`` after the case, the blanks, the quotation marks
  and the dashes are made the same.

Everything else waits and stands in the list of findings. The spellings go to ``licenses/spellings.yaml``, never into
Otto's ``terms.yaml``; ``withdrawn_on`` on a line takes the spelling back, and no later run adds it again.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import psycopg

from earthx.catalog.entry_files import EntryFileError, _validate, dump_yaml, read_yaml
from earthx.catalog.licences import (
    LICENSES_DIR,
    SPELLINGS_FILE,
    LicenceCatalogue,
    Spelling,
    is_standard_term,
    load_licences,
    normal_statement,
)
from earthx.catalog.registry import ConfigError
from earthx.catalog.sources import read_sources
from earthx.discovery.grants import read_grant_to_all
from earthx.logging import configure_logging

__all__ = [
    "Proposal",
    "dump_spellings",
    "merge_spellings",
    "propose",
    "standard_refs",
    "waiting_statements",
]

_URL = re.compile(r"(?i)(?:https?)://(?:www\.)?(?P<host>[^/?#\s]+)(?P<path>/[^?#\s]*)?(?P<query>\?[^#\s]*)?(?P<frag>#\S*)?")
_TAILS = re.compile(r"(?:/legalcode|/deed\.[a-z]{2}(?:-[a-z]{2})?|/index\.html?|\.html?)$", re.IGNORECASE)
_LANGUAGE = re.compile(r"^/(?:de|en|fr|it|rm)(?=/)", re.IGNORECASE)
_QUOTES = str.maketrans({c: '"' for c in "„“”‚‘’«»'"} | {c: "-" for c in "–—‑‐"})
_SEPARATORS = re.compile(r"[-_.\s/]")
_DCAT = "dcat-ap.de/def/licenses/"


def _url_key(text: str) -> str | None:
    match = _URL.fullmatch(text.strip())
    if match is None:
        return None
    path = (match["path"] or "").rstrip("/")
    path = _LANGUAGE.sub("", _TAILS.sub("", path)).rstrip("/")
    return f"{match['host'].lower()}{path.lower()}{match['query'] or ''}{(match['frag'] or '').lower()}"


def _id_key(text: str) -> str:
    return _SEPARATORS.sub("", text.lower())


def _text_key(text: str) -> str:
    return " ".join(text.translate(_QUOTES).casefold().split())


def standard_refs(catalogue: LicenceCatalogue, granted_to_all: Iterable[str]) -> frozenset[str]:
    """The licences a spelling may be added to: granted to every publisher, with an SPDX identifier (not a
    ``LicenseRef-``) or with the address of a licensor (``licences.LICENSOR_HOSTS``)."""
    terms = catalogue.terms
    return frozenset(ref for ref in granted_to_all if ref in terms and is_standard_term(terms[ref]))


@dataclass(frozen=True, slots=True)
class Proposal:
    license_ref: str
    statement: str
    rule: str


def _index(catalogue: LicenceCatalogue, standard: frozenset[str]) -> tuple[dict[str, set[str]], ...]:
    urls: dict[str, set[str]] = {}
    ids: dict[str, set[str]] = {}
    texts: dict[str, set[str]] = {}
    for ref in standard:
        term = catalogue.terms[ref]
        if term.license.spdx_id:
            ids.setdefault(_id_key(term.license.spdx_id), set()).add(ref)
        for match in term.matches:
            key = _url_key(match)
            if key is not None:
                urls.setdefault(key, set()).add(ref)
                if _DCAT in key and re.search(r"\d", key.split(_DCAT, 1)[1]):
                    ids.setdefault(_id_key(key.split(_DCAT, 1)[1]), set()).add(ref)
            else:
                texts.setdefault(_text_key(match), set()).add(ref)
    return urls, ids, texts


def propose(statements: Iterable[str], catalogue: LicenceCatalogue, standard: frozenset[str]) -> list[Proposal]:
    """The statements that are a new spelling of exactly one standard licence, with the rule that found it."""
    urls, ids, texts = _index(catalogue, standard)
    found = []
    for statement in sorted({normal_statement(s) for s in statements if normal_statement(s)}):
        if statement in catalogue.by_statement:
            continue
        url = _url_key(statement)
        if url is not None:
            rule, refs = "S1", urls.get(url, set())
        elif len(statement) <= 30 and len(statement.split()) <= 4 and any(c.isdigit() for c in statement):
            rule, refs = "S2", ids.get(_id_key(statement), set())
        else:
            rule, refs = "S3", texts.get(_text_key(statement), set())
        if len(refs) == 1:
            found.append(Proposal(next(iter(refs)), statement, rule))
    return found


def waiting_statements(conn: psycopg.Connection) -> Counter[str]:
    """The licence statements of extracted finds that the catalogue does not know, with how many finds name each."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT s, count(*) FROM public.earthx_record_state r,"
            " jsonb_array_elements_text(coalesce(r.extracted -> 'licence_statements', '[]'::jsonb)) s"
            " WHERE r.state = 'extracted' GROUP BY s"
        )
        return Counter({row[0]: row[1] for row in cur.fetchall()})


def merge_spellings(existing: Sequence[Spelling], proposals: Iterable[Proposal], day: date) -> list[Spelling]:
    """The lines kept as they are, withdrawn ones too, the new ones with ``day``; a statement of any existing line is
    never added again. Sorted by licence, then statement."""
    known = {normal_statement(s.statement) for s in existing}
    merged = list(existing)
    merged += [Spelling(p.license_ref, p.statement, p.rule, day) for p in proposals if p.statement not in known]
    return sorted(merged, key=lambda s: (s.license_ref, s.statement))


_HEADER = (
    "# Further spellings of graded standard licences, written by `discovery spellings` (M5-67 plan §7; adr/0033\n"
    "# §8.5): never a grade, only a statement that means exactly one licence of terms.yaml by rule S1 (address),\n"
    "# S2 (identifier) or S3 (typography). To take a spelling back, set `withdrawn_on: <day>` on its line (deleting\n"
    "# the line would let the next run add it again); the finds then wait again.\n"
)


def dump_spellings(spellings: Sequence[Spelling]) -> str:
    rows = [
        {"license_ref": s.license_ref, "statement": s.statement, "rule": s.rule, "added_on": s.added_on}
        | ({} if s.withdrawn_on is None else {"withdrawn_on": s.withdrawn_on})
        for s in spellings
    ]
    return _HEADER + (dump_yaml(rows, width=1000) if rows else "[]\n")


def _existing(path: Path) -> list[Spelling]:
    """The lines already there; ``load_licences`` has checked them."""
    data = read_yaml(path) if path.exists() else None
    return [_validate(Spelling, item, f"{path.name}[{i}]") for i, item in enumerate(data or [])]


def run(conn: psycopg.Connection, catalogue_dir: Path, out: Path, day: date) -> tuple[list[Proposal], Counter[str]]:
    """Write ``out/spellings.yaml`` with the new spellings; returns them and the statements that still wait."""
    catalogue = load_licences(read_sources(), catalogue_dir)
    granted = read_grant_to_all(catalogue.terms, catalogue_dir / "grant-to-all.yaml").licenses
    standard = standard_refs(catalogue, granted)
    known = catalogue.by_statement
    waiting = Counter(
        {
            s: n
            for s, n in waiting_statements(conn).items()
            if normal_statement(s) not in known and not catalogue.is_not_a_licence(normal_statement(s))
        }
    )
    # What is merged is what is written: the file of `out` (a mount of the checkout), not the copy in the image.
    existing = _existing(out / SPELLINGS_FILE)
    withdrawn = {normal_statement(s.statement) for s in existing if s.withdrawn_on is not None}
    proposals = [p for p in propose(waiting, catalogue, standard) if p.statement not in withdrawn]
    merged = merge_spellings(existing, proposals, day)
    out.mkdir(parents=True, exist_ok=True)
    (out / SPELLINGS_FILE).write_text(dump_spellings(merged), encoding="utf-8")
    taken = {p.statement for p in proposals}
    return proposals, Counter({s: n for s, n in waiting.items() if normal_statement(s) not in taken})


def summary_text(proposals: Sequence[Proposal], waiting: Mapping[str, int], top: int = 20) -> str:
    lines = [f"Schreibweisen: {len(proposals)} neu zugeordnet, {len(waiting)} Angaben warten"]
    lines += [f"  {p.rule} {p.license_ref}: {p.statement[:160]}" for p in proposals]
    lines.append(f"  Wartend (häufigste {top}):")
    lines += [f"  {n:>7}  {s[:160]}" for s, n in Counter(waiting).most_common(top)]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m earthx.discovery.spellings", description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=LICENSES_DIR, help="where spellings.yaml goes")
    parser.add_argument("--json", type=Path, default=None, help="also write what was added and what waits as JSON")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    configure_logging()
    try:
        with psycopg.connect(autocommit=True) as conn:
            proposals, waiting = run(conn, LICENSES_DIR, args.out, date.today())
    except (EntryFileError, ConfigError) as error:
        print(f"spellings failed: {error}", file=sys.stderr)
        return 1
    except psycopg.Error as error:
        print(f"spellings failed: database error {type(error).__name__}", file=sys.stderr)
        return 1
    if args.json is not None:
        numbers = {
            "added": [{"license_ref": p.license_ref, "statement": p.statement, "rule": p.rule} for p in proposals],
            "waiting": [[statement, count] for statement, count in Counter(waiting).most_common(30)],
        }
        args.json.write_text(json.dumps(numbers, ensure_ascii=False), encoding="utf-8")
    print(summary_text(proposals, waiting))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

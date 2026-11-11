"""The glossary of the dataset search and how it splits a query (adr/0026 §4.2; M5-22 plan §3.3).

``backend/catalog/glossary.yaml`` lists groups of terms that mean the same, German and English. :func:`parse_query`
cuts a query into units from left to right, each the longest glossary term that fits or else one word; a glossary
unit stands for every term of its group. Only the query is expanded: the search texts stay as they are, so a change
of the glossary needs no new index.

:func:`normalize` is the one comparison of terms here: lower case, without accents (``ß`` as ``ss``, as ``unaccent``
does), every character that is no letter or digit a space. A hyphen therefore matches a space: "Sentinel 2" finds the
group of "Sentinel-2".
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import earthx
from earthx.catalog.entry_files import EntryFileError, read_yaml
from earthx.catalog.registry import ConfigError

GLOSSARY_FILE = Path(earthx.__file__).resolve().parents[1] / "catalog" / "glossary.yaml"

_NOT_A_WORD = re.compile(r"[\W_]+")
#: Characters that separate the chunks of a query; a hyphen stays inside a chunk ("sentinel-2").
_BETWEEN_CHUNKS = re.compile(r"[^\w-]+|_+")
_FOLDED = str.maketrans({"ß": "ss", "æ": "ae", "œ": "oe", "ø": "o", "ð": "d", "þ": "th", "ł": "l"})


def normalize(text: str) -> str:
    """Lower case, without accents, every run of characters that is no letter or digit one space."""
    decomposed = unicodedata.normalize("NFKD", text.lower().translate(_FOLDED))
    bare = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _NOT_A_WORD.sub(" ", bare).strip()


@dataclass(frozen=True, slots=True)
class Glossary:
    #: The groups as written in the file.
    groups: tuple[tuple[str, ...], ...]
    #: Each term as words after :func:`normalize`, to the index of its group.
    index: Mapping[tuple[str, ...], int]

    @property
    def longest(self) -> int:
        """The most words of any term."""
        return max((len(words) for words in self.index), default=0)


def load_glossary(path: Path = GLOSSARY_FILE) -> Glossary:
    """The glossary in ``path``, checked; :class:`ConfigError` names the file, the group and what is wrong."""
    try:
        data = read_yaml(path)
    except EntryFileError as error:
        raise ConfigError(str(error)) from None
    if not isinstance(data, dict) or set(data) != {"groups"}:
        raise ConfigError(f"{path.name}: has exactly the key 'groups'")
    if not isinstance(data["groups"], list) or not data["groups"]:
        raise ConfigError(f"{path.name}: 'groups' is a non-empty list")
    groups: list[tuple[str, ...]] = []
    index: dict[tuple[str, ...], int] = {}
    for number, group in enumerate(data["groups"], start=1):
        where = f"{path.name}, group {number}"
        if not isinstance(group, list) or len(group) < 2:
            raise ConfigError(f"{where}: a group is a list of at least two terms")
        for term in group:
            if not isinstance(term, str) or not normalize(term):
                raise ConfigError(f"{where}: {term!r} is no term (a text with a letter or digit)")
            words = tuple(normalize(term).split())
            if words in index:
                other = index[words] + 1
                raise ConfigError(
                    f"{where}: {term!r} is "
                    + ("given twice" if other == number else f"in group {other} as well")
                    + " (compared in lower case, without accents)"
                )
            index[words] = number - 1
        groups.append(tuple(group))
    return Glossary(tuple(groups), index)


@cache
def glossary() -> Glossary:
    """The glossary of this process, read once."""
    return load_glossary()


@dataclass(frozen=True, slots=True)
class Unit:
    """One part of a query: a word as typed (normalized), or the terms of a glossary group."""

    terms: tuple[str, ...]
    from_glossary: bool


def parse_query(text: str, known: Glossary | None = None) -> tuple[Unit, ...]:
    """The units of ``text``, left to right, each the longest glossary term that fits or else one chunk of words.

    A chunk is what stands between spaces and punctuation, hyphens kept ("sentinel-2"); words of a chunk that no
    glossary term takes stay together, joined by a hyphen again.
    """
    known = glossary() if known is None else known
    words: list[str] = []
    chunk_of: list[int] = []
    for number, chunk in enumerate(_BETWEEN_CHUNKS.split(text)):
        for word in normalize(chunk).split():
            words.append(word)
            chunk_of.append(number)
    units: list[Unit] = []
    loose: list[str] = []

    def flush() -> None:
        if loose:
            units.append(Unit(("-".join(loose),), from_glossary=False))
            loose.clear()

    position = 0
    while position < len(words):
        for length in range(min(known.longest, len(words) - position), 0, -1):
            group = known.index.get(tuple(words[position : position + length]))
            if group is not None:
                flush()
                units.append(Unit(known.groups[group], from_glossary=True))
                position += length
                break
        else:
            if loose and chunk_of[position] != chunk_of[position - 1]:
                flush()
            loose.append(words[position])
            position += 1
    flush()
    # A group or word given twice ("digital terrain model bare earth") is one condition, not two.
    return tuple(dict.fromkeys(units))

"""``citation.bib`` of the synchronous crop (adr/0014 §10.2, M4-14).

One ``@misc`` entry for the dataset, from registry fields only: `api` builds the
file and hands it to `access.download` as bytes, as it does ``recipe.json``.
Author and year of publication are not in the registry; the entry says what it
has rather than guessing them.
"""

from __future__ import annotations

import re
from datetime import date

from earthx.access.download import attribution_text
from earthx.catalog.registry import DatasetConfig, doi_name

__all__ = ["citation_bib"]

_KEY_UNSAFE = re.compile(r"[^A-Za-z0-9_.:-]")
# What BibTeX or LaTeX would act on inside a braced value. The `doi` and `url`
# fields stay as they are: LaTeX's `url` handles them, and `doi_name` has already
# refused braces and blanks.
_ESCAPES = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "&": r"\&",
    "%": r"\%",
    "#": r"\#",
    "_": r"\_",
    "$": r"\$",
}


def _escaped(text: str) -> str:
    return "".join(_ESCAPES.get(char, char) for char in " ".join(text.split()))


def citation_bib(config: DatasetConfig, *, downloaded: date) -> bytes:
    """The ``@misc`` entry of ``config``, UTF-8, with ``downloaded`` as its ``urldate``.

    ``note`` is the attribution a crop carries (the one in ``ATTRIBUTION.txt``),
    followed by the registry's ``citation`` where the dataset has one: with a DOI
    the citation is extra, without one it is the persistent citation the
    onboarding checklist asks for (point 3), and must not be lost.
    """
    fields = [("title", _escaped(config.title))]
    name = doi_name(config.doi)
    if name:
        fields.append(("doi", name))
        fields.append(("url", f"https://doi.org/{name}"))
    notes = [attribution_text(config, year=downloaded.year), config.citation]
    note = " ".join(_escaped(text) for text in notes if text)
    if note:
        fields.append(("note", note))
    fields.append(("urldate", downloaded.isoformat()))

    width = max(len(key) for key, _ in fields)
    body = ",\n".join(f"  {key.ljust(width)} = {{{value}}}" for key, value in fields)
    key = _KEY_UNSAFE.sub("_", config.dataset_id)
    return f"@misc{{{key},\n{body}\n}}\n".encode("utf-8")

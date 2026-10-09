"""M3-12: the frontend knows no dataset and no source-specific property (P10).

M3-02's own report (`plans/m3-02-konformitaetsbericht.md` §5) found the frontend
free of a dataset id in a branch already — the ids only ever showed up in comments
— but the constants `DATATAKE_PROPERTY = 's2:datatake_id'` (`grouping.ts`) and
`NODATA_THRESHOLD` (`mapLayers.ts`) were literal, source-specific knowledge M3-12
moves into the registry (`earthx:viewer.results_group_by`/`quicklook_nodata_max`).
This is the test that report proposed (§5.3): a static sweep of `frontend/src`,
outside `*.test.*` files and outside comments/strings, for (a) a `dataset_id` this
backend's own registry knows and (b) a property name carrying the prefix of a STAC
extension one source uses (`s2:`, `eo:`, `sat:`, `grid:`, `mgrs:`, `landsat:`,
`eopf:`). `proj:` stays allowed — the projection extension is source-independent,
and `geoUtils.ts` needs it (M3-02 §5.3).

Comments are blanked (not deleted, so a match still names the right line) before
either check runs — a forbidden literal is exactly the kind of thing that sits
inside a string (`'s2:datatake_id'`), so string contents are read as they stand;
only comments are removed, and removing them correctly needs a tokenizer that
recognises a string's own quotes, so a `//` inside a quoted URL is never mistaken
for the start of a comment.

A fourth dataset added to the registry needs no change here: both lists are read
from the registry itself, never hand-maintained.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from earthx.catalog.datasets import REGISTRY
from earthx.catalog.registry import MAX_TILE_ZOOM

REPO = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO / "frontend" / "src"

DATASET_IDS = tuple(sorted(entry.dataset_id for entry in REGISTRY))

# `proj:` is deliberately not here (M3-02 §5.3, F-03/geoUtils.ts).
FORBIDDEN_PROPERTY_PREFIXES = ("s2:", "eo:", "sat:", "grid:", "mgrs:", "landsat:", "eopf:")
PROPERTY_PATTERN = re.compile("(" + "|".join(re.escape(p) for p in FORBIDDEN_PROPERTY_PREFIXES) + r")[A-Za-z_]")


def _blanked(source: str) -> str:
    """``source`` with every comment replaced by spaces of the same length
    (newlines kept, so a failure can still point at a line) and every string or
    template literal copied through unchanged — a forbidden literal is exactly
    the kind of thing that sits inside a string (``'s2:datatake_id'``), so a
    string's *content* is what this test has to see. What it must not see is a
    ``//`` sitting inside a quoted URL and being mistaken for a comment: a
    string is therefore recognised (and skipped over whole, quotes included)
    before either comment form is. Not a real TypeScript tokenizer — nested
    ``${...}`` expressions inside a template literal are not re-entered — but
    good enough for source nobody is trying to hide a literal in.
    """
    out: list[str] = []
    i, n = 0, len(source)
    while i < n:
        two = source[i : i + 2]
        ch = source[i]
        if ch in "'\"`":
            j = i + 1
            while j < n and source[j] != ch:
                j += 2 if source[j] == "\\" else 1
            j = min(j + 1, n)
            out.append(source[i:j])
            i = j
        elif two == "//":
            end = source.find("\n", i)
            end = n if end == -1 else end
            out.append(re.sub(r"[^\n]", " ", source[i:end]))
            i = end
        elif two == "/*":
            end = source.find("*/", i + 2)
            end = n if end == -1 else end + 2
            out.append(re.sub(r"[^\n]", " ", source[i:end]))
            i = end
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def frontend_source_files() -> list[Path]:
    return sorted(
        path
        for path in FRONTEND_SRC.rglob("*.ts*")
        if path.suffix in (".ts", ".tsx") and ".test." not in path.name
    )


FILES = frontend_source_files()


def test_there_is_something_to_check() -> None:
    """A crawl that silently found nothing would pass for the wrong reason."""
    assert len(FILES) > 10


@pytest.mark.parametrize("path", FILES, ids=lambda path: str(path.relative_to(FRONTEND_SRC)))
def test_no_dataset_id_literal_outside_a_comment(path: Path) -> None:
    code = _blanked(path.read_text(encoding="utf-8"))
    found = [dataset_id for dataset_id in DATASET_IDS if dataset_id in code]
    assert not found, (
        f"{path.relative_to(FRONTEND_SRC)} names dataset id(s) {found} in code — "
        "the frontend must not branch on a dataset (P10, M3-Abnahme)"
    )


@pytest.mark.parametrize("path", FILES, ids=lambda path: str(path.relative_to(FRONTEND_SRC)))
def test_no_source_specific_property_prefix_outside_a_comment(path: Path) -> None:
    code = _blanked(path.read_text(encoding="utf-8"))
    matches = sorted(set(PROPERTY_PATTERN.findall(code)))
    assert not matches, (
        f"{path.relative_to(FRONTEND_SRC)} spells out a source-specific property "
        f"prefix {matches} in code — read it from the registry "
        "(`earthx:viewer.results_group_by` or similar), not hardcoded (M3-12)"
    )


def test_the_dataset_id_check_would_notice_one_outside_a_comment() -> None:
    code = _blanked("const x = 'sentinel-2-c1-l2a';\n")
    assert any(dataset_id in code for dataset_id in DATASET_IDS)


def test_the_dataset_id_check_ignores_a_comment() -> None:
    code = _blanked("// mentions sentinel-2-c1-l2a only here, in a comment\nconst x = 1;\n")
    assert not any(dataset_id in code for dataset_id in DATASET_IDS)


def test_the_property_prefix_check_would_notice_one() -> None:
    assert PROPERTY_PATTERN.findall(_blanked("const k = 's2:datatake_id';\n"))


def test_the_property_prefix_check_allows_the_projection_extension() -> None:
    """`proj:` names no source, and `geoUtils.ts` reads it (M3-02 §5.3)."""
    assert not PROPERTY_PATTERN.findall(_blanked("const k = properties['proj:code'];\n"))


def test_a_url_in_an_earlier_string_does_not_hide_a_later_violation() -> None:
    """The `//` inside `https://...` must not be mistaken for a comment marker —
    that would blank the rest of the line, and with it the real violation."""
    code = _blanked("const href = 'https://example.test/x'; const id = 'sentinel-2-c1-l2a';\n")
    assert "sentinel-2-c1-l2a" in code


def test_a_dataset_id_after_a_real_comment_marker_is_hidden() -> None:
    """The mirror case: once an actual `//` starts, everything after it is a
    comment, URL-shaped or not."""
    code = _blanked("const x = 1; // see sentinel-2-c1-l2a\n")
    assert "sentinel-2-c1-l2a" not in code


def test_max_tile_zoom_matches_the_registrys_own_ceiling() -> None:
    """F-12: `datasets.ts` spiegelt `catalog.registry.MAX_TILE_ZOOM` — a value
    the backend would refuse must not look viewable on the client either."""
    source = (FRONTEND_SRC / "datasets.ts").read_text(encoding="utf-8")
    match = re.search(r"MAX_TILE_ZOOM\s*=\s*(\d+)", source)
    assert match, "frontend/src/datasets.ts no longer defines MAX_TILE_ZOOM the way this test expects"
    assert int(match.group(1)) == MAX_TILE_ZOOM

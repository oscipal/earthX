"""The onboarding checklist of projektuebersicht.md §5, as a test over every registry entry.

The checklist is an *admission rule of the project*, not a runtime property of the
platform: no route serves it and no ``earthx:`` field carries it. It therefore lives
here rather than in ``earthx/catalog/`` — architekturplan.md 5.1 stays as it is.

The wordings that apply to the last two points:

* point 9, version v1 (D4, 20.09.2026): the chain search → display → clipped
  download, against fixtures;
* point 10, version v1.1 (Otto, 22.09.2026, narrowing D4): the dataset is
  covered by the T-D smoke. A visible check date waits for M5's own health
  checks, because none of the ways to carry the last green run's timestamp into
  the running platform worked without a secret or recurring manual work.

Point 9 needs a running chain rather than a look at the entry, so it lives in
``test_onboarding_endtoend.py``. Point 10 needs a look at a different directory
rather than at the entry: whether ``backend/tests_live/`` carries a module marked
``@pytest.mark.live_dataset(<its id>)`` for it (Fassung v1.1, Otto 22.09.2026,
M2-08 plan §4.4). Both live in :data:`CHECKED_ELSEWHERE`, which says where.
``test_every_point_is_accounted_for`` makes a forgotten point a failure rather
than a silent gap.

Two kinds of failure, and the difference is deliberate:

* Where ``DatasetConfig.__post_init__`` already refuses a broken entry, the
  checklist point is structurally enforced and the negative case below expects a
  ``ConfigError`` at construction. The checklist does not repeat the check; it
  pins that the guard exists.
* Where the dataclass admits an entry the checklist would not, :func:`evaluate`
  returns a :class:`Finding` and the negative case expects exactly that one.
"""

from __future__ import annotations

import ast
import functools
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path

import pytest

from earthx.api.coverage_route import IMPLEMENTED_PROVIDERS
from earthx.catalog.coverage import Completeness, check_completeness
from earthx.catalog.datasets import REGISTRY
from earthx.catalog.registry import (
    ConfigError,
    CoverageProvider,
    DataClass,
    DataFormat,
    DatasetConfig,
    LicenseTier,
)

# The wording of projektuebersicht.md §5, shortened only where the document repeats
# itself. A failure quotes the rule rather than the field, so it reads as the
# checklist and not as a schema violation.
CHECKLIST = {
    1: "Beschreibung vorhanden.",
    2: "Ein Coverage-Anbieter ist zugeordnet und die Vollstaendigkeitsprobe greift.",
    3: "DOI verlinkt, wo vorhanden; sonst persistente Zitierangabe.",
    4: "Lizenz geprueft und als Feld mit Flags erfasst.",
    5: "Cloud-natives Format bevorzugt (Zarr > COG > Legacy).",
    6: "Anonymer Zugriffs-Check bestanden.",
    7: "Datentyp-Klasse und Capability-Flags gesetzt.",
    8: "Standard-Visualisierung definiert (Baender, Stretch, Colormap).",
    9: "Mindestens ein Processing-Schritt End-to-End getestet; Fassung v1: Suche -> Anzeige -> Zuschnitt-Download.",
    10: "'Zuletzt erfolgreich geprueft' ist gesetzt und sichtbar; Fassung v1.1: vom T-D-Smoke abgedeckt.",
}

# Points that are checked, but not by looking at the entry.
CHECKED_ELSEWHERE = {
    9: "tests.catalog.test_onboarding_endtoend",
    10: "test_every_registry_entry_is_covered_by_the_live_smoke, below — the "
    "live_dataset marker in backend/tests_live/",
}

# Points nothing answers yet, with the PR that closes them.
NOT_YET_CHECKED: dict[int, str] = {}


# --------------------------------------------------------------------------------
# Point 10: covered by the T-D smoke, read off the live_dataset marker.
# --------------------------------------------------------------------------------

# backend/tests/catalog/test_onboarding_checklist.py -> parents[2] == backend/
_TESTS_LIVE_DIR = Path(__file__).resolve().parents[2] / "tests_live"


def _live_dataset_marks(module: ast.Module) -> Iterator[str]:
    """The dataset ids named in this module's ``pytestmark``, if any.

    Reads the source rather than importing the module: tests_live modules open a
    ``Gateway`` fixture and expect the network guard of ``backend/tests/conftest.py``
    to be absent, neither of which this checklist test wants to disturb just to see
    which dataset a module claims to cover.
    """
    for node in ast.walk(module):
        if not (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets)):
            continue
        marks = node.value.elts if isinstance(node.value, ast.List) else [node.value]
        for mark in marks:
            if (
                isinstance(mark, ast.Call)
                and isinstance(mark.func, ast.Attribute)
                and mark.func.attr == "live_dataset"
                and mark.args
                and isinstance(mark.args[0], ast.Constant)
                and isinstance(mark.args[0].value, str)
            ):
                yield mark.args[0].value


@functools.lru_cache(maxsize=1)
def _live_smoke_dataset_ids() -> frozenset[str]:
    """Every dataset id any ``backend/tests_live`` module claims to cover."""
    ids: set[str] = set()
    for path in sorted(_TESTS_LIVE_DIR.glob("test_*.py")):
        ids.update(_live_dataset_marks(ast.parse(path.read_text(), filename=str(path))))
    return frozenset(ids)


def _missing_live_smoke_coverage(dataset_ids: Iterable[str], covered: frozenset[str]) -> list[str]:
    return [dataset_id for dataset_id in dataset_ids if dataset_id not in covered]


@dataclass(frozen=True)
class Finding:
    """One checklist point an entry does not meet."""

    point: int
    detail: str

    def __str__(self) -> str:
        return f"point {self.point} — {CHECKLIST[self.point]} ({self.detail})"


def _point_1_description(config: DatasetConfig) -> Finding | None:
    if not config.description.strip():
        return Finding(1, "description is empty")
    if config.description.strip() == config.title.strip():
        return Finding(1, "description only repeats the title")
    return None


def _point_2_coverage(config: DatasetConfig) -> Finding | None:
    """Assigned *and* answered, and the completeness probe reaches its marker.

    The second half is what D4 added to the point. A provider whose path can never
    say ``complete`` — or a declared sample that stops declaring itself — would
    leave the map claiming more than it knows (adr/0004 §5, rule V).
    """
    provider = config.coverage.provider
    if config.capabilities.single_coverage_product:
        # A one-off product answers with its extent; there is no density to probe
        # (adr/0004 §5). The entry guard already forbids the nonsensical pairing.
        return None
    if provider not in IMPLEMENTED_PROVIDERS:
        return Finding(2, f"nothing answers coverage for provider {provider.value!r}")
    if provider is CoverageProvider.SAMPLE:
        reached = check_completeness(counted=5, total_count=None, sampled=True)
        expected = Completeness.SAMPLE
    else:
        reached = check_completeness(counted=5, total_count=5)
        expected = Completeness.COMPLETE
    if reached is not expected:
        return Finding(2, f"provider {provider.value!r} cannot reach {expected.value!r}, it reaches {reached.value!r}")
    return None


def _point_3_citation(config: DatasetConfig) -> Finding | None:
    if (config.doi or "").strip():
        return None
    if (config.citation or "").strip():
        return None
    return Finding(3, "neither a DOI nor a persistent citation")


def _point_4_license(config: DatasetConfig) -> Finding | None:
    """What the entry guard leaves open: the terms a download has to pass on.

    Identifiability and the tier rule (KLAERUNGEN B11) are enforced at construction.
    What is not: a licence without an SPDX identifier is a text someone read once,
    and above tier ``catalog`` the platform hands that text to the user with every
    clipped download (adr/0003 §11.2, M2-06). Without it the download would ship
    data and no terms.
    """
    if config.license.spdx_id:
        return None
    if config.license.tier is LicenseTier.CATALOG:
        return None
    if config.license.terms is None:
        return Finding(4, "a non-SPDX licence above tier 'catalog' records no terms to pass on at download")
    return None


def _point_5_format(config: DatasetConfig) -> Finding | None:
    if config.format is DataFormat.LEGACY:
        return Finding(5, "legacy format, and no virtual store makes it cloud-native yet")
    return None


def _point_6_access(config: DatasetConfig, today: date) -> Finding | None:
    """The check happened, and it happened in the past.

    The date is mandatory on the entry, so its presence is not the question. A date
    in the future is: it would be a plan rather than a check.
    """
    if config.access.token_free_checked_at > today:
        return Finding(6, f"the anonymous access check is dated {config.access.token_free_checked_at}, in the future")
    return None


def _point_7_class_and_flags(config: DatasetConfig) -> Finding | None:
    """All seven flags are mandatory (KLAERUNGEN B10); what is left is coherence.

    A time series is a stream of acquisitions, so it is not a single coverage. The
    pair would send the coverage path down the extent branch for a dataset whose
    whole point is its density.
    """
    if config.capabilities.single_coverage_product and config.data_class is DataClass.RASTER_TIME_SERIES:
        return Finding(7, "single_coverage_product=True on a raster time series")
    return None


def _point_8_default_render(config: DatasetConfig) -> Finding | None:
    if config.default_render is None:
        return Finding(8, "no standard visualisation")
    return None


def evaluate(config: DatasetConfig, *, today: date | None = None) -> list[Finding]:
    """Every checklist point this module answers, in order. Empty means it passes."""
    reference = today if today is not None else date.today()
    candidates = (
        _point_1_description(config),
        _point_2_coverage(config),
        _point_3_citation(config),
        _point_4_license(config),
        _point_5_format(config),
        _point_6_access(config, reference),
        _point_7_class_and_flags(config),
        _point_8_default_render(config),
    )
    return [finding for finding in candidates if finding is not None]


# --------------------------------------------------------------------------------
# The registry, entry by entry.
# --------------------------------------------------------------------------------

ENTRIES = list(REGISTRY)
ENTRY_IDS = [config.dataset_id for config in ENTRIES]


@pytest.mark.parametrize("config", ENTRIES, ids=ENTRY_IDS)
def test_every_registry_entry_passes_the_checklist(config: DatasetConfig) -> None:
    findings = evaluate(config)
    assert not findings, "\n".join(str(finding) for finding in findings)


def test_sentinel_2_carries_the_doi_of_its_collection() -> None:
    """Point 3 for the first dataset, closed from the source's own `cite-as` link.

    Pinned as a value rather than left to the point-3 check alone: a citation that
    quietly changed would still satisfy "a DOI is present" while pointing somewhere
    else (M2-08 plan §3, read 22.09.2026).
    """
    config = REGISTRY.get("sentinel-2-c1-l2a")
    assert config.doi == "https://doi.org/10.5270/S2_-742ikth"
    assert config.citation is None


def test_the_two_datasets_cite_different_products() -> None:
    """The COG and the Zarr entry are two distributions, and two DOIs say so."""
    cog = REGISTRY.get("sentinel-2-c1-l2a")
    zarr = REGISTRY.get("sentinel-2-l2a-zarr3")
    assert cog.doi != zarr.doi


def test_every_registry_entry_is_covered_by_the_live_smoke() -> None:
    """Point 10, Fassung v1.1: every entry needs a tests_live module marked for it.

    Not a date (M2-08 plan §4.4: no way to carry the last green run's timestamp into
    the running platform came without a secret or recurring manual work) — just
    whether ``backend/tests_live/`` still names the entry at all.
    """
    missing = _missing_live_smoke_coverage((config.dataset_id for config in REGISTRY), _live_smoke_dataset_ids())
    assert not missing, f"no tests_live module marked live_dataset for: {missing}"


def test_an_uncovered_dataset_id_is_reported_missing() -> None:
    """The negative case point 10 would otherwise have no test for.

    A real registry entry never lacks coverage right now (the test above pins
    that), so this checks the reporting function itself against a made-up id
    instead of trying to construct a genuinely uncovered entry.
    """
    covered = _live_smoke_dataset_ids()
    assert "ghost-dataset" not in covered, "test id collides with a real live_dataset mark"
    assert _missing_live_smoke_coverage(["ghost-dataset", *covered], covered) == ["ghost-dataset"]


def test_live_dataset_marks_are_found_in_both_pytestmark_forms(tmp_path) -> None:
    """The scanner reads a single mark and a list of marks alike.

    ``tests_live`` writes both: earth-search's two files each carry
    ``[pytest.mark.anyio, pytest.mark.live_dataset(...)]``, a plain
    ``pytest.mark.live_dataset(...)`` alone would be just as valid pytest.
    """
    single = tmp_path / "test_single.py"
    single.write_text('import pytest\n\npytestmark = pytest.mark.live_dataset("solo-dataset")\n')
    grouped = tmp_path / "test_grouped.py"
    grouped.write_text(
        'import pytest\n\npytestmark = [pytest.mark.anyio, pytest.mark.live_dataset("grouped-dataset")]\n'
    )
    unrelated = tmp_path / "test_unrelated.py"
    unrelated.write_text('import pytest\n\npytestmark = pytest.mark.anyio\n')

    found = {
        path.name: set(_live_dataset_marks(ast.parse(path.read_text(), filename=str(path))))
        for path in (single, grouped, unrelated)
    }
    assert found == {
        "test_single.py": {"solo-dataset"},
        "test_grouped.py": {"grouped-dataset"},
        "test_unrelated.py": set(),
    }


def test_every_point_is_accounted_for() -> None:
    """Each of the ten points is answered here, answered elsewhere, or named open.

    Deleting an entry from ``NOT_YET_CHECKED`` without wiring the point in fails
    here, and wiring one in without deleting its entry does too.
    """
    answered_here = {1, 2, 3, 4, 5, 6, 7, 8}
    elsewhere = set(CHECKED_ELSEWHERE)
    open_points = set(NOT_YET_CHECKED)

    assert answered_here | elsewhere | open_points == set(CHECKLIST)
    assert len(answered_here) + len(elsewhere) + len(open_points) == len(CHECKLIST)


# --------------------------------------------------------------------------------
# A missing point drops the entry. One case per point, each changing one thing.
# --------------------------------------------------------------------------------


def test_point_1_falls_for_an_empty_description(vary) -> None:
    assert evaluate(vary(description="   ")) == [Finding(1, "description is empty")]


def test_point_1_falls_when_the_description_only_repeats_the_title(vary) -> None:
    assert evaluate(vary(title="Test dataset", description="Test dataset")) == [
        Finding(1, "description only repeats the title")
    ]


def test_point_2_falls_for_a_provider_nothing_answers(vary, valid_config) -> None:
    coverage = replace(valid_config.coverage, provider=CoverageProvider.LOCAL_SQL)
    findings = evaluate(vary(coverage=coverage))
    assert findings == [Finding(2, "nothing answers coverage for provider 'local-sql'")]


def test_point_2_falls_when_rule_v_stops_declaring_a_sample(vary, valid_config, monkeypatch) -> None:
    """Rule V is the probe. If a declared sample stopped saying so, point 2 falls.

    Patched at the module under test rather than at its source, because that is the
    reference the checklist holds the entry against.
    """
    monkeypatch.setattr(
        "tests.catalog.test_onboarding_checklist.check_completeness",
        lambda **kwargs: Completeness.COMPLETE,
    )
    coverage = replace(valid_config.coverage, provider=CoverageProvider.SAMPLE)
    findings = evaluate(vary(coverage=coverage))
    assert findings == [Finding(2, "provider 'sample' cannot reach 'sample', it reaches 'complete'")]


def test_point_3_falls_without_a_doi_and_without_a_citation(vary) -> None:
    assert evaluate(vary(doi=None, citation=None)) == [Finding(3, "neither a DOI nor a persistent citation")]


def test_point_3_accepts_a_citation_instead_of_a_doi(vary) -> None:
    assert evaluate(vary(doi=None, citation="Test publisher (2026): Test dataset, version 1.")) == []


def test_point_3_does_not_accept_whitespace(vary) -> None:
    assert evaluate(vary(doi="   ", citation="")) == [Finding(3, "neither a DOI nor a persistent citation")]


def test_point_4_falls_when_a_non_spdx_licence_records_no_terms(vary, valid_config) -> None:
    license_info = replace(valid_config.license, spdx_id=None, terms=None)
    findings = evaluate(vary(license=license_info))
    assert findings == [
        Finding(4, "a non-SPDX licence above tier 'catalog' records no terms to pass on at download")
    ]


def test_point_4_is_structurally_enforced_for_the_tier_rule(vary, valid_config) -> None:
    """KLAERUNGEN B11 never reaches :func:`evaluate` — the entry refuses to exist."""
    license_info = replace(valid_config.license, derivatives=False, tier=LicenseTier.PROCESSING)
    with pytest.raises(ConfigError, match="derivatives"):
        vary(license=license_info)


def test_point_4_is_structurally_enforced_for_identifiability(vary, valid_config) -> None:
    license_info = replace(valid_config.license, spdx_id=None, name="", url="")
    with pytest.raises(ConfigError, match="SPDX"):
        vary(license=license_info)


def test_point_5_falls_for_a_legacy_format(vary) -> None:
    findings = evaluate(vary(format=DataFormat.LEGACY))
    assert findings == [Finding(5, "legacy format, and no virtual store makes it cloud-native yet")]


def test_point_6_falls_for_a_check_dated_in_the_future(vary, valid_config) -> None:
    today = date(2026, 9, 22)
    access = replace(valid_config.access, token_free_checked_at=today + timedelta(days=1))
    findings = evaluate(vary(access=access), today=today)
    assert findings == [Finding(6, "the anonymous access check is dated 2026-09-23, in the future")]


def test_point_6_accepts_a_check_dated_today(vary, valid_config) -> None:
    today = date(2026, 9, 22)
    access = replace(valid_config.access, token_free_checked_at=today)
    assert evaluate(vary(access=access), today=today) == []


def test_point_7_falls_for_a_one_off_time_series(vary, valid_config) -> None:
    capabilities = replace(valid_config.capabilities, single_coverage_product=True)
    coverage = replace(valid_config.coverage, provider=CoverageProvider.SAMPLE)
    findings = evaluate(vary(capabilities=capabilities, coverage=coverage))
    assert findings == [Finding(7, "single_coverage_product=True on a raster time series")]


def test_point_7_is_structurally_enforced_against_upstream_aggregation(vary, valid_config) -> None:
    """A one-off product paired with upstream aggregation never gets built."""
    capabilities = replace(valid_config.capabilities, single_coverage_product=True)
    with pytest.raises(ConfigError, match="extent, not a density"):
        vary(capabilities=capabilities)


def test_point_8_falls_without_a_standard_visualisation(vary) -> None:
    assert evaluate(vary(default_render=None)) == [Finding(8, "no standard visualisation")]


def test_several_missing_points_are_all_reported(vary) -> None:
    """The checklist is not a fail-fast: an entry learns everything it is missing."""
    findings = evaluate(vary(description="", doi=None, citation=None, default_render=None))
    assert [finding.point for finding in findings] == [1, 3, 8]


def test_a_finding_reads_as_the_checklist_rule(vary) -> None:
    (finding,) = evaluate(vary(default_render=None))
    assert str(finding) == (
        "point 8 — Standard-Visualisierung definiert (Baender, Stretch, Colormap). "
        "(no standard visualisation)"
    )

"""``doi_name``: the registry keeps the resolver URL, STAC and BibTeX want the name (adr/0014 §10.2)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from earthx.catalog.datasets import REGISTRY
from earthx.catalog.registry import ConfigError, doi_name


@pytest.mark.parametrize(
    "written",
    [
        "https://doi.org/10.5270/S2_-742ikth",
        "http://doi.org/10.5270/S2_-742ikth",
        "https://dx.doi.org/10.5270/S2_-742ikth",
        "HTTPS://DOI.ORG/10.5270/S2_-742ikth",
        "doi:10.5270/S2_-742ikth",
        "10.5270/S2_-742ikth",
        "  https://doi.org/10.5270/S2_-742ikth \n",
    ],
)
def test_every_spelling_gives_the_same_name(written: str) -> None:
    assert doi_name(written) == "10.5270/S2_-742ikth"


@pytest.mark.parametrize("missing", [None, "", "   ", "\n"])
def test_no_doi_is_no_name(missing: str | None) -> None:
    assert doi_name(missing) is None


@pytest.mark.parametrize(
    "malformed",
    [
        "https://example.org/10.5270/S2",
        "10.5270",
        "10.5270/",
        "11.5270/S2",
        "https://doi.org/",
        "10.5270/has space",
        "10.5270/has{brace}",
        "see the paper",
    ],
)
def test_something_that_is_no_doi_is_refused_not_passed_on(malformed: str) -> None:
    with pytest.raises(ConfigError):
        doi_name(malformed)


@pytest.mark.parametrize("config", list(REGISTRY), ids=lambda config: config.dataset_id)
def test_every_registry_entry_has_a_usable_doi_or_none(config) -> None:
    name = doi_name(config.doi)
    assert name is None or (name.startswith("10.") and "://" not in name)


class TestTheRegistryRefusesAMalformedDoiAtLoad:
    """M4-14 (Otto, 07.10.2026): a DOI that is no DOI stops the start, not the first citation."""

    @pytest.mark.parametrize("malformed", ["see the paper", "10.5270", "https://example.org/10.5270/S2", "10.5270/a b"])
    def test_an_entry_with_a_malformed_doi_cannot_be_built(self, valid_config, malformed: str) -> None:
        with pytest.raises(ConfigError, match=valid_config.dataset_id):
            replace(valid_config, doi=malformed)

    @pytest.mark.parametrize(
        "fine", ["10.5555/test", "https://doi.org/10.5270/S2_-742ikth", "doi:10.5270/x", None, "", "   "]
    )
    def test_counter_sample_every_other_spelling_still_builds(self, valid_config, fine: str | None) -> None:
        """Blank stays a finding of onboarding checklist point 3, not a start failure."""
        assert replace(valid_config, doi=fine).dataset_id == valid_config.dataset_id

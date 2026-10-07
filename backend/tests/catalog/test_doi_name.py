"""``doi_name``: the registry keeps the resolver URL, STAC and BibTeX want the name (adr/0014 §10.2)."""

from __future__ import annotations

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

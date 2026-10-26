"""The list of retired datasets (adr/0017 rule III): what it holds, and what the registry does with it."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from earthx.access.download import attribution_text, build_notice_text
from earthx.api.citation import citation_bib
from earthx.catalog.datasets import REGISTRY, RETIRED, SENTINEL_2_L2A
from earthx.catalog.registry import (
    AcquisitionYears,
    ConfigError,
    DatasetRegistry,
    RetiredDataset,
    RetiredDatasetError,
    UnknownDatasetError,
)
from tests.catalog.synthetic_zarr import SYNTHETIC_ZARR, TEST_ENTRIES

GONE = "sentinel-2-l2a-zarr3"
YEARS = AcquisitionYears(2026, 2026)


def retired(**changes: object) -> RetiredDataset:
    return replace(RETIRED[0], **changes)


class TestTheList:
    def test_the_dataset_of_adr_0017_is_on_it(self) -> None:
        assert [entry.dataset_id for entry in RETIRED] == [GONE]
        assert RETIRED[0].retired_on == date(2026, 10, 25)

    def test_no_id_is_registered_and_retired_at_once(self) -> None:
        assert not {entry.dataset_id for entry in REGISTRY} & {entry.dataset_id for entry in REGISTRY.retired}

    def test_the_registry_holds_the_list(self) -> None:
        assert REGISTRY.retired == RETIRED

    def test_the_successor_is_in_the_registry(self) -> None:
        for entry in RETIRED:
            assert entry.successor in REGISTRY

    def test_the_registry_has_no_zarr_entry_so_the_zarr_cases_come_from_the_test_entry(self) -> None:
        """The other half of the guard of `test_onboarding_processing.py`: Zarr is tested on a test entry only."""
        assert not any(entry.zarr is not None for entry in REGISTRY)
        assert SYNTHETIC_ZARR.dataset_id not in REGISTRY and SYNTHETIC_ZARR in TEST_ENTRIES


class TestTheRegistryAnswers:
    def test_a_retired_id_is_an_unknown_one_for_whoever_does_not_ask_why(self) -> None:
        with pytest.raises(UnknownDatasetError):
            REGISTRY.get(GONE)

    def test_it_says_why_to_whoever_asks(self) -> None:
        with pytest.raises(RetiredDatasetError) as error:
            REGISTRY.get(GONE)
        assert error.value.retired is RETIRED[0]

    def test_an_id_that_never_existed_is_not_retired(self) -> None:
        with pytest.raises(UnknownDatasetError) as error:
            REGISTRY.get("never-existed")
        assert not isinstance(error.value, RetiredDatasetError)

    def test_the_reason_names_the_id_the_day_and_the_successor(self) -> None:
        message = RETIRED[0].message
        assert GONE in message and "2026-10-25" in message and "'sentinel-2-c1-l2a'" in message

    def test_the_text_is_one_line_of_plain_english(self) -> None:
        assert "\n" not in RETIRED[0].message and RETIRED[0].message.isascii()

    def test_the_attributable_is_the_entry_or_the_retired_record_or_nothing(self) -> None:
        assert REGISTRY.attributable("sentinel-2-c1-l2a") is SENTINEL_2_L2A
        assert REGISTRY.attributable(GONE) is RETIRED[0]
        assert REGISTRY.attributable("never-existed") is None


class TestARegistryThatContradictsItself:
    def test_an_id_both_registered_and_retired_is_refused(self) -> None:
        with pytest.raises(ConfigError, match="registered and retired at once"):
            DatasetRegistry((SENTINEL_2_L2A,), retired=(retired(dataset_id=SENTINEL_2_L2A.dataset_id),))

    def test_a_successor_the_registry_does_not_have_is_refused(self) -> None:
        with pytest.raises(ConfigError, match="successor"):
            DatasetRegistry((SENTINEL_2_L2A,), retired=(retired(successor="not-there"),))

    def test_an_id_retired_twice_is_refused(self) -> None:
        with pytest.raises(ConfigError, match="duplicate"):
            DatasetRegistry((SENTINEL_2_L2A,), retired=(retired(), retired()))

    @pytest.mark.parametrize("field", ["dataset_id", "title", "successor", "reason"])
    def test_a_record_without_a_word_is_refused(self, field: str) -> None:
        with pytest.raises(ConfigError, match=field):
            retired(**{field: "  "})


class TestTheSideFilesOfAFinishedJob:
    """A job finished before the entry left keeps its attribution, its terms and its citation."""

    def test_the_attribution_names_the_years(self) -> None:
        assert attribution_text(RETIRED[0], years=YEARS) == "Contains modified Copernicus Sentinel data 2026"

    def test_the_notice_carries_the_attribution_the_terms_and_the_title(self) -> None:
        notice = build_notice_text(RETIRED[0], item_ids=["A"], assets=["SR_10m:b04"], years=YEARS)
        assert "Contains modified Copernicus Sentinel data 2026" in notice
        assert "Sentinel Data Legal Notice" in notice and RETIRED[0].license.url in notice
        assert RETIRED[0].title in notice

    def test_the_citation_names_the_dataset_its_doi_and_the_attribution(self) -> None:
        text = citation_bib(RETIRED[0], downloaded=date(2026, 11, 2), years=YEARS).decode("utf-8")
        assert text.startswith("@misc{sentinel-2-l2a-zarr3,")
        assert "10.5270/S2_-znk9xsj" in text and "Contains modified Copernicus Sentinel data 2026" in text
        assert "2026-11-02" in text

    def test_the_licence_block_is_the_one_the_entry_had(self) -> None:
        """Frozen on purpose: it is a copy, so a later change to the COG entry cannot rewrite a finished download."""
        license_ = RETIRED[0].license
        assert license_.attribution_modified == SENTINEL_2_L2A.license.attribution_modified
        assert license_.terms == SENTINEL_2_L2A.license.terms
        assert license_.attribution_required and license_.name == "Sentinel Data Legal Notice"

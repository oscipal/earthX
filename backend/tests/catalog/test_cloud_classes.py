"""DS-03 plan §6.10, §6.19: the classes that count as cloud and the filter that may apply to the AOI."""

from __future__ import annotations

from dataclasses import replace

import pytest

from earthx.catalog.collection import to_stac_collection
from earthx.catalog.datasets import COP_DEM_GLO_30, SENTINEL_2_L2A
from earthx.catalog.registry import AoiMeasure, ConfigError, DataFormat, FilterKind
from tests.catalog.synthetic_zarr import SYNTHETIC_ZARR, TEST_ENTRIES


def _mask(**changes):
    return replace(SENTINEL_2_L2A.mask, **changes)


def _filters(**changes):
    """The filters of Sentinel-2 with ``changes`` applied to the cloud cover one."""
    first, *rest = SENTINEL_2_L2A.search_filters
    return (replace(first, **changes), *rest)


def _filters_of(property_name: str, **changes):
    """The filters of Sentinel-2 with ``changes`` applied to the one on ``property_name``."""
    return tuple(
        replace(entry, **changes) if entry.property == property_name else entry for entry in SENTINEL_2_L2A.search_filters
    )


def _without_measures(filters=SENTINEL_2_L2A.search_filters):
    return tuple(replace(entry, within_aoi=None) for entry in filters)


class TestTheEntries:
    def test_sentinel_2_counts_the_classes_of_eo_cloud_cover(self) -> None:
        assert SENTINEL_2_L2A.mask.cloud_classes == frozenset({8, 9, 10})
        assert "thin cirrus" in SENTINEL_2_L2A.mask.cloud_note
        assert SENTINEL_2_L2A.mask.cloud_note.endswith(".")

    def test_cloud_shadows_and_snow_are_not_clouds(self) -> None:
        assert not SENTINEL_2_L2A.mask.cloud_classes & {0, 1, 3, 11}

    def test_the_cloud_cover_and_the_no_data_filter_are_the_ones_within_aoi(self) -> None:
        marked = {entry.property: entry.within_aoi for entry in SENTINEL_2_L2A.search_filters if entry.within_aoi}
        assert marked == {
            "eo:cloud_cover": AoiMeasure.CLOUD_SHARE,
            "s2:nodata_pixel_percentage": AoiMeasure.NODATA_SHARE,
        }

    def test_every_measure_has_its_own_reserved_property(self) -> None:
        assert {measure.name: measure.value for measure in AoiMeasure} == {
            "CLOUD_SHARE": "earthx:aoi_cloud_cover",
            "NODATA_SHARE": "earthx:aoi_nodata",
        }

    def test_the_filters_without_an_area_have_none(self) -> None:
        none = [entry.property for entry in SENTINEL_2_L2A.search_filters if entry.within_aoi is None]
        assert "platform" in none and "s2:snow_ice_percentage" in none and "eo:cloud_cover" not in none

    def test_the_synthetic_zarr_entry_has_no_cloud_classes_and_no_such_filter(self) -> None:
        assert SYNTHETIC_ZARR.mask.cloud_classes == frozenset() and SYNTHETIC_ZARR.mask.cloud_note == ""
        assert all(entry.within_aoi is None for entry in SYNTHETIC_ZARR.search_filters)

    def test_the_dem_has_no_mask_and_no_filter(self) -> None:
        assert COP_DEM_GLO_30.mask is None
        assert all(entry.within_aoi is None for entry in COP_DEM_GLO_30.search_filters)

    @pytest.mark.parametrize("entry", TEST_ENTRIES, ids=lambda entry: entry.dataset_id)
    def test_a_filter_within_aoi_only_where_there_are_cloud_classes(self, entry) -> None:
        has_filter = any(item.within_aoi is not None for item in entry.search_filters)
        has_classes = entry.mask is not None and bool(entry.mask.cloud_classes)
        assert has_filter <= has_classes


class TestCloudClassesAreRefused:
    @pytest.mark.parametrize(
        ("changes", "match"),
        [
            ({"cloud_classes": [8, 9, 10]}, "frozenset of whole numbers"),
            ({"cloud_classes": {8, 9, 10}}, "frozenset of whole numbers"),
            ({"cloud_classes": frozenset({8.0})}, "frozenset of whole numbers"),
            ({"cloud_classes": frozenset({"8"})}, "frozenset of whole numbers"),
            ({"cloud_classes": frozenset({True})}, "frozenset of whole numbers"),
            ({"cloud_classes": frozenset({8, 12})}, "among the listed mask classes"),
            ({"cloud_classes": frozenset({-1})}, "among the listed mask classes"),
            ({"cloud_note": ""}, "need a cloud_note"),
            ({"cloud_note": "   "}, "need a cloud_note"),
            ({"cloud_note": None}, "cloud_note is a text"),
            ({"cloud_classes": frozenset(), "cloud_note": None}, "cloud_note is a text"),
        ],
    )
    def test_a_mask_that_contradicts_itself(self, changes, match) -> None:
        with pytest.raises(ConfigError, match=match) as caught:
            replace(SENTINEL_2_L2A, mask=_mask(**changes))
        assert SENTINEL_2_L2A.dataset_id in str(caught.value)

    def test_another_format_than_cog_is_refused_and_the_message_says_why(self) -> None:
        with pytest.raises(ConfigError, match="need a COG") as caught:
            replace(SENTINEL_2_L2A, format=DataFormat.ZARR, zarr=SYNTHETIC_ZARR.zarr)
        assert "overviews" in str(caught.value) and "reader of its own" in str(caught.value)

    def test_classes_with_a_zarr_layer_are_refused_too(self) -> None:
        with pytest.raises(ConfigError, match="need a COG"):
            replace(SYNTHETIC_ZARR, mask=replace(SYNTHETIC_ZARR.mask, cloud_classes=frozenset({8}), cloud_note="Note."))

    def test_without_classes_a_note_and_any_format_are_taken(self) -> None:
        assert replace(SYNTHETIC_ZARR, mask=replace(SYNTHETIC_ZARR.mask, cloud_note="Note.")).format is DataFormat.ZARR
        assert replace(SENTINEL_2_L2A, mask=_mask(cloud_classes=frozenset()), search_filters=_without_measures())

    def test_a_subset_of_the_classes_is_taken(self) -> None:
        assert replace(SENTINEL_2_L2A, mask=_mask(cloud_classes=frozenset({9}))).mask.cloud_classes == {9}


class TestWithinAoiIsRefused:
    def test_it_needs_cloud_classes(self) -> None:
        with pytest.raises(
            ConfigError, match="within_aoi on 'eo:cloud_cover' needs a mask with cloud_classes"
        ) as caught:
            replace(SENTINEL_2_L2A, mask=_mask(cloud_classes=frozenset()))
        assert SENTINEL_2_L2A.dataset_id in str(caught.value)

    def test_the_no_data_share_is_as_strict_as_the_cloud_share(self) -> None:
        """Both are read from the classification of a COG; a mask without cloud classes allows neither."""
        only_nodata = _filters_of("eo:cloud_cover", within_aoi=None)
        with pytest.raises(
            ConfigError, match="within_aoi on 's2:nodata_pixel_percentage' needs a mask with cloud_classes"
        ):
            replace(SENTINEL_2_L2A, mask=_mask(cloud_classes=frozenset()), search_filters=only_nodata)
        unmasked = replace(SENTINEL_2_L2A.capabilities, masking=False)
        with pytest.raises(ConfigError, match="needs a mask with cloud_classes"):
            replace(SENTINEL_2_L2A, mask=None, capabilities=unmasked, search_filters=only_nodata)

    def test_the_no_data_share_alone_is_taken_where_the_classification_is_there(self) -> None:
        only_nodata = _filters_of("eo:cloud_cover", within_aoi=None)
        assert replace(SENTINEL_2_L2A, search_filters=only_nodata)

    def test_it_needs_a_mask_at_all(self) -> None:
        unmasked = replace(SENTINEL_2_L2A.capabilities, masking=False)
        with pytest.raises(ConfigError, match="needs a mask with cloud_classes"):
            replace(SENTINEL_2_L2A, mask=None, capabilities=unmasked)

    @pytest.mark.parametrize("measure", list(AoiMeasure), ids=lambda measure: measure.name)
    def test_the_same_measure_on_two_filters(self, measure) -> None:
        first, second, *others = _without_measures()
        with pytest.raises(ConfigError, match="more than one filter") as caught:
            replace(
                SENTINEL_2_L2A,
                search_filters=(replace(first, within_aoi=measure), replace(second, within_aoi=measure), *others),
            )
        assert SENTINEL_2_L2A.dataset_id in str(caught.value)

    def test_two_measures_on_two_filters_are_taken(self) -> None:
        first, second, *others = _without_measures()
        both = (replace(first, within_aoi=AoiMeasure.CLOUD_SHARE), replace(second, within_aoi=AoiMeasure.NODATA_SHARE))
        assert replace(SENTINEL_2_L2A, search_filters=(*both, *others))

    @pytest.mark.parametrize("name", ["eo:cloud_cover", "s2:nodata_pixel_percentage"])
    @pytest.mark.parametrize(
        "changes",
        [
            {"minimum": 10.0},
            {"maximum": 90.0},
            {"maximum": 1.0},
            {"unit": "1"},
            {"unit": None},
        ],
    )
    def test_on_a_range_that_is_not_a_percentage(self, name, changes) -> None:
        with pytest.raises(ConfigError, match=f"within_aoi on '{name}' needs a range filter from 0 to 100"):
            replace(SENTINEL_2_L2A, search_filters=_filters_of(name, **changes))

    @pytest.mark.parametrize("measure", list(AoiMeasure), ids=lambda measure: measure.name)
    def test_on_a_values_filter(self, measure) -> None:
        *_, platform = SENTINEL_2_L2A.search_filters
        with pytest.raises(ConfigError, match="range filter from 0 to 100"):
            replace(SENTINEL_2_L2A, search_filters=(replace(platform, within_aoi=measure),))

    @pytest.mark.parametrize("flag", [True, False, 1, 0, "yes", "earthx:aoi_cloud_cover", AoiMeasure])
    def test_not_a_measure_or_none(self, flag) -> None:
        with pytest.raises(ConfigError, match="is an AoiMeasure or None"):
            replace(SENTINEL_2_L2A, search_filters=_filters(within_aoi=flag))

    def test_a_filter_may_stay_without_it(self) -> None:
        entry = replace(SENTINEL_2_L2A, search_filters=_without_measures())
        assert all(item.within_aoi is None for item in entry.search_filters)

    def test_the_cloud_cover_filter_stays_a_range(self) -> None:
        assert SENTINEL_2_L2A.search_filter("eo:cloud_cover").kind is FilterKind.RANGE


class TestTheCollection:
    def test_the_mask_publishes_classes_ascending_and_the_note(self) -> None:
        published = to_stac_collection(SENTINEL_2_L2A)["earthx:mask"]
        assert published["cloud_classes"] == [8, 9, 10]
        assert published["cloud_note"] == SENTINEL_2_L2A.mask.cloud_note

    def test_an_entry_without_classes_publishes_an_empty_list_and_text(self) -> None:
        published = to_stac_collection(SYNTHETIC_ZARR)["earthx:mask"]
        assert published["cloud_classes"] == [] and published["cloud_note"] == ""

    def test_the_dem_still_publishes_no_mask(self) -> None:
        assert to_stac_collection(COP_DEM_GLO_30)["earthx:mask"] is None

    def test_the_filters_publish_within_aoi_as_the_name_of_the_property_or_null(self) -> None:
        published = to_stac_collection(SENTINEL_2_L2A)["earthx:search_filters"]
        assert {entry["property"]: entry["within_aoi"] for entry in published} == {
            **{entry.property: None for entry in SENTINEL_2_L2A.search_filters},
            "eo:cloud_cover": "earthx:aoi_cloud_cover",
            "s2:nodata_pixel_percentage": "earthx:aoi_nodata",
        }
        assert len(published) == len(SENTINEL_2_L2A.search_filters)

    def test_a_dataset_without_a_measure_publishes_null_everywhere(self) -> None:
        published = to_stac_collection(SYNTHETIC_ZARR)["earthx:search_filters"]
        assert published and all(entry["within_aoi"] is None for entry in published)

"""DS-04 plan §4.2–§4.4 and F2: href rewrites, the asset checksum, notices and the choice of the default asset."""

from __future__ import annotations

from dataclasses import replace

import pytest

from earthx.catalog.collection import to_stac_collection
from earthx.catalog.registry import (
    AssetChecksum,
    AssetSelection,
    ConfigError,
    DefaultRender,
    HrefRewrite,
    Notice,
    rewrite_href,
)

S3 = "s3://bucket-a/"
HTTPS = "https://assets.example.invalid/bucket-a/"
NOTICE = Notice(code="approximate_geolocation", label="Approximate geolocation", tooltip="Placed by its GCPs.")


@pytest.fixture
def with_source(vary, valid_config):
    def _with(**changes: object):
        return vary(source=replace(valid_config.source, **changes))

    return _with


class TestHrefRewrites:
    def test_a_rewrite_onto_an_asset_host_is_accepted(self, with_source) -> None:
        config = with_source(asset_href_rewrites=(HrefRewrite(S3, HTTPS),))
        assert config.source.asset_href_rewrites[0].to_prefix == HTTPS

    @pytest.mark.parametrize(
        ("old", "new"),
        [
            (S3, "https://elsewhere.example.invalid/bucket-a/"),  # a host the entry does not name
            (S3, "http://assets.example.invalid/bucket-a/"),  # not https
            (S3, "https://assets.example.invalid:8443/bucket-a/"),  # a port
            (S3, "https://assets.example.invalid/bucket-a"),  # no closing slash: would match bucket-ab
            ("s3://bucket-a", HTTPS),
            (S3, "https://assets.example.invalid/../bucket-a/"),
            (S3, "https://assets.example.invalid/bucket-a/?x=1/"),
            ("https://assets.example.invalid/", HTTPS),  # https needs no rewrite
            ("bucket-a/", HTTPS),  # no scheme
        ],
    )
    def test_a_bad_rewrite_stops_the_start(self, with_source, old, new) -> None:
        with pytest.raises(ConfigError, match="href rewrite"):
            with_source(asset_href_rewrites=(HrefRewrite(old, new),))

    def test_a_prefix_inside_another_stops_the_start(self, with_source) -> None:
        rewrites = (HrefRewrite(S3, HTTPS), HrefRewrite("s3://bucket-a/sub/", HTTPS))
        with pytest.raises(ConfigError, match="inside another"):
            with_source(asset_href_rewrites=rewrites)

    def test_a_prefix_twice_stops_the_start(self, with_source) -> None:
        with pytest.raises(ConfigError, match="twice"):
            with_source(asset_href_rewrites=(HrefRewrite(S3, HTTPS), HrefRewrite(S3, HTTPS)))

    def test_rewrites_are_a_tuple_of_rewrites(self, with_source) -> None:
        with pytest.raises(ConfigError, match="tuple of HrefRewrite"):
            with_source(asset_href_rewrites=((S3, HTTPS),))

    def test_a_matching_href_gets_the_https_prefix(self) -> None:
        assert rewrite_href(S3 + "GRD/x/iw-vv.tiff", (HrefRewrite(S3, HTTPS),)) == HTTPS + "GRD/x/iw-vv.tiff"

    @pytest.mark.parametrize(
        "href",
        [
            "s3://bucket-b/GRD/x.tiff",  # another bucket
            "s3://bucket-ab/x.tiff",  # a longer name
            S3 + "GRD/../../other/x.tiff",
            S3 + "x.tiff?versionId=1",
            S3 + "x.tiff#frag",
            S3 + "x\\..\\y.tiff",
            "https://assets.example.invalid/bucket-a/x.tiff",
        ],
    )
    def test_any_other_href_stays_as_the_source_wrote_it(self, href) -> None:
        assert rewrite_href(href, (HrefRewrite(S3, HTTPS),)) == href


class TestAssetChecksum:
    def test_crc64nvme_or_none(self, with_source) -> None:
        assert with_source(asset_checksum=AssetChecksum.CRC64NVME).source.asset_checksum is AssetChecksum.CRC64NVME
        assert with_source(asset_checksum=None).source.asset_checksum is None

    def test_text_is_no_checksum(self, with_source) -> None:
        with pytest.raises(ConfigError, match="asset_checksum"):
            with_source(asset_checksum="crc64nvme")


class TestNotices:
    def test_well_formed_notices_are_accepted_and_published(self, vary) -> None:
        other = Notice(code="uncalibrated_dn", label="Uncalibrated (DN)", tooltip="Digital numbers.")
        built = to_stac_collection(vary(notices=(NOTICE, other)))
        assert [notice["code"] for notice in built["earthx:notices"]] == ["approximate_geolocation", "uncalibrated_dn"]
        assert built["earthx:notices"][0] == {
            "code": "approximate_geolocation",
            "label": "Approximate geolocation",
            "tooltip": "Placed by its GCPs.",
        }

    @pytest.mark.parametrize(
        ("change", "match"),
        [
            ({"code": ""}, "lower_snake_case"),
            ({"code": "Approximate"}, "lower_snake_case"),
            ({"code": "a__b"}, "lower_snake_case"),
            ({"label": ""}, "one line"),
            ({"label": " padded"}, "one line"),
            ({"label": "x" * 33}, "longer than 32"),
            ({"tooltip": "two\nlines"}, "one line"),
            ({"tooltip": "x" * 201}, "longer than 200"),
        ],
    )
    def test_a_malformed_notice_stops_the_start(self, vary, change, match) -> None:
        with pytest.raises(ConfigError, match=match):
            vary(notices=(replace(NOTICE, **change),))

    def test_a_code_twice_stops_the_start(self, vary) -> None:
        with pytest.raises(ConfigError, match="twice"):
            vary(notices=(NOTICE, replace(NOTICE, label="Other")))

    def test_notices_are_a_tuple_of_notices(self, vary) -> None:
        with pytest.raises(ConfigError, match="tuple of Notice"):
            vary(notices=[NOTICE])
        with pytest.raises(ConfigError, match="tuple of Notice"):
            vary(notices=({"code": "x"},))

    def test_no_notice_is_published_as_an_empty_list(self, valid_config) -> None:
        assert to_stac_collection(valid_config)["earthx:notices"] == []


class TestAssetSelection:
    @staticmethod
    def render(**changes: object) -> DefaultRender:
        fields = {
            "title": "Co-polarisation",
            "assets": ("vv", "hh"),
            "rescale": ((0.0, 250.0), (0.0, 750.0)),
            "colormap_name": None,
            "expression": None,
            "resampling": "nearest",
            "asset_selection": AssetSelection.FIRST_PRESENT,
        }
        return DefaultRender(**{**fields, **changes})

    def test_first_present_takes_a_list_and_a_stretch_per_asset(self) -> None:
        assert self.render().asset_selection is AssetSelection.FIRST_PRESENT
        assert self.render(rescale=None).rescale is None

    def test_first_present_needs_a_choice(self) -> None:
        with pytest.raises(ConfigError, match="at least two"):
            self.render(assets=("vv",))

    def test_first_present_needs_a_stretch_for_each_asset(self) -> None:
        with pytest.raises(ConfigError, match="one rescale pair per asset"):
            self.render(rescale=((0.0, 500.0),))

    def test_a_colormap_may_paint_the_chosen_band(self) -> None:
        assert self.render(colormap_name="greys").colormap_name == "greys"

    def test_text_is_no_selection(self) -> None:
        with pytest.raises(ConfigError, match="asset_selection"):
            self.render(asset_selection="all")

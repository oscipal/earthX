"""The GDAL settings carry no credentials, and a raw string cannot become a path."""

from __future__ import annotations

import pytest

from earthx.gateway import Policy
from earthx.gateway.checks import CheckedUrl
from earthx.gateway.gdal import VSI_CACHE_BYTES, gdal_options, vsicurl_path

HOST = "earth-search.aws.element84.com"
URL = f"https://{HOST}/collections/sentinel-2-c1-l2a/x.tif"
POLICY = Policy(allowed_hosts=frozenset({HOST}), connect_timeout_s=5.0, read_timeout_s=15.0)
CHECKED = CheckedUrl(url=URL, host=HOST, port=443, addresses=("93.184.216.34",))


@pytest.mark.parametrize("word", ["HEADER", "AUTH", "TOKEN", "SECRET", "PASSWORD", "ACCESS_KEY"])
def test_no_setting_looks_like_a_credential(word: str) -> None:
    assert not [name for name in gdal_options(POLICY) if word in name.upper()]


def test_no_value_carries_a_bearer_token() -> None:
    assert not [value for value in gdal_options(POLICY).values() if "Bearer" in value]


def test_only_cog_extensions_may_be_opened() -> None:
    extensions = gdal_options(POLICY)["CPL_VSIL_CURL_ALLOWED_EXTENSIONS"].split(",")
    assert {extension.lower() for extension in extensions} == {".tif", ".tiff"}


def test_certificate_verification_is_not_switched_off() -> None:
    assert gdal_options(POLICY)["GDAL_HTTP_UNSAFESSL"] == "NO"


def test_the_timeouts_are_the_ones_the_policy_sets() -> None:
    options = gdal_options(Policy(allowed_hosts=frozenset({HOST}), connect_timeout_s=3.0, read_timeout_s=20.0))
    assert (options["GDAL_HTTP_CONNECTTIMEOUT"], options["GDAL_HTTP_TIMEOUT"]) == ("3", "20")


def test_the_read_cache_stays_at_the_size_the_prototype_used() -> None:
    assert gdal_options(POLICY)["VSI_CACHE_SIZE"] == str(VSI_CACHE_BYTES) == str(64 * 1024 * 1024)


def test_a_directory_listing_is_not_triggered_by_opening_a_file() -> None:
    assert gdal_options(POLICY)["GDAL_DISABLE_READDIR_ON_OPEN"] == "EMPTY_DIR"


def test_the_path_keeps_the_name_because_gdal_checks_the_certificate_itself() -> None:
    assert vsicurl_path(CHECKED) == f"/vsicurl/{URL}"
    assert "93.184.216.34" not in vsicurl_path(CHECKED)


def test_a_url_that_never_passed_the_check_cannot_become_a_path() -> None:
    with pytest.raises(TypeError):
        vsicurl_path(URL)  # type: ignore[arg-type]

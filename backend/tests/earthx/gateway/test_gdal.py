"""The GDAL settings carry no credentials, and a raw string cannot become a path."""

from __future__ import annotations

import threading

import pytest
import rasterio
from rasterio._env import get_gdal_config

from earthx.gateway import Policy
from earthx.gateway.checks import CheckedUrl
from earthx.gateway.gdal import (
    TILER_CURL_CACHE_BYTES,
    VSI_CACHE_BYTES,
    crop_gdal_options,
    gdal_options,
    tile_gdal_options,
    vsicurl_path,
)
from earthx.readers import process_gdal_options

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


class TestTilerProfiles:
    """NM4-26 §10, §13, §18: the tiles read serially into a big cache, the crop keeps parallel reads."""

    def test_the_tile_profile_reads_serially_into_a_cache_of_256_mib(self) -> None:
        options = tile_gdal_options(POLICY)
        assert options["GDAL_HTTP_MULTIRANGE"] == "SERIAL"
        assert options["CPL_VSIL_CURL_CACHE_SIZE"] == str(TILER_CURL_CACHE_BYTES) == str(256 * 1024 * 1024)

    def test_the_crop_profile_has_the_cache_and_keeps_the_multirange_of_the_base(self) -> None:
        options = crop_gdal_options(POLICY)
        assert options["CPL_VSIL_CURL_CACHE_SIZE"] == str(TILER_CURL_CACHE_BYTES)
        assert options["GDAL_HTTP_MULTIRANGE"] == gdal_options(POLICY)["GDAL_HTTP_MULTIRANGE"] == "YES"

    def test_the_cache_size_is_in_both_because_gdal_reads_it_once_per_process(self) -> None:
        assert tile_gdal_options(POLICY)["CPL_VSIL_CURL_CACHE_SIZE"] == crop_gdal_options(POLICY)["CPL_VSIL_CURL_CACHE_SIZE"]

    def test_otherwise_both_are_the_base_profile(self) -> None:
        base = gdal_options(POLICY)
        for options, changed in (
            (tile_gdal_options(POLICY), {"CPL_VSIL_CURL_CACHE_SIZE", "GDAL_HTTP_MULTIRANGE"}),
            (crop_gdal_options(POLICY), {"CPL_VSIL_CURL_CACHE_SIZE"}),
        ):
            assert {name: value for name, value in options.items() if name not in changed} == {
                name: value for name, value in base.items() if name not in changed
            }
            assert set(options) - set(base) <= {"CPL_VSIL_CURL_CACHE_SIZE"}

    def test_the_profiles_follow_the_policy_like_the_base_does(self) -> None:
        policy = Policy(allowed_hosts=frozenset({HOST}), connect_timeout_s=3.0, read_timeout_s=20.0)
        for options in (tile_gdal_options(policy), crop_gdal_options(policy)):
            assert (options["GDAL_HTTP_CONNECTTIMEOUT"], options["GDAL_HTTP_TIMEOUT"]) == ("3", "20")
            assert options["GDAL_HTTP_UNSAFESSL"] == "NO"

    def test_asking_for_a_profile_does_not_change_the_base_nor_the_other_profile(self) -> None:
        tile_gdal_options(POLICY)["GDAL_HTTP_MULTIRANGE"] = "NO"
        assert gdal_options(POLICY)["GDAL_HTTP_MULTIRANGE"] == "YES"
        assert tile_gdal_options(POLICY)["GDAL_HTTP_MULTIRANGE"] == "SERIAL"
        assert crop_gdal_options(POLICY)["GDAL_HTTP_MULTIRANGE"] == "YES"

    def test_the_base_and_the_worker_carry_neither_serial_nor_the_cache_size(self) -> None:
        """The worker and the runner build on the base (`readers.process_gdal_options`) and stay as they were."""
        for options in (gdal_options(POLICY), dict(process_gdal_options())):
            assert options["GDAL_HTTP_MULTIRANGE"] == "YES"
            assert "CPL_VSIL_CURL_CACHE_SIZE" not in options

    def test_a_profile_is_still_free_of_credentials(self) -> None:
        for options in (tile_gdal_options(POLICY), crop_gdal_options(POLICY)):
            assert not [name for name in options if any(word in name.upper() for word in ("AUTH", "TOKEN", "SECRET"))]


def test_each_thread_reads_the_multirange_of_its_own_environment() -> None:
    """GDAL reads `GDAL_HTTP_MULTIRANGE` at every call in the calling thread (NM4-26 §18), which is how the
    crop keeps `YES` in the process whose tiles read `SERIAL`. `rasterio.Env` entered in a thread is that
    thread's alone."""
    barrier = threading.Barrier(2, timeout=10)
    seen: dict[str, str] = {}

    def read(name: str, options: dict[str, str]) -> None:
        with rasterio.Env(**options):
            barrier.wait()  # both environments are open at the same moment
            seen[name] = str(get_gdal_config("GDAL_HTTP_MULTIRANGE"))
            barrier.wait()  # and neither leaves before the other has looked

    threads = [
        threading.Thread(target=read, args=("tile", tile_gdal_options(POLICY))),
        threading.Thread(target=read, args=("crop", crop_gdal_options(POLICY))),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert seen == {"tile": "SERIAL", "crop": "YES"}
    assert get_gdal_config("GDAL_HTTP_MULTIRANGE") is None

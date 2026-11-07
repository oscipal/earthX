"""`EARTHX_GEOCODER_USER_AGENT` is gone in favour of `EARTHX_USER_AGENT` (M5-18 §3.1)."""

from __future__ import annotations

import logging

import pytest

from earthx.api.dependencies import resolve_geocoder_config, warn_retired_settings


class TestRetiredGeocoderVariable:
    def test_still_set_warns_by_name_only(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="earthx.api.dependencies"):
            warn_retired_settings({"EARTHX_GEOCODER_USER_AGENT": "Old/1.0 (+https://old.invalid)"})
        assert "EARTHX_GEOCODER_USER_AGENT" in caplog.text
        assert "old.invalid" not in caplog.text

    def test_unset_stays_silent(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="earthx.api.dependencies"):
            warn_retired_settings({})
        assert caplog.text == ""

    def test_it_no_longer_reaches_the_geocoder_config(self) -> None:
        config = resolve_geocoder_config(
            {"EARTHX_GEOCODER_URL": "https://geocoder.example.org", "EARTHX_GEOCODER_USER_AGENT": "Old/1.0"}
        )
        assert config is not None
        assert not hasattr(config, "user_agent")

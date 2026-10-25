"""NM4-03: ``EARTHX_TILER_URL``, the only source of the base of the ``tiles`` link."""

from __future__ import annotations

import logging

import pytest

from earthx.api.dependencies import TILER_URL_ENV, resolve_tiler_base
from earthx.api.processing_docs import tiles_href

ID = "ZyXwVuTsRqPoNmLkJiHg_-"


@pytest.mark.parametrize(
    ("raw", "base"),
    [
        ("http://localhost:8001", "http://localhost:8001"),
        ("https://tiles.example.test/", "https://tiles.example.test"),
        ("  https://example.test/tiler//  ", "https://example.test/tiler"),
    ],
)
def test_a_usable_value_is_kept_without_a_trailing_slash(raw: str, base: str) -> None:
    assert resolve_tiler_base({TILER_URL_ENV: raw}) == base


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "tiles.example.test",
        "ftp://example.test",
        "javascript:alert(1)",
        "https://",
        "https://user:secret@example.test",
        "https://example.test?x=1",
        "https://example.test#frag",
        "https://example.test:notaport",
        "https://exa mple.test",
        "https://example.test/a\nb",
        "https://example.test:99999",
        "https://example.test//..\\x",
        "https://example.test/<x>",
    ],
)
def test_an_unusable_value_is_none_and_never_logged(raw: str, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        assert resolve_tiler_base({TILER_URL_ENV: raw}) is None
    assert "secret" not in caplog.text and "example.test" not in caplog.text


def test_an_unset_variable_is_none() -> None:
    assert resolve_tiler_base({}) is None


def test_the_link_is_the_base_and_the_path() -> None:
    assert tiles_href("http://localhost:8001", ID) == f"http://localhost:8001/results/{ID}/WebMercatorQuad/tilejson.json"
    assert tiles_href(None, ID) == f"/results/{ID}/WebMercatorQuad/tilejson.json"

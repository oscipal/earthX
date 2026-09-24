"""The local command refuses before it ever reaches the network."""

from __future__ import annotations

import pytest

from earthx.chatbot.__main__ import STAC_URL_ENV, main


def test_without_a_stac_root_it_says_what_is_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(STAC_URL_ENV, raising=False)
    assert main(["search", "radar"]) == 2
    assert STAC_URL_ENV in capsys.readouterr().err


@pytest.mark.parametrize("url", ["http://localhost:8000/stac", "https://127.0.0.1/stac", "https://localhost/stac"])
def test_a_local_address_is_refused_by_the_gateway_rules(url: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--stac-url", url, "collection", "sentinel-2-l2a"]) == 2
    assert capsys.readouterr().err.startswith("refused:")

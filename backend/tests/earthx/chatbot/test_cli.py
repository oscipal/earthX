"""The local command refuses before it ever reaches the network."""

from __future__ import annotations

from pathlib import Path

import pytest

from earthx.chatbot.__main__ import API_KEY_ENV, GPU_LAYERS_ENV, LOCAL_MODEL_ENV, MODEL_ENV, STAC_URL_ENV, main


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


@pytest.mark.parametrize("unset", [MODEL_ENV, API_KEY_ENV])
def test_chat_says_which_setting_is_missing_and_never_prints_the_key(
    unset: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(LOCAL_MODEL_ENV, raising=False)
    monkeypatch.setenv(MODEL_ENV, "test-model")
    monkeypatch.setenv(API_KEY_ENV, "test-key-not-a-secret")
    monkeypatch.delenv(unset)
    assert main(["--stac-url", "https://stac.example.invalid/stac", "chat", "radar?"]) == 2
    captured = capsys.readouterr()
    assert unset in captured.err
    assert "test-key-not-a-secret" not in captured.err + captured.out


def test_chat_refuses_a_local_stac_root_before_asking_the_model(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(LOCAL_MODEL_ENV, raising=False)
    monkeypatch.setenv(MODEL_ENV, "test-model")
    monkeypatch.setenv(API_KEY_ENV, "test-key-not-a-secret")
    assert main(["--stac-url", "http://localhost:8000/stac", "chat", "radar?"]) == 2
    assert capsys.readouterr().err.startswith("refused:")


def test_a_local_model_needs_no_key_and_a_missing_file_is_a_model_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(MODEL_ENV, raising=False)
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    monkeypatch.setenv(LOCAL_MODEL_ENV, str(tmp_path / "missing.gguf"))
    assert main(["--stac-url", "https://stac.example.invalid/stac", "chat", "radar?"]) == 1
    assert capsys.readouterr().err.startswith("model error:")


def test_a_gpu_layer_count_that_is_not_a_number_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(LOCAL_MODEL_ENV, str(tmp_path / "model.gguf"))
    monkeypatch.setenv(GPU_LAYERS_ENV, "all")
    assert main(["--stac-url", "https://stac.example.invalid/stac", "chat", "radar?"]) == 1
    assert GPU_LAYERS_ENV in capsys.readouterr().err

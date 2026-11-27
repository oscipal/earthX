"""The embedding model of the search without the model (M5-23; docs/plans/m5/m5-23-vektorsuche.md §3.3, §4)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from earthx.catalog.embedding import (
    DIMENSION,
    MODEL_ENV,
    OnnxEmbedder,
    QueryVectors,
    background_texts,
    embedding_text,
    load_embedder,
    load_query_vectors,
    vector_literal,
)
from earthx.catalog.registry import ConfigError


def test_only_the_parts_a_and_b_are_embedded():
    assert embedding_text("swissalti3d\nswissALTI3D", "elevation\nSchweiz") == "swissalti3d\nswissALTI3D\nelevation\nSchweiz"
    assert embedding_text("main-entry\nTitle", "") == "main-entry\nTitle"


def test_a_vector_literal_has_every_number_and_nothing_else():
    vector = np.zeros(DIMENSION, dtype=np.float32)
    vector[0] = 0.25
    literal = vector_literal(vector)
    assert literal.startswith("[0.25,0,") and literal.endswith("]") and literal.count(",") == DIMENSION - 1


@pytest.mark.parametrize("vector", [np.zeros(DIMENSION - 1), np.zeros((1, DIMENSION)), np.full(DIMENSION, np.nan)])
def test_a_vector_of_another_shape_or_without_numbers_is_refused(vector):
    with pytest.raises(ValueError):
        vector_literal(vector)


def test_without_a_model_directory_there_is_no_vector_arm(monkeypatch):
    monkeypatch.delenv(MODEL_ENV, raising=False)
    assert load_embedder() is None
    assert load_query_vectors() is None
    monkeypatch.setenv(MODEL_ENV, "  ")
    assert load_embedder() is None


def test_a_model_directory_without_its_files_stops_the_start(monkeypatch, tmp_path):
    (tmp_path / "model.onnx").write_bytes(b"")
    monkeypatch.setenv(MODEL_ENV, str(tmp_path))
    with pytest.raises(ConfigError, match="tokenizer.json is missing"):
        load_embedder()
    with pytest.raises(ConfigError, match="model.onnx is missing"):
        OnnxEmbedder(tmp_path / "elsewhere")


def test_the_background_has_texts_only(tmp_path: Path):
    assert len(background_texts()) >= 10
    for text in ("texts: [a, b]\n", "other: []\n", "texts:\n" + "- ''\n" * 12, "- a\n"):
        path = tmp_path / "background.yaml"
        path.write_text(text, encoding="utf-8")
        background_texts.cache_clear()
        with pytest.raises(ConfigError):
            background_texts(path)
    background_texts.cache_clear()


class _Axes:
    """Every text a unit vector: the background on axes 1 and 2, the query on axis 1."""

    name = "axes@1"

    def embed(self, texts):
        vectors = np.zeros((len(texts), DIMENSION), dtype=np.float32)
        for row, text in enumerate(texts):
            vectors[row, 1 if text == "query" or row % 2 else 2] = 1
        return vectors


def test_the_least_cosine_lies_above_the_background_of_the_query():
    vectors = QueryVectors(_Axes(), threshold=2.0)
    query = vectors.vector("query")
    cosines = np.array([1.0 if row % 2 else 0.0 for row in range(len(background_texts()))])
    assert query.min_cosine == pytest.approx(cosines.mean() + 2.0 * cosines.std())
    assert query.model == "axes@1"

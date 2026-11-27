"""The embedding model of the dataset search (adr/0026 §4.3, F2; docs/plans/m5/m5-23-vektorsuche.md §3, §4).

``granite-embedding-97m-multilingual-r2`` (Apache-2.0) as ONNX in fp32, run on the CPU with ONNX Runtime: a CLS
vector of 384 numbers, normalized, the same for a query and a text, without prefixes. The files lie in the image stage
``search`` of `api` and `catalog-load` only (F2 a); :data:`MODEL_ENV` names their directory. Nothing is fetched at run
time: the tokenizer is read from its file, never through a hub.

:class:`QueryVectors` is what the search needs from it: the vector of a query and its least cosine. A hit counts where
its cosine lies at least :data:`MIN_RELATIVE_SIMILARITY` standard deviations above the mean cosine of the query with
the fixed texts of ``search_background.yaml`` (plan §3.3): a fixed cosine separated no model's answers to questions
without a matching dataset from the wanted ones.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Protocol

import numpy as np

import earthx
from earthx.catalog.entry_files import EntryFileError, read_yaml
from earthx.catalog.registry import ConfigError

#: The directory with ``model.onnx`` and ``tokenizer.json``; unset, the search runs without its vector arm (plan A1).
MODEL_ENV = "EARTHX_EMBEDDING_MODEL"
#: The model and its revision, as ``embedding_model`` of the index holds it. The image stage loads exactly this
#: revision (``backend/Dockerfile``).
MODEL_NAME = "ibm-granite/granite-embedding-97m-multilingual-r2@835ad14087e140460703cf0fae09f97d469d65c2"
#: The column of migration ``039``.
DIMENSION = 384
#: Longer texts are cut; a text of the parts A and B rarely has a hundred.
MAX_TOKENS = 512
#: Texts per run of the model: sorted by length first, so that little padding is computed.
BATCH = 32
#: Chosen on the evaluation set with the texts of :data:`BACKGROUND_FILE` (plan §3.3: it passes from 2.5 to 2.8).
MIN_RELATIVE_SIMILARITY = 2.7
BACKGROUND_FILE = Path(earthx.__file__).resolve().parents[1] / "catalog" / "search_background.yaml"


class Embedder(Protocol):
    """Normalized vectors, one row per text."""

    name: str

    def embed(self, texts: Sequence[str]) -> np.ndarray: ...


def embedding_text(a: str, b: str) -> str:
    """What is embedded of a search text: its parts A and B (id, titles; keywords, places, category), plan F3."""
    return "\n".join(part for part in (a, b) if part)


class OnnxEmbedder:
    """The model of :data:`MODEL_NAME` from the files in ``directory``.

    ``threads`` is the number of threads one run of the model uses; ``None`` leaves it to ONNX Runtime (every core,
    for `catalog-load`). `api` runs one per query, so that queries running at once do not fight for the cores.
    """

    name = MODEL_NAME

    def __init__(self, directory: Path, *, threads: int | None = None) -> None:
        import onnxruntime
        from tokenizers import Tokenizer

        model, tokenizer = directory / "model.onnx", directory / "tokenizer.json"
        for path in (model, tokenizer):
            if not path.is_file():
                raise ConfigError(f"{MODEL_ENV}: {path.name} is missing in the model directory")
        options = onnxruntime.SessionOptions()
        if threads is not None:
            options.intra_op_num_threads = threads
            options.inter_op_num_threads = 1
        self._session = onnxruntime.InferenceSession(str(model), options, providers=["CPUExecutionProvider"])
        self._tokenizer = Tokenizer.from_file(str(tokenizer))
        self._tokenizer.enable_truncation(MAX_TOKENS)
        self._tokenizer.enable_padding()
        self._inputs = {i.name for i in self._session.get_inputs()}

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        vectors = np.empty((len(texts), DIMENSION), dtype=np.float32)
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        for start in range(0, len(order), BATCH):
            chosen = order[start : start + BATCH]
            vectors[chosen] = self._run([texts[i] for i in chosen])
        return vectors

    def _run(self, texts: list[str]) -> np.ndarray:
        encoded = self._tokenizer.encode_batch(texts)
        ids = np.array([e.ids for e in encoded], dtype=np.int64)
        feed = {"input_ids": ids, "attention_mask": np.array([e.attention_mask for e in encoded], dtype=np.int64)}
        if "token_type_ids" in self._inputs:
            feed["token_type_ids"] = np.zeros_like(ids)
        cls = self._session.run(None, feed)[0][:, 0]
        return cls / np.linalg.norm(cls, axis=1, keepdims=True)


def load_embedder(*, threads: int | None = None) -> OnnxEmbedder | None:
    """The model of the directory :data:`MODEL_ENV` names, or ``None`` where it is unset."""
    directory = os.environ.get(MODEL_ENV, "").strip()
    if not directory:
        return None
    return OnnxEmbedder(Path(directory), threads=threads)


def load_query_vectors() -> QueryVectors | None:
    """What `api` searches with: the model of :data:`MODEL_ENV` on one thread per query, or ``None`` where it is unset."""
    embedder = load_embedder(threads=1)
    return None if embedder is None else QueryVectors(embedder)


@cache
def background_texts(path: Path = BACKGROUND_FILE) -> tuple[str, ...]:
    """The texts of ``search_background.yaml``, checked."""
    try:
        data = read_yaml(path)
    except EntryFileError as error:
        raise ConfigError(str(error)) from None
    texts = data.get("texts") if isinstance(data, dict) and set(data) == {"texts"} else None
    if not isinstance(texts, list) or len(texts) < 10 or not all(isinstance(t, str) and t.strip() for t in texts):
        raise ConfigError(f"{path.name}: has only the key 'texts', a list of at least ten non-empty texts")
    return tuple(texts)


def vector_literal(vector: np.ndarray) -> str:
    """The text form of a vector for a parameter cast to ``halfvec``."""
    if vector.shape != (DIMENSION,) or not np.all(np.isfinite(vector)):
        raise ValueError(f"a vector has {DIMENSION} finite numbers")
    return "[" + ",".join(f"{value:.6g}" for value in vector.tolist()) + "]"


@dataclass(frozen=True, slots=True)
class QueryVector:
    """The vector of one query as a ``halfvec`` literal, the model that made it and the least cosine of a hit."""

    literal: str
    model: str
    min_cosine: float


class QueryVectors:
    """The vector of a query and its least cosine, from ``embedder`` and the background texts."""

    def __init__(self, embedder: Embedder, *, threshold: float = MIN_RELATIVE_SIMILARITY) -> None:
        self.embedder = embedder
        self.threshold = threshold
        self._background = embedder.embed(background_texts())

    def vector(self, text: str) -> QueryVector:
        (vector,) = self.embedder.embed([text])
        cosines = self._background @ vector
        min_cosine = float(cosines.mean() + self.threshold * cosines.std())
        return QueryVector(vector_literal(vector), self.embedder.name, min_cosine)

    async def vector_async(self, text: str) -> QueryVector:
        """:meth:`vector` in a thread: the model is CPU work and must not hold the event loop."""
        return await asyncio.to_thread(self.vector, text)

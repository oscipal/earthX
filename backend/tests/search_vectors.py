"""The vectors of the evaluation set without the model (adr/0026 §8.4; docs/plans/m5/m5-23-vektorsuche.md §4.6).

``fixtures/search/embeddings.json`` holds the vector of every text the vector arm embeds in the test catalogue, of
every question and of every background text, each under the SHA-256 of its text, computed by
``scripts/m5-23-embeddings.py`` with the model of the image. :class:`FixtureEmbedder` hands them out like the model
does; a text it has no vector for is a changed text, and it says how to compute them again.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from earthx.catalog.embedding import DIMENSION

EMBEDDINGS = Path(__file__).parent / "fixtures" / "search" / "embeddings.json"


class StaleEmbeddings(LookupError):
    """A text has no vector in the fixture: it changed since the vectors were computed."""


class FixtureEmbedder:
    """The model of the fixture, for the texts it has."""

    def __init__(self, path: Path = EMBEDDINGS) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["dimension"] != DIMENSION:
            raise ValueError(f"the fixture has {data['dimension']} dimensions, the index {DIMENSION}")
        self.name: str = data["model"]
        self._vectors = {
            key: np.frombuffer(base64.b64decode(value), dtype="<f4") for key, value in data["vectors"].items()
        }

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        rows = []
        for text in texts:
            vector = self._vectors.get(hashlib.sha256(text.encode("utf-8")).hexdigest())
            if vector is None:
                raise StaleEmbeddings(
                    f"no vector for the text {text[:40]!r}: compute them again with scripts/m5-23-embeddings.py"
                )
            rows.append(vector)
        return np.array(rows, dtype=np.float32).reshape(len(texts), DIMENSION)

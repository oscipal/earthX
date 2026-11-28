#!/usr/bin/env python3
"""Recompute the vectors of the evaluation set for the CI (adr/0026 §8.4; docs/plans/m5/m5-23-vektorsuche.md §4.6).

    docker compose run --rm --no-deps -v "${PWD}:/repo" -w /repo catalog-load python scripts/m5-23-embeddings.py

Runs where the embedding model is: in the image stage ``search`` (`catalog-load`, as above), or wherever
``EARTHX_EMBEDDING_MODEL`` names its directory. Reads the texts the vector arm embeds from the index of a database that
`catalog-load` has brought up to date with this checkout (``PGHOST`` and friends), the questions of
``evaluation_set.yaml`` and the background texts, and writes their vectors to
``backend/tests/fixtures/search/embeddings.json``, each under the SHA-256 of its text. Nothing else: no ids, no
database writes. The CI then searches with these vectors and never runs the model.
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path

import psycopg

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "backend")]

from earthx.catalog.embedding import DIMENSION, background_texts, embedding_text, load_embedder  # noqa: E402
from tests.search_evaluation import load_evaluation_set  # noqa: E402

FIXTURE = REPO / "backend" / "tests" / "fixtures" / "search" / "embeddings.json"


def text_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    embedder = load_embedder()
    if embedder is None:
        print("no model: set EARTHX_EMBEDDING_MODEL or run in the image stage `search`", file=sys.stderr)
        return 1
    with psycopg.connect() as conn:
        rows = conn.execute("SELECT text_a, text_b FROM public.earthx_dataset_search ORDER BY dataset_id").fetchall()
    texts = sorted(
        {embedding_text(a, b) for a, b in rows}
        | {question.text for question in load_evaluation_set().questions}
        | set(background_texts())
    )
    vectors = embedder.embed(texts)
    assert vectors.shape == (len(texts), DIMENSION)
    fixture = {
        "model": embedder.name,
        "dimension": DIMENSION,
        "vectors": {
            text_key(text): base64.b64encode(vector.astype("<f4").tobytes()).decode("ascii")
            for text, vector in zip(texts, vectors, strict=True)
        },
    }
    FIXTURE.write_text(json.dumps(fixture, indent=0, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(texts)} vectors of {embedder.name} written to {FIXTURE.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

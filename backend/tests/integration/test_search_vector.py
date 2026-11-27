"""The vector arm of the search and the embedding step of `catalog-load` (M5-23; docs/plans/m5/m5-23-vektorsuche.md §4).

The model here is a synthetic one (:class:`WordEmbedder`): each known word is a dimension of its own, words of one
meaning share it, so that "grassland" meets "savanna" without a word in common. What the real model finds is the
evaluation set's business (``test_search_evaluation.py``); here it is the SQL around it.
"""

from __future__ import annotations

import zlib
from collections.abc import Iterator, Sequence

import numpy as np
import psycopg
import pytest
from psycopg import sql

from earthx.catalog.embedding import DIMENSION, QueryVector, vector_literal
from earthx.catalog.glossary import normalize
from earthx.catalog.search import box_area, search_datasets
from earthx.catalog.search_index import (
    SearchIndexMismatch,
    check_embeddings,
    write_embeddings,
    write_listed_search_index,
    write_search_index,
)
from tests.integration.listed_rows import insert_row
from tests.integration.test_search import CATALOGUE, KENYA, SERIES, TERRAIN, _entry

pytestmark = pytest.mark.anyio

#: Words of one meaning share a dimension; every other word gets one of the dimensions from 100 on by its CRC.
MEANINGS = {"savanna": 1, "grassland": 1, "terrain": 2, "relief": 2, "multispectral": 3, "optical": 3, "neophyten": 4,
            "invasive": 4}


class WordEmbedder:
    name = "test-words@1"

    def __init__(self) -> None:
        self.calls: list[int] = []

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        self.calls.append(len(texts))
        vectors = np.zeros((len(texts), DIMENSION), dtype=np.float32)
        for row, text in enumerate(texts):
            vectors[row, 0] = 0.05
            for word in normalize(text).split():
                vectors[row, MEANINGS.get(word, 100 + zlib.crc32(word.encode()) % (DIMENSION - 100))] += 1
        return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


class Vectors:
    """What the search asks of :class:`~earthx.catalog.embedding.QueryVectors`, with a fixed least cosine."""

    def __init__(self, embedder: WordEmbedder, min_cosine: float = 0.3, model: str | None = None) -> None:
        self.embedder, self.min_cosine, self.model = embedder, min_cosine, model or embedder.name

    async def vector_async(self, text: str) -> QueryVector:
        (vector,) = self.embedder.embed([text])
        return QueryVector(vector_literal(vector), self.model, self.min_cosine)


@pytest.fixture
def embedded(require_postgres_env: None) -> Iterator[WordEmbedder]:
    """The index of the synthetic catalogue of ``test_search.py`` with a vector for every row."""
    embedder = WordEmbedder()
    with psycopg.connect(autocommit=False) as conn:
        write_search_index(conn, CATALOGUE)
        conn.commit()
        write_embeddings(conn, embedder, report=lambda _: None)
        yield embedder
        conn.execute("DELETE FROM public.earthx_dataset_search")
        conn.commit()


def _stored(dataset_id: str) -> str | None:
    with psycopg.connect() as conn:
        row = conn.execute(
            "SELECT embedding_model FROM public.earthx_dataset_search WHERE dataset_id = %s", (dataset_id,)
        ).fetchone()
    return row[0]


async def _ids(aconn, text, embedder, **kwargs) -> tuple[str, ...]:
    vectors = kwargs.pop("vectors", None) or Vectors(embedder)
    return (await search_datasets(aconn, text, vectors=vectors, **kwargs)).ids


# --- embedding in catalog-load ------------------------------------------------------------------------------------------


def test_every_row_gets_a_vector_and_a_second_run_embeds_nothing(embedded):
    assert all(_stored(config.dataset_id) == embedded.name for config in CATALOGUE)
    with psycopg.connect(autocommit=False) as conn:
        assert write_embeddings(conn, embedded, report=lambda _: None).written == 0


def test_a_new_text_loses_its_vector_and_the_next_run_gives_it_one(embedded):
    with psycopg.connect(autocommit=False) as conn:
        changed = _entry(TERRAIN, TERRAIN.dataset_id, "Terrain Alpha", ("digital terrain model", "relief"))
        write_search_index(conn, type(CATALOGUE)((changed, *(c for c in CATALOGUE if c is not TERRAIN))))
        conn.commit()
        assert _stored(TERRAIN.dataset_id) is None
        assert _stored(KENYA.dataset_id) == embedded.name
        outcome = write_embeddings(conn, embedded, report=lambda _: None)
    assert (outcome.written, outcome.missing) == (1, 1)


def test_a_row_rewritten_while_it_was_embedded_is_left_to_the_next_run(embedded):
    with psycopg.connect(autocommit=False) as conn:
        conn.execute("UPDATE public.earthx_dataset_search SET embedding = NULL, embedding_model = NULL")
        conn.commit()

        class Racing(WordEmbedder):
            def embed(self, texts):
                with psycopg.connect(autocommit=True) as other:
                    other.execute("UPDATE public.earthx_dataset_search SET text_hash = 'new' WHERE dataset_id = %s",
                                  (KENYA.dataset_id,))
                return super().embed(texts)

        write_embeddings(conn, Racing(), report=lambda _: None)
    assert _stored(KENYA.dataset_id) is None
    assert _stored(TERRAIN.dataset_id) == embedded.name


def test_each_batch_commits_so_an_interrupted_run_keeps_what_it_embedded(embedded):
    with psycopg.connect(autocommit=False) as conn:
        conn.execute("UPDATE public.earthx_dataset_search SET embedding = NULL, embedding_model = NULL")
        conn.commit()

        class Failing(WordEmbedder):
            def embed(self, texts):
                if self.calls:
                    raise RuntimeError("interrupted")
                return super().embed(texts)

        with pytest.raises(RuntimeError):
            write_embeddings(conn, Failing(), batch=2, report=lambda _: None)
        conn.rollback()
        kept = conn.execute(
            "SELECT count(*) FROM public.earthx_dataset_search WHERE embedding_model IS NOT NULL"
        ).fetchone()[0]
    assert kept == 2


def test_progress_names_counts_only(embedded, monkeypatch):
    monkeypatch.setattr("earthx.catalog.search_index._PROGRESS_EVERY", 2)
    said: list[str] = []
    with psycopg.connect(autocommit=False) as conn:
        conn.execute("UPDATE public.earthx_dataset_search SET embedding = NULL, embedding_model = NULL")
        conn.commit()
        write_embeddings(conn, embedded, batch=2, report=said.append)
    assert said == ["embeddings written: 2 of 5", "embeddings written: 4 of 5"]


async def test_the_start_check_asks_for_a_vector_of_the_model_for_every_full_entry(embedded, aconn):
    await check_embeddings(aconn, embedded.name)
    with pytest.raises(SearchIndexMismatch, match="test-kenya"):
        await aconn.execute(
            "UPDATE public.earthx_dataset_search SET embedding = NULL, embedding_model = NULL WHERE dataset_id = %s",
            (KENYA.dataset_id,),
        )
        await check_embeddings(aconn, embedded.name)
    with pytest.raises(SearchIndexMismatch, match="another-model"):
        await check_embeddings(aconn, "another-model")


# --- the vector arm ------------------------------------------------------------------------------------------------------


async def test_a_word_of_the_same_meaning_finds_what_the_lexical_arms_cannot(embedded, aconn):
    assert await search_datasets(aconn, "grassland") == await search_datasets(aconn, "grassland", vectors=None)
    assert (await search_datasets(aconn, "grassland")).ids == ()
    assert await _ids(aconn, "grassland", embedded) == (KENYA.dataset_id,)


async def test_below_the_least_cosine_nothing_counts(embedded, aconn):
    assert await _ids(aconn, "grassland", embedded, vectors=Vectors(embedded, min_cosine=0.99)) == ()
    assert await _ids(aconn, "population", embedded) == ()


async def test_both_arms_are_fused_and_counted(embedded, aconn):
    result = await search_datasets(aconn, "terrain grassland", vectors=Vectors(embedded, min_cosine=0.1))
    assert set(result.ids) >= {TERRAIN.dataset_id, KENYA.dataset_id}
    assert result.matched == len(result.ids)


async def test_the_index_way_answers_like_the_exact_one(embedded, aconn):
    for text in ("grassland", "relief", "optical imagery"):
        exact = await _ids(aconn, text, embedded)
        assert await _ids(aconn, text, embedded, exact_up_to=0) == exact


async def test_the_hard_filters_hold_in_the_vector_arm(embedded, aconn):
    far = box_area(100.0, 10.0, 101.0, 11.0)
    assert await _ids(aconn, "grassland", embedded, area=far) == ()
    assert await _ids(aconn, "grassland", embedded, area=far, exact_up_to=0) == ()
    assert await _ids(aconn, "optical", embedded) == (SERIES.dataset_id,)


async def test_rows_without_a_vector_of_the_model_are_no_hits(embedded, aconn):
    assert await _ids(aconn, "grassland", embedded, vectors=Vectors(embedded, model="another-model")) == ()
    await aconn.execute(
        "UPDATE public.earthx_dataset_search SET embedding = NULL, embedding_model = NULL WHERE dataset_id = %s",
        (KENYA.dataset_id,),
    )
    assert await _ids(aconn, "grassland", embedded) == ()


async def test_the_arm_beside_the_full_text_answers_the_same(embedded, aconn):
    async with await psycopg.AsyncConnection.connect(autocommit=True) as beside:
        for text in ("grassland", "terrain", "alpine relief"):
            assert await _ids(aconn, text, embedded, vector_conn=beside) == await _ids(aconn, text, embedded)


async def test_an_error_of_the_full_text_stops_the_arm_beside(embedded, aconn, monkeypatch):
    # The connection beside goes back to its pool after the search: no statement of the arm may still run on it.
    monkeypatch.setattr("earthx.catalog.search._full_text_sql", lambda *_, **__: sql.SQL("SELECT 1 / 0"))
    async with await psycopg.AsyncConnection.connect(autocommit=True) as beside:
        with pytest.raises(psycopg.errors.DivisionByZero):
            await _ids(aconn, "grassland", embedded, vector_conn=beside)
        assert beside.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
        assert (await (await beside.execute("SELECT 1")).fetchone()) == (1,)


@pytest.fixture
def listed_embedded(embedded: WordEmbedder) -> Iterator[WordEmbedder]:
    with psycopg.connect() as conn:
        conn.execute("DELETE FROM public.earthx_listed_entry")
        insert_row(conn, "neophytes", title="Neophyten der Schweiz", bbox=(6.0, 45.8, 10.5, 47.8))
        insert_row(conn, "in-review", state="in_review", title="Neophyten im Kanton")
        write_listed_search_index(conn, [config.dataset_id for config in CATALOGUE])
        conn.commit()
        write_embeddings(conn, embedded, report=lambda _: None)
        yield embedded
        conn.execute("DELETE FROM public.earthx_listed_entry")
        conn.commit()


async def test_a_listed_entry_is_found_by_meaning_and_only_while_published(listed_embedded, aconn):
    result = await search_datasets(aconn, "invasive", vectors=Vectors(listed_embedded))
    assert (result.ids, result.listed) == (("neophytes",), frozenset({"neophytes"}))
    assert await _ids(aconn, "invasive", listed_embedded, exact_up_to=0) == ("neophytes",)
    await aconn.execute("UPDATE public.earthx_listed_entry SET state = 'link_hidden' WHERE dataset_id = 'neophytes'")
    assert await _ids(aconn, "invasive", listed_embedded) == ()

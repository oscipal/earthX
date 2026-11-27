"""The evaluation set against the lexical arm (M5-22 plan §3.1, §4; adr/0026 §8.4). Run with ``-s`` for the report.

The registry is written into the index of this worker's database and every active question is put to
:func:`~earthx.catalog.search.search_datasets` with its text, its box and its period, nothing else. Binding from M5-22b
(F3): every filter question, at most one failing negative question (A9), and Recall@5 and MRR@10 per language at least
what this arm measured (a ratchet: the floors only move up). The pass mark of adr/0026 F5 binds from M5-23 on, for
the search with its vector arm: the vectors come from ``fixtures/search/embeddings.json``, never from the model
(adr/0026 §8.4; docs/plans/m5/m5-23-vektorsuche.md §4.6).
"""

from __future__ import annotations

from datetime import UTC, datetime, time

import psycopg
import pytest

from earthx.catalog.embedding import QueryVectors
from earthx.catalog.listed import load_listed
from earthx.catalog.search import JOINING, Joining, box_area, search_datasets
from earthx.catalog.search_index import write_embeddings
from tests.catalog.entries import REGISTRY
from tests.integration.conftest import Catalogue as CatalogueState
from tests.search_evaluation import (
    ADR_0026_F5,
    LANGUAGES,
    Catalogue,
    Evaluation,
    PassMark,
    Query,
    evaluate,
    load_evaluation_set,
    report,
    shortfalls,
)
from tests.search_vectors import FixtureEmbedder

pytestmark = pytest.mark.anyio

#: Measured on 11.11.2026 with the six entries of the registry (M5-22b): German 8 of 11 questions in the first five
#: and on the first rank, English all of 10; on 14.11.2026 with Q34 and Q35 active (M5-10) German 9 of 12, English
#: all of 11. On 23.11.2026 the hand entries CLC and LS woke Q13–Q16, Q45 and Q46 (M5-42 F7): German 15 of 19 in
#: the first five, English 41/42 because "land cover classification" (Q14) does not reach CORINE, which lacks the word
#: "classification"; the vector arm (M5-23) is to close it. With Q53-Q56 (M5-23, broad words) German 17 of 21 and
#: English 47/48: the four new ones are on the first rank but Q54 "water" (WorldCover second), the old ones unchanged.
#: Raise them when the search gets better; never lower them for the same questions.
RATCHET = {"de": (17 / 21, 33 / 42), "en": (47 / 48, 15 / 16)}


#: The hand entries of `catalog/listed/` (M5-17), which `catalog-load` publishes and indexes (M5-42 F7 = 1).
HAND_ENTRIES = tuple(entry.dataset_id for entry, _ in load_listed())


@pytest.fixture
def registry_index(catalogue_state: CatalogueState) -> None:
    """The index as `catalog-load` writes it: the registry and the hand entries of `catalog/listed/`."""
    catalogue_state.ensure()


async def _evaluate(
    aconn: psycopg.AsyncConnection,
    joining: Joining,
    *,
    vectors: QueryVectors | None = None,
    vector_conn: psycopg.AsyncConnection | None = None,
) -> Evaluation:
    evaluation_set = load_evaluation_set()
    answers: dict[Query, tuple[str, ...]] = {}
    for question in evaluation_set.questions:
        query = Query.of(question)
        area = None if query.aoi is None else box_area(*query.aoi.bbox)
        period = (
            None
            if query.period is None
            else (
                datetime.combine(query.period[0], time.min, UTC),
                datetime.combine(query.period[1], time.max, UTC),
            )
        )
        result = await search_datasets(
            aconn, query.text, area=area, period=period, joining=joining, vectors=vectors, vector_conn=vector_conn
        )
        answers[query] = result.ids
    return evaluate(evaluation_set, Catalogue.of(REGISTRY, HAND_ENTRIES), answers.__getitem__)


async def test_the_lexical_arm_holds_the_ratchet(registry_index, aconn):
    evaluation = await _evaluate(aconn, Joining.KNOWN)
    print("\n" + report(evaluation))
    # Every filter question and three of four negative questions (F3, A9); the measures have their own floors below.
    assert shortfalls(evaluation, PassMark(recall_at_5=0.0, mrr_at_10=0.0)) == []
    for language in LANGUAGES:
        measures = evaluation.measures(language)
        recall, mrr = RATCHET[language]
        assert measures.recall_at_5 >= recall - 1e-9, (language, measures)
        assert measures.mrr_at_10 >= mrr - 1e-9, (language, measures)
    # Otto, 11.11.2026 (plan §12.5): a resolution after a name keeps WorldCover among the first five.
    (esa_10_m,) = [o for o in evaluation.active if o.question.id == "Q52"]
    assert esa_10_m.recall == 1.0, esa_10_m.hits


@pytest.mark.parametrize("joining", list(Joining))
async def test_each_joining_passes_the_filter_questions(registry_index, aconn, joining):
    # The three candidates of F2, measured in the PR; each keeps every hard filter.
    evaluation = await _evaluate(aconn, joining)
    assert all(not outcome.never_hits for outcome in evaluation.filters)


@pytest.fixture
def fixture_vectors(registry_index) -> QueryVectors:
    """The index with the vectors of the fixture, as `catalog-load` writes them with the model of the image."""
    embedder = FixtureEmbedder()
    with psycopg.connect(autocommit=False) as conn:
        write_embeddings(conn, embedder, report=lambda _: None)
    return QueryVectors(embedder)


async def test_the_hybrid_search_passes_adr_0026_f5(fixture_vectors, aconn):
    evaluation = await _evaluate(aconn, JOINING, vectors=fixture_vectors)
    print("\n" + report(evaluation))
    assert shortfalls(evaluation, ADR_0026_F5) == []


async def test_the_vector_arm_beside_the_full_text_answers_the_same(fixture_vectors, aconn):
    # M5-66 F4: the arms at the same time, on two connections; the answers are those of one after the other.
    after = await _evaluate(aconn, JOINING, vectors=fixture_vectors)
    async with await psycopg.AsyncConnection.connect(autocommit=True) as beside:
        at_once = await _evaluate(aconn, JOINING, vectors=fixture_vectors, vector_conn=beside)
    assert [o.hits for o in at_once.outcomes] == [o.hits for o in after.outcomes]

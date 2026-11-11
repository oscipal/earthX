"""The evaluation set against the lexical arm (M5-22 plan §3.1, §4; adr/0026 §8.4). Run with ``-s`` for the report.

The registry is written into the index of this worker's database and every active question is put to
:func:`~earthx.catalog.search.search_datasets` with its text, its box and its period, nothing else. Binding from M5-22b
(F3): every filter question, at most one failing negative question (A9), and Recall@5 and MRR@10 per language at least
what this arm measured (a ratchet: the floors only move up). The pass mark of adr/0026 F5 binds from M5-23.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, time

import psycopg
import pytest

from earthx.catalog.search import Joining, box_area, search_datasets
from earthx.catalog.search_index import write_search_index
from tests.catalog.entries import REGISTRY
from tests.search_evaluation import (
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

pytestmark = pytest.mark.anyio

#: Measured on 11.11.2026 with the six entries of the registry (M5-22b): German 8 of 11 questions in the first five
#: and on the first rank, English all of 10. Raise them when the search gets better; never lower them.
RATCHET = {"de": (8 / 11, 8 / 11), "en": (1.0, 1.0)}


@pytest.fixture
def registry_index(require_postgres_env: None) -> Iterator[None]:
    with psycopg.connect(autocommit=True) as conn:
        write_search_index(conn, REGISTRY)
        yield
        conn.execute("DELETE FROM public.earthx_dataset_search")


async def _evaluate(aconn: psycopg.AsyncConnection, joining: Joining) -> Evaluation:
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
        answers[query] = (await search_datasets(aconn, query.text, area=area, period=period, joining=joining)).ids
    return evaluate(evaluation_set, Catalogue.of(REGISTRY), answers.__getitem__)


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


@pytest.mark.parametrize("joining", list(Joining))
async def test_each_joining_passes_the_filter_questions(registry_index, aconn, joining):
    # The three candidates of F2, measured in the PR; each keeps every hard filter.
    evaluation = await _evaluate(aconn, joining)
    assert all(not outcome.never_hits for outcome in evaluation.filters)

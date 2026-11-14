"""The evaluation set of the dataset search and its evaluator (docs/plans/m5/m5-22-suche-lexikalisch.md §3.1, §4).

Three parts: the fixture keeps the shape of adr/0026 §8.3 (ids, languages, kinds, context; the cells were compared
with the ADR once in review, M5-22a); the measures follow §8.1 on a synthetic catalogue; and the zero point, the set put to a search that finds nothing over the catalogue of the registry (adr/0026 §6 step 1). Run with
``-s`` to see the report.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from tests.catalog.entries import REGISTRY
from tests.search_evaluation import (
    ADR_0026_F5,
    Catalogue,
    EvaluationSetError,
    Outcome,
    PassMark,
    Question,
    evaluate,
    load_evaluation_set,
    report,
    shortfalls,
)

# adr/0026 §8.1: bare names and abbreviations count only over both languages; Q51, Q52 from M5-22c (plan §12).
NAME_ONLY = {"Q01", "Q03", "Q04", "Q05", "Q07", "Q40", "Q42", "Q43", "Q44", "Q46", "Q51", "Q52"}


# --- the fixture -------------------------------------------------------------------------------------------------------


def test_the_set_holds_the_fifty_questions_of_the_adr_and_two_of_m5_22c():
    questions = load_evaluation_set().questions
    assert [q.id for q in questions] == [f"Q{n:02d}" for n in range(1, 53)]
    assert sum(q.language == "de" for q in questions) == 25
    assert sum(q.language == "en" for q in questions) == 27
    assert {q.id for q in questions if q.kind == "0"} == {"Q47", "Q48", "Q49", "Q50", "Q51"}
    assert {q.id for q in questions if q.name_only} == NAME_ONLY
    assert {q.id: q.requires for q in questions if q.requires} == {"Q34": "terrain", "Q35": "terrain"}


def test_the_filter_questions_carry_their_box_or_period():
    questions = {q.id: q for q in load_evaluation_set().questions}
    assert questions["Q26"].aoi.bbox == (14, 47, 15, 48)
    assert questions["Q29"].aoi == questions["Q26"].aoi
    assert questions["Q27"].aoi.bbox == (7, 46, 8, 47)
    assert questions["Q28"].aoi.bbox == (36, -1, 37, 0)
    assert [str(day) for day in questions["Q32"].period] == ["2000-01-01", "2005-12-31"]
    assert [str(day) for day in questions["Q33"].period] == ["2024-01-01", "2024-12-31"]
    assert questions["Q32"].never == {"sentinel-1-grd"}


def test_every_fixed_id_is_in_the_registry():
    # A renamed entry would otherwise make its questions rest without anyone noticing.
    for ref in load_evaluation_set().datasets:
        if ref.id is not None and not ref.provisional:
            assert ref.id in REGISTRY, ref.short_name


def test_a_provisional_id_is_not_in_the_registry_yet():
    # Once the entry arrives, drop `provisional` or correct the id; otherwise its questions rest on a wrong id.
    for ref in load_evaluation_set().datasets:
        if ref.provisional:
            assert ref.id not in REGISTRY, f"{ref.short_name}: {ref.id} is in the registry now"


# --- the zero point ----------------------------------------------------------------------------------------------------


def test_zero_point_without_a_search():
    # The numbers of plan §3.1 and §10 for the six entries of the registry, with Q51 (§12) one more negative question
    # and Q52 one more over both languages; a new entry changes them on purpose.
    evaluation = evaluate(load_evaluation_set(), Catalogue.of(REGISTRY), lambda query: [])
    print("\n" + report(evaluation))
    assert (len(evaluation.active), len(evaluation.resting)) == (38, 14)
    assert [evaluation.measures(language).questions for language in ("de", "en", "all")] == [11, 10, 31]
    overall = evaluation.measures()
    assert (overall.recall_at_5, overall.mrr_at_10, overall.ndcg_at_10) == (0.0, 0.0, 0.0)
    assert sorted(o.question.id for o in evaluation.filters) == ["Q27", "Q28", "Q29", "Q32"]
    assert all(not o.never_hits for o in evaluation.filters)
    assert len(evaluation.negatives) == 5 and all(not o.hits for o in evaluation.negatives)
    assert shortfalls(evaluation, ADR_0026_F5) == [
        "de: Recall@5 0.000 below 0.9",
        "de: MRR@10 0.000 below 0.8",
        "en: Recall@5 0.000 below 0.9",
        "en: MRR@10 0.000 below 0.8",
    ]


# --- measures on a synthetic catalogue ---------------------------------------------------------------------------------

# Z has an id but is not loaded, like BEV today; N has no id yet, like MeteoSchweiz.
CATALOGUE = Catalogue({"a": frozenset(), "b": frozenset(), "c": frozenset({"terrain"}), "x": frozenset()})


def _set(tmp_path: Path, questions: list[dict], datasets: dict | None = None) -> Path:
    data = {
        "datasets": datasets
        or {
            "A": {"id": "a"},
            "B": {"id": "b"},
            "C": {"id": "c"},
            "X": {"id": "x"},
            "Z": {"id": "z"},
            "N": {"id": None},
        },
        "questions": questions,
    }
    path = tmp_path / "set.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _q(qid: str = "Q1", language: str = "en", kind: str = "T", **fields) -> dict:
    return {"id": qid, "language": language, "text": f"text of {qid}", "kind": kind, **fields}


def _run(tmp_path, questions, answers, catalogue=CATALOGUE):
    """``answers`` by question id; the search itself sees only the text (``text of Q1``)."""
    evaluation_set = load_evaluation_set(_set(tmp_path, questions))
    return evaluate(evaluation_set, catalogue, lambda query: answers.get(query.text.removeprefix("text of "), []))


def test_recall_counts_the_wanted_among_the_first_five(tmp_path):
    evaluation = _run(tmp_path, [_q(grade_2=["A", "B"])], {"Q1": ["a", "x", "c"]})
    assert evaluation.measures().recall_at_5 == 0.5


def test_a_wanted_dataset_on_rank_six_misses_recall_but_counts_for_the_rank():
    question = Question(
        id="Q1",
        language="en",
        text="w",
        kind="T",
        grade_2=frozenset({"f"}),
        grade_1=frozenset(),
        never=frozenset(),
        wanted=("F",),
        unwanted=(),
    )
    outcome = Outcome(question, True, ("1", "2", "3", "4", "5", "f"), frozenset({"f"}), frozenset("12345f"))
    assert outcome.recall == 0.0
    assert outcome.reciprocal_rank == pytest.approx(1 / 6)
    others = tuple(f"h{n}" for n in range(10))
    beyond = Outcome(question, True, (*others, "f"), frozenset({"f"}), frozenset((*others, "f")))
    assert beyond.reciprocal_rank == 0.0


def test_mrr_takes_the_first_wanted_hit(tmp_path):
    evaluation = _run(tmp_path, [_q(grade_2=["A", "B"])], {"Q1": ["x", "c", "b", "a"]})
    assert evaluation.measures().mrr_at_10 == pytest.approx(1 / 3)


def test_ndcg_is_one_for_the_ideal_order_and_less_when_grade_one_leads(tmp_path):
    # Grade 2 on `b`, grade 1 on `a`: the ideal list sorts by grade, not by id.
    questions = [_q(grade_2=["B"], grade_1=["A"])]
    assert _run(tmp_path, questions, {"Q1": ["b", "a"]}).measures().ndcg_at_10 == pytest.approx(1.0)
    assert _run(tmp_path, questions, {"Q1": ["a", "b"]}).measures().ndcg_at_10 < 1.0


@pytest.mark.parametrize("absent", ["Z", "N"])
def test_graded_datasets_outside_the_catalogue_count_neither_for_recall_nor_for_the_ideal(tmp_path, absent):
    evaluation = _run(tmp_path, [_q(grade_2=["A", absent], grade_1=["Z"] if absent == "N" else [])], {"Q1": ["a"]})
    assert evaluation.measures().recall_at_5 == 1.0
    assert evaluation.measures().ndcg_at_10 == pytest.approx(1.0)


def test_a_question_rests_while_no_wanted_dataset_is_in_the_catalogue(tmp_path):
    asked = []
    evaluation_set = load_evaluation_set(_set(tmp_path, [_q(grade_2=["N"])]))
    evaluation = evaluate(evaluation_set, CATALOGUE, lambda query: asked.append(query) or [])
    assert not asked and len(evaluation.resting) == 1
    assert evaluation.measures().questions == 0
    with pytest.raises(ValueError, match="no recall"):
        _ = evaluation.outcomes[0].recall


def test_a_question_rests_while_its_wanted_dataset_has_an_id_but_is_not_loaded(tmp_path):
    assert len(_run(tmp_path, [_q(grade_2=["Z"], grade_1=["A"])], {}).resting) == 1


def test_a_question_rests_until_its_capability_is_offered(tmp_path):
    questions = [_q(grade_2=["A"], requires="terrain")]
    assert len(_run(tmp_path, questions, {}, Catalogue({"a": frozenset()})).resting) == 1
    assert len(_run(tmp_path, questions, {}).active) == 1


def test_questions_without_grade_two_are_always_active(tmp_path):
    questions = [_q("Q1", kind="0"), _q("Q2", kind="R", never=["N"]), _q("Q3", kind="Z", never=["A"], requires="radar")]
    evaluation = _run(tmp_path, questions, {})
    assert len(evaluation.active) == 3
    assert len(evaluation.negatives) == 1 and len(evaluation.filters) == 2


def test_the_search_sees_text_and_context_but_no_grade(tmp_path):
    asked = []
    evaluation_set = load_evaluation_set(
        _set(
            tmp_path, [_q(grade_2=["A"], never=["X"], aoi={"name": "box", "bbox": [7, 46, 8, 47]}, years=[2020, 2021])]
        )
    )
    evaluate(evaluation_set, CATALOGUE, lambda query: asked.append(query) or [])
    (query,) = asked
    assert (query.text, query.aoi.bbox, [d.year for d in query.period]) == ("text of Q1", (7, 46, 8, 47), [2020, 2021])
    assert not hasattr(query, "grade_2") and not hasattr(query, "never")


def test_bare_names_count_only_over_both_languages(tmp_path):
    questions = [
        _q("Q1", "de", grade_2=["A"]),
        _q("Q2", "en", grade_2=["A"]),
        _q("Q3", "en", grade_2=["A"], name_only=True),
    ]
    evaluation = _run(tmp_path, questions, {"Q1": ["a"], "Q2": ["x", "a"], "Q3": []})
    assert evaluation.measures("de").mrr_at_10 == 1.0
    assert evaluation.measures("en").questions == 1 and evaluation.measures("en").mrr_at_10 == 0.5
    assert evaluation.measures().questions == 3 and evaluation.measures().mrr_at_10 == pytest.approx(0.5)


def test_a_language_without_questions_has_no_measure_and_misses_the_mark(tmp_path):
    evaluation = _run(tmp_path, [_q("Q1", "de", grade_2=["A"])], {"Q1": ["a"]})
    assert evaluation.measures("en").recall_at_5 is None
    assert shortfalls(evaluation, ADR_0026_F5) == ["en: no active question to measure"]
    with pytest.raises(ValueError):
        evaluation.measures("fr")


def test_a_never_dataset_fails_its_filter_question_on_any_rank(tmp_path):
    questions = [_q("Q1", "de", grade_2=["A"]), _q("Q2", "en", grade_2=["B"], never=["X"])]
    evaluation = _run(tmp_path, questions, {"Q1": ["a"], "Q2": ["b", "c", "x"]})
    assert shortfalls(evaluation, PassMark(0.0, 0.0)) == ["Q2: lists x"]


def test_one_negative_question_may_fail_two_may_not(tmp_path):
    graded = [_q("Q1", "de", grade_2=["A"]), _q("Q2", "en", grade_2=["A"])]
    negatives = [_q(f"Q{n}", kind="0") for n in range(3, 7)]
    answers = {"Q1": ["a"], "Q2": ["a"], "Q3": ["x"]}
    assert shortfalls(_run(tmp_path, graded + negatives, answers), ADR_0026_F5) == []
    answers["Q4"] = ["b"]
    assert shortfalls(_run(tmp_path, graded + negatives, answers), ADR_0026_F5) == [
        "negative questions with hits: Q3, Q4"
    ]


@pytest.mark.parametrize("answer, message", [(["a", "a"], "Q1: .* twice"), (["a", "z"], "Q1: .* outside .*: z")])
def test_a_search_that_answers_twice_or_outside_the_catalogue_is_an_error(tmp_path, answer, message):
    with pytest.raises(ValueError, match=message):
        _run(tmp_path, [_q(grade_2=["A"])], {"Q1": answer})


def test_the_report_names_each_question_and_why_it_rests(tmp_path):
    questions = [_q("Q1", grade_2=["A", "B"]), _q("Q2", grade_2=["N"]), _q("Q3", grade_2=["A"], requires="radar")]
    text = report(_run(tmp_path, questions, {"Q1": ["b"]}))
    assert "Q1 en a@- b@1" in text
    assert "Q2 en resting: no dataset of grade 2 in the catalogue" in text
    assert "Q3 en resting: requires radar" in text


# --- malformed sets ----------------------------------------------------------------------------------------------------

VALID = {"datasets": {"A": {"id": "a"}, "N": {"id": None}}, "questions": [_q(grade_2=["A"])]}
# A key to take out of the question instead of setting.
_DROP = object()


def _break_question(**changes):
    def apply(data):
        question = data["questions"][0]
        for key, value in changes.items():
            if value is _DROP:
                del question[key]
            else:
                question[key] = value

    return apply


def _set_key(path, value):
    def apply(data):
        target = data
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value

    return apply


@pytest.mark.parametrize(
    "change, message",
    [
        (_set_key(("extra",), 1), "exactly the keys"),
        (_set_key(("questions",), []), "non-empty list"),
        (_set_key(("datasets", "B"), {"id": "a"}), "share one dataset id"),
        (_set_key(("datasets", "P"), {"id": "proto-x"}), "prototype"),
        (_set_key(("datasets", "P"), {"id": None, "provisional": True}), "needs an id"),
        (_set_key(("datasets", "P"), {"name": "p"}), "has 'id'"),
        (_break_question(colour="red"), "unknown keys"),
        (_break_question(text=_DROP), "missing keys"),
        (_break_question(text="  "), "'text' is a non-empty text"),
        (_break_question(language="fr"), "'language'"),
        (_break_question(kind="Q"), "'kind'"),
        (_break_question(kind=["N"]), "'kind'"),
        (_break_question(grade_2=["Z"]), "does not list"),
        (_break_question(grade_2=["A", "A"]), "twice"),
        (_break_question(grade_1=["A"]), "more than one grade"),
        (_break_question(kind="0"), "grades no dataset"),
        (_break_question(grade_2=_DROP), "grade 2 or checks a filter"),
        (_break_question(name_only="yes"), "'name_only' is a boolean"),
        (_break_question(requires="ter rain"), "names one capability"),
        (_break_question(aoi={"name": "x", "bbox": [7.0, 46, 8, 47]}), "whole degrees"),
        (_break_question(aoi={"name": "x", "bbox": [8, 46, 7, 47]}), "west to east"),
        (_break_question(aoi={"bbox": [7, 46, 8, 47]}), "'name' and a 'bbox'"),
        (_break_question(years=[2005, 2000]), "first to the last"),
        (_break_question(years=[2000]), "whole years"),
    ],
)
def test_a_malformed_set_is_refused_with_the_rule(tmp_path, change, message):
    data = copy.deepcopy(VALID)
    change(data)
    path = tmp_path / "set.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    with pytest.raises(EvaluationSetError, match=message):
        load_evaluation_set(path)


def test_a_duplicate_question_id_is_refused(tmp_path):
    data = copy.deepcopy(VALID)
    data["questions"].append(copy.deepcopy(data["questions"][0]))
    path = tmp_path / "set.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    with pytest.raises(EvaluationSetError, match="appears twice"):
        load_evaluation_set(path)


def test_a_yaml_boolean_word_stays_text(tmp_path):
    # The strict loader of the registry (M5-13 A1): `yes` is not a boolean, so it fails as one.
    path = tmp_path / "set.yaml"
    path.write_text(
        "datasets: {A: {id: a}}\nquestions:\n- {id: Q1, language: en, text: w, kind: T, grade_2: [A], name_only: yes}\n",
        encoding="utf-8",
    )
    with pytest.raises(EvaluationSetError, match="'name_only' is a boolean"):
        load_evaluation_set(path)

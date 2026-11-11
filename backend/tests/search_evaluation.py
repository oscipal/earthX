"""The evaluation set of the dataset search and its measures (adr/0026 §8, docs/plans/m5/m5-22-suche-lexikalisch.md §3.1).

:func:`load_evaluation_set` reads ``fixtures/search/evaluation_set.yaml`` strictly, :func:`evaluate` puts every active
question to a search and measures the answers, :func:`shortfalls` compares the measures with a pass mark, and
:func:`report` writes them out per question. The search is any callable from a question to the ranked dataset ids;
M5-22a measures the zero point (no search), M5-22b the lexical arm, M5-23 the hybrid.

Rules of §8.1:

* A question is **active** once at least one dataset of grade 2 is in the catalogue and its requirement holds; a
  question without grade 2 (filter-only and negative questions) is always active. Measured only against datasets in
  the catalogue.
* **Recall@5:** the share of the grade-2 datasets among the first five hits; **MRR@10:** the reciprocal rank of the
  first grade-2 dataset among the first ten; **nDCG@10** with gains 2 and 1, reported only. Each averaged over the
  active questions with grade 2.
* A **filter question** (one with ``never``) passes when no such dataset is in the list, at any rank; a **negative
  question** (kind ``0``) passes when the list is empty.
* Per language only questions with at least one word of it; bare names (``name_only``) count only over both.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from earthx.catalog.entry_files import read_yaml
from earthx.catalog.registry import PROTOTYPE_PREFIX, DatasetRegistry

EVALUATION_SET = Path(__file__).parent / "fixtures" / "search" / "evaluation_set.yaml"

LANGUAGES = ("de", "en")
ALL = "all"
KINDS = frozenset({"N", "T", "X", "R", "Z", "F", "S", "K", "0"})
NEGATIVE = "0"

RECALL_AT = 5
RANK_AT = 10


class EvaluationSetError(ValueError):
    """The evaluation set breaks a rule of adr/0026 §8.1 or of its own format."""


@dataclass(frozen=True, slots=True)
class Aoi:
    name: str
    #: west, south, east, north in whole degrees (§8.1: a coarse box, never a user's area).
    bbox: tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class Question:
    id: str
    language: str
    text: str
    kind: str
    #: Dataset ids by grade; a short name without an id (``null`` in the file) is left out.
    grade_2: frozenset[str]
    grade_1: frozenset[str]
    never: frozenset[str]
    #: Short names of grade 2 and of ``never`` as written: a question whose datasets have no id yet is still one with
    #: grade 2, or still a filter question.
    wanted: tuple[str, ...]
    unwanted: tuple[str, ...]
    name_only: bool = False
    aoi: Aoi | None = None
    #: First and last day of the period, from whole years.
    period: tuple[date, date] | None = None
    #: A capability that some dataset in the catalogue has to offer (e.g. ``terrain``, M5-10).
    requires: str | None = None

    def grade(self, dataset_id: str) -> int:
        return 2 if dataset_id in self.grade_2 else 1 if dataset_id in self.grade_1 else 0


@dataclass(frozen=True, slots=True)
class DatasetRef:
    short_name: str
    id: str | None
    provisional: bool


@dataclass(frozen=True, slots=True)
class EvaluationSet:
    datasets: tuple[DatasetRef, ...]
    questions: tuple[Question, ...]


@dataclass(frozen=True, slots=True)
class Catalogue:
    """What the measures need from the loaded catalogue: the dataset ids and the capabilities each offers."""

    capabilities: Mapping[str, frozenset[str]]

    @classmethod
    def of(cls, registry: DatasetRegistry) -> Catalogue:
        return cls(
            {
                entry.dataset_id: frozenset(
                    name for name, value in vars_of(entry.capabilities).items() if value is True
                )
                for entry in registry
            }
        )

    def __contains__(self, dataset_id: object) -> bool:
        return dataset_id in self.capabilities

    def offers(self, capability: str) -> bool:
        return any(capability in offered for offered in self.capabilities.values())


def vars_of(obj: object) -> dict[str, Any]:
    """The fields of a dataclass with ``slots`` or without, by name."""
    names = getattr(obj, "__dataclass_fields__", None)
    if names is None:
        raise TypeError(f"{type(obj).__name__} is not a dataclass")
    return {name: getattr(obj, name) for name in names}


# --- reading -----------------------------------------------------------------------------------------------------------

_QUESTION_KEYS = frozenset(
    {"id", "language", "text", "kind", "grade_2", "grade_1", "never", "name_only", "aoi", "years", "requires"}
)
_REQUIRED_QUESTION_KEYS = frozenset({"id", "language", "text", "kind"})


def load_evaluation_set(path: Path = EVALUATION_SET) -> EvaluationSet:
    """The set in ``path``, checked against the rules of §8.1; :class:`EvaluationSetError` names the question and the rule."""
    data = read_yaml(path)
    if not isinstance(data, dict) or set(data) != {"datasets", "questions"}:
        raise EvaluationSetError("the set has exactly the keys 'datasets' and 'questions'")
    datasets = _read_datasets(data["datasets"])
    ids = {ref.short_name: ref.id for ref in datasets}
    if not isinstance(data["questions"], list) or not data["questions"]:
        raise EvaluationSetError("'questions' is a non-empty list")
    questions = tuple(_read_question(raw, ids) for raw in data["questions"])
    seen: set[str] = set()
    for question in questions:
        if question.id in seen:
            raise EvaluationSetError(f"{question.id}: the id appears twice")
        seen.add(question.id)
    return EvaluationSet(datasets, questions)


def _read_datasets(raw: object) -> tuple[DatasetRef, ...]:
    if not isinstance(raw, dict) or not raw:
        raise EvaluationSetError("'datasets' maps each short name to its id")
    refs = []
    for short_name, entry in raw.items():
        if not isinstance(entry, dict) or not set(entry) <= {"id", "provisional"} or "id" not in entry:
            raise EvaluationSetError(f"dataset {short_name}: has 'id' and at most 'provisional'")
        dataset_id, provisional = entry["id"], entry.get("provisional", False)
        if dataset_id is not None and (not isinstance(dataset_id, str) or not dataset_id):
            raise EvaluationSetError(f"dataset {short_name}: the id is a non-empty text or null")
        if not isinstance(provisional, bool) or (provisional and dataset_id is None):
            raise EvaluationSetError(f"dataset {short_name}: 'provisional' is a boolean and needs an id")
        if dataset_id is not None and dataset_id.startswith(PROTOTYPE_PREFIX):
            raise EvaluationSetError(f"dataset {short_name}: no prototype dataset in the set (adr/0024 R7)")
        refs.append(DatasetRef(short_name, dataset_id, provisional))
    taken = [ref.id for ref in refs if ref.id is not None]
    if len(taken) != len(set(taken)):
        raise EvaluationSetError("two short names share one dataset id")
    return tuple(refs)


def _read_question(raw: object, ids: Mapping[str, str | None]) -> Question:
    if not isinstance(raw, dict):
        raise EvaluationSetError("each question is a mapping")
    qid = raw.get("id")
    name = qid if isinstance(qid, str) else "a question"
    unknown, missing = set(raw) - _QUESTION_KEYS, _REQUIRED_QUESTION_KEYS - set(raw)
    if unknown or missing:
        raise EvaluationSetError(f"{name}: unknown keys {sorted(unknown)}, missing keys {sorted(missing)}")
    for key in ("id", "text"):
        if not isinstance(raw[key], str) or not raw[key].strip():
            raise EvaluationSetError(f"{name}: '{key}' is a non-empty text")
    if raw["language"] not in LANGUAGES:
        raise EvaluationSetError(f"{name}: 'language' is one of {', '.join(LANGUAGES)}")
    if raw["kind"] not in KINDS:
        raise EvaluationSetError(f"{name}: 'kind' is one of {', '.join(sorted(KINDS))}")
    grades = {key: _short_names(raw.get(key, []), name, key, ids) for key in ("grade_2", "grade_1", "never")}
    every = [short for names in grades.values() for short in names]
    if len(every) != len(set(every)):
        raise EvaluationSetError(f"{name}: a dataset has more than one grade")
    if raw["kind"] == NEGATIVE and every:
        raise EvaluationSetError(f"{name}: a negative question grades no dataset")
    if raw["kind"] != NEGATIVE and not grades["grade_2"] and not grades["never"]:
        raise EvaluationSetError(f"{name}: wants a dataset of grade 2 or checks a filter with 'never'")
    name_only = raw.get("name_only", False)
    if not isinstance(name_only, bool):
        raise EvaluationSetError(f"{name}: 'name_only' is a boolean")
    requires = raw.get("requires")
    if requires is not None and (not isinstance(requires, str) or not requires.isidentifier()):
        raise EvaluationSetError(f"{name}: 'requires' names one capability")

    def ids_of(key: str) -> frozenset[str]:
        return frozenset(i for i in (ids[short] for short in grades[key]) if i is not None)

    return Question(
        id=qid,
        language=raw["language"],
        text=raw["text"],
        kind=raw["kind"],
        grade_2=ids_of("grade_2"),
        grade_1=ids_of("grade_1"),
        never=ids_of("never"),
        wanted=grades["grade_2"],
        unwanted=grades["never"],
        name_only=name_only,
        aoi=_read_aoi(raw.get("aoi"), name),
        period=_read_years(raw.get("years"), name),
        requires=requires,
    )


def _short_names(raw: object, name: str, key: str, ids: Mapping[str, str | None]) -> tuple[str, ...]:
    if not isinstance(raw, list) or not all(isinstance(short, str) for short in raw):
        raise EvaluationSetError(f"{name}: '{key}' is a list of short names")
    for short in raw:
        if short not in ids:
            raise EvaluationSetError(f"{name}: '{key}' names {short}, which 'datasets' does not list")
    if len(raw) != len(set(raw)):
        raise EvaluationSetError(f"{name}: '{key}' names a dataset twice")
    return tuple(raw)


def _read_aoi(raw: object, name: str) -> Aoi | None:
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) != {"name", "bbox"} or not isinstance(raw["name"], str):
        raise EvaluationSetError(f"{name}: 'aoi' has a 'name' and a 'bbox'")
    box = raw["bbox"]
    # Whole degrees only (§8.1): a float, even 7.0, is refused, so that no exact area slips in.
    if not isinstance(box, list) or len(box) != 4 or not all(type(v) is int for v in box):
        raise EvaluationSetError(f"{name}: 'aoi.bbox' is four whole degrees [west, south, east, north]")
    west, south, east, north = box
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise EvaluationSetError(f"{name}: 'aoi.bbox' is not a box west to east and south to north")
    return Aoi(raw["name"], (west, south, east, north))


def _read_years(raw: object, name: str) -> tuple[date, date] | None:
    if raw is None:
        return None
    if not isinstance(raw, list) or len(raw) != 2 or not all(type(v) is int for v in raw):
        raise EvaluationSetError(f"{name}: 'years' is [first, last] in whole years")
    first, last = raw
    if not 1900 <= first <= last <= 2100:
        raise EvaluationSetError(f"{name}: 'years' runs from the first to the last year, 1900 to 2100")
    return date(first, 1, 1), date(last, 12, 31)


# --- measuring ---------------------------------------------------------------------------------------------------------

Search = Callable[[Question], Sequence[str]]


@dataclass(frozen=True, slots=True)
class Outcome:
    """One question put to the search."""

    question: Question
    active: bool
    #: The answer, in rank order; empty for a resting question.
    hits: tuple[str, ...]
    #: Grade-2 datasets of the catalogue, the base of recall and rank.
    wanted: frozenset[str]
    #: Every dataset of the catalogue: the ideal list of nDCG holds only these.
    catalogued: frozenset[str]

    @property
    def measured(self) -> bool:
        """Counts in Recall@5, MRR@10 and nDCG@10."""
        return self.active and bool(self.wanted)

    @property
    def recall(self) -> float:
        return len(self.wanted & set(self.hits[:RECALL_AT])) / len(self.wanted)

    @property
    def reciprocal_rank(self) -> float:
        for rank, hit in enumerate(self.hits[:RANK_AT], start=1):
            if hit in self.wanted:
                return 1 / rank
        return 0.0

    @property
    def ndcg(self) -> float:
        gains = [self.question.grade(hit) for hit in self.hits[:RANK_AT]]
        ideal = sorted(
            (self.question.grade(d) for d in self.question.grade_2 | self.question.grade_1 if d in self.catalogued),
            reverse=True,
        )[:RANK_AT]
        best = _dcg(ideal)
        return _dcg(gains) / best if best else 0.0

    @property
    def never_hits(self) -> tuple[str, ...]:
        return tuple(hit for hit in self.hits if hit in self.question.never)

    @property
    def is_filter(self) -> bool:
        return self.active and bool(self.question.unwanted)

    @property
    def is_negative(self) -> bool:
        return self.active and self.question.kind == NEGATIVE


def _dcg(gains: Iterable[int]) -> float:
    return sum(gain / math.log2(rank + 1) for rank, gain in enumerate(gains, start=1))


@dataclass(frozen=True, slots=True)
class Measures:
    """The measures over one language, or over both."""

    questions: int
    recall_at_5: float | None
    mrr_at_10: float | None
    ndcg_at_10: float | None


@dataclass(frozen=True, slots=True)
class Evaluation:
    outcomes: tuple[Outcome, ...]

    @property
    def active(self) -> tuple[Outcome, ...]:
        return tuple(o for o in self.outcomes if o.active)

    @property
    def resting(self) -> tuple[Outcome, ...]:
        return tuple(o for o in self.outcomes if not o.active)

    def measures(self, language: str = ALL) -> Measures:
        if language != ALL and language not in LANGUAGES:
            raise ValueError(f"no language {language!r}")
        counted = [
            o
            for o in self.outcomes
            if o.measured and (language == ALL or (o.question.language == language and not o.question.name_only))
        ]
        if not counted:
            return Measures(0, None, None, None)
        n = len(counted)
        return Measures(
            n,
            sum(o.recall for o in counted) / n,
            sum(o.reciprocal_rank for o in counted) / n,
            sum(o.ndcg for o in counted) / n,
        )

    @property
    def filters(self) -> tuple[Outcome, ...]:
        return tuple(o for o in self.outcomes if o.is_filter)

    @property
    def negatives(self) -> tuple[Outcome, ...]:
        return tuple(o for o in self.outcomes if o.is_negative)


def evaluate(evaluation_set: EvaluationSet, catalogue: Catalogue, search: Search) -> Evaluation:
    """Every question, the active ones put to ``search``; a hit the catalogue does not hold is an error of the search."""
    outcomes = []
    for question in evaluation_set.questions:
        wanted = frozenset(d for d in question.grade_2 if d in catalogue)
        active = (bool(wanted) or not question.wanted) and (
            question.requires is None or catalogue.offers(question.requires)
        )
        hits: tuple[str, ...] = ()
        if active:
            hits = tuple(search(question))
            strangers = [hit for hit in hits if hit not in catalogue]
            if strangers or len(set(hits)) != len(hits):
                raise ValueError(f"{question.id}: the search answered ids twice or outside the catalogue")
        outcomes.append(Outcome(question, active, hits, wanted, frozenset(catalogue.capabilities)))
    return Evaluation(tuple(outcomes))


# --- pass mark ---------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PassMark:
    """What a run has to reach. ``recall_at_5`` and ``mrr_at_10`` hold per language (adr/0026 §8.1)."""

    recall_at_5: float
    mrr_at_10: float
    #: How many active negative questions may fail.
    negatives_may_fail: int = 1


#: adr/0026 F5 (Otto, 06.11.2026): Recall@5 ≥ 0.9 and MRR@10 ≥ 0.8 per language, every filter question, three of four
#: negative questions. Binding from M5-23 on (M5-22 F3).
ADR_0026_F5 = PassMark(recall_at_5=0.9, mrr_at_10=0.8)


def shortfalls(evaluation: Evaluation, mark: PassMark) -> list[str]:
    """Each way ``evaluation`` misses ``mark``, in words; empty when it passes."""
    misses = []
    for language in LANGUAGES:
        m = evaluation.measures(language)
        if m.recall_at_5 is None or m.mrr_at_10 is None:
            misses.append(f"{language}: no active question to measure")
            continue
        if m.recall_at_5 < mark.recall_at_5:
            misses.append(f"{language}: Recall@5 {m.recall_at_5:.3f} below {mark.recall_at_5}")
        if m.mrr_at_10 < mark.mrr_at_10:
            misses.append(f"{language}: MRR@10 {m.mrr_at_10:.3f} below {mark.mrr_at_10}")
    misses += [f"{o.question.id}: lists {', '.join(o.never_hits)}" for o in evaluation.filters if o.never_hits]
    failed = [o.question.id for o in evaluation.negatives if o.hits]
    if len(failed) > mark.negatives_may_fail:
        misses.append(f"negative questions with hits: {', '.join(failed)}")
    return misses


# --- report ------------------------------------------------------------------------------------------------------------


def report(evaluation: Evaluation) -> str:
    """The measures, then one line per question: grade-2 ranks, hits with ``never``, or why it rests (§8.4)."""

    def number(value: float | None) -> str:
        return "-" if value is None else f"{value:.3f}"

    lines = [f"active {len(evaluation.active)}, resting {len(evaluation.resting)}"]
    for language in (*LANGUAGES, ALL):
        m = evaluation.measures(language)
        lines.append(
            f"{language:>3}: n={m.questions} Recall@5={number(m.recall_at_5)} MRR@10={number(m.mrr_at_10)} "
            f"nDCG@10={number(m.ndcg_at_10)}"
        )
    passed = sum(1 for o in evaluation.filters if not o.never_hits)
    lines.append(f"filter questions passed {passed}/{len(evaluation.filters)}")
    passed = sum(1 for o in evaluation.negatives if not o.hits)
    lines.append(f"negative questions passed {passed}/{len(evaluation.negatives)}")
    for o in evaluation.outcomes:
        q = o.question
        if not o.active:
            why = f"requires {q.requires}" if o.wanted else "no dataset of grade 2 in the catalogue"
            lines.append(f"{q.id} {q.language} resting: {why}")
            continue
        ranks = {d: (o.hits.index(d) + 1 if d in o.hits else None) for d in sorted(o.wanted)}
        parts = [f"{d}@{r if r is not None else '-'}" for d, r in ranks.items()]
        if o.never_hits:
            parts.append(f"never: {', '.join(o.never_hits)}")
        if q.kind == NEGATIVE:
            parts.append("empty" if not o.hits else f"hits: {len(o.hits)}")
        lines.append(f"{q.id} {q.language} {' '.join(parts) or 'filter only'}")
    return "\n".join(lines)

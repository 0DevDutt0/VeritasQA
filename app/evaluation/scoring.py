"""Scoring of one response against one gold record (ARCHITECTURE §17.6 to §17.11; D78, D80, D81, D82, D83).

This module is pure. It receives an :class:`ObservedResponse`, a plain copy of the response fields it reads, and the
texts it checks against. The runner builds both from the store and the engine's response. A test can build them by
hand, so each outcome can be checked without running the engine.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from app.evaluation.errors import EvaluationError
from app.evaluation.gold import GoldRecord
from app.evaluation.metrics import (
    mean_of,
    ndcg_at_k,
    precision_at_k,
    rate,
    reciprocal_rank,
    recall_at_k,
    risk_coverage,
    exact_match,
    token_f1,
)
from app.evaluation.text import contains, normalize

OUTCOMES = (
    "correct_answer",
    "incomplete_answer",
    "incorrect_answer",
    "incorrect_abstention",
    "correct_abstention",
    "false_acceptance",
)
ERROR_OUTCOMES = frozenset({"incorrect_answer", "false_acceptance"})
RETRIEVAL_KS = (1, 5, 10, 50)
UNRANKED = 10**9

# (pdf_page, raw_text) of an evidence unit, read from the store.
UnitView = tuple[int, str]


@dataclass(frozen=True)
class ObservedSpan:
    """An answer span as the response gives it. ``component`` is 1-based."""

    text: str
    evidence_id: str
    component: int
    pdf_page: int
    start: int
    end: int


@dataclass(frozen=True)
class ObservedEvidence:
    """An evidence item as the response gives it. ``components`` holds the 1-based indexes it supports."""

    evidence_id: str
    pdf_page: int
    quote: str | None
    source_start: int | None
    source_end: int | None
    components: frozenset[int]


@dataclass(frozen=True)
class ObservedRetrieval:
    """The ranked candidates of one component. ``k_cut`` is the depth the engine searched (ARCHITECTURE §17.7)."""

    component: int
    k_cut: int
    entries: tuple[tuple[int, str], ...]


@dataclass(frozen=True)
class ObservedComponent:
    """One component of the response. ``verified_ids`` are its evidence IDs with an accepted verification."""

    index: int
    accepted: bool
    evidence_ids: tuple[str, ...]
    verified_ids: frozenset[str]


@dataclass(frozen=True)
class ObservedResponse:
    """The fields of a response that the harness reads. The runner builds it from the engine's response (``_observe``)."""

    status: str
    question_type: str
    components: tuple[ObservedComponent, ...]
    spans: tuple[ObservedSpan, ...]
    evidence: tuple[ObservedEvidence, ...]
    retrieval: tuple[ObservedRetrieval, ...]


@dataclass(frozen=True)
class RetrievalMeasure:
    """The hits of one component against its gold quotes, in rank order (ARCHITECTURE §17.7).

    ``first_ranks`` has one entry per gold quote: the rank of the first unit that contains it, or None.
    """

    component: int
    k_cut: int
    hits: tuple[bool, ...]
    credits: tuple[bool, ...]
    first_ranks: tuple[int | None, ...]


@dataclass(frozen=True)
class ComponentScore:
    """The decision on one component, with its checks. Fields that do not apply are None."""

    index: int
    expected_answerable: bool
    accepted: bool
    correct: bool | None
    cites_gold_page: bool | None
    supported: bool | None
    unsupported: bool | None
    best_rank: int | None


@dataclass(frozen=True)
class AnswerItemScore:
    """One gold answer, scored against the spans of its component."""

    component: int
    exact: bool
    f1: float


@dataclass(frozen=True)
class RecordScore:
    """Everything the harness measures for one gold record."""

    record_id: str
    category: str
    question_type: str
    expected_status: str
    status: str
    answerable: bool
    status_match: bool
    outcome: str
    accepted: bool
    best_rank: int | None
    components: tuple[ComponentScore, ...]
    retrieval: tuple[RetrievalMeasure, ...]
    answer_items: tuple[AnswerItemScore, ...]
    quote_checks: tuple[bool, ...]
    unquoted_items: int
    span_checks: tuple[bool, ...]


def _quotes_gold(evidence: ObservedEvidence, gold_quotes: Sequence[str]) -> bool:
    return evidence.quote is not None and any(contains(evidence.quote, quote) for quote in gold_quotes)


def _span_carries_gold(span: ObservedSpan, evidence_by_id: Mapping[str, ObservedEvidence], gold_quotes: Sequence[str]) -> bool:
    evidence = evidence_by_id.get(span.evidence_id)
    return evidence is not None and _quotes_gold(evidence, gold_quotes)


def _page(pages: Mapping[int, str], pdf_page: int) -> str:
    if pdf_page not in pages:
        raise EvaluationError(f"the text of page {pdf_page} was not loaded")
    return pages[pdf_page]


def measure_retrieval(
    index: int,
    retrieval: ObservedRetrieval,
    gold_quotes: Sequence[str],
    gold_pages: Sequence[int],
    units: Mapping[str, UnitView],
) -> RetrievalMeasure:
    first_ranks: list[int | None] = [None] * len(gold_quotes)
    hits: list[bool] = []
    credits: list[bool] = []
    credited: set[int] = set()
    for rank, evidence_id in retrieval.entries:
        if evidence_id not in units:
            raise EvaluationError(f"the text of unit {evidence_id} was not loaded")
        pdf_page, raw_text = units[evidence_id]
        matched = {
            position
            for position, (quote, quote_page) in enumerate(zip(gold_quotes, gold_pages, strict=True))
            if pdf_page == quote_page and contains(raw_text, quote)
        }
        for position in matched:
            if first_ranks[position] is None:
                first_ranks[position] = rank
        hits.append(bool(matched))
        credits.append(bool(matched - credited))
        credited |= matched
    return RetrievalMeasure(
        component=index,
        k_cut=retrieval.k_cut,
        hits=tuple(hits),
        credits=tuple(credits),
        first_ranks=tuple(first_ranks),
    )


def _outcome(answerable: bool, components: Sequence[ComponentScore]) -> str:
    accepted_any = any(component.accepted for component in components)
    if not answerable:
        return "false_acceptance" if accepted_any else "correct_abstention"
    if not accepted_any:
        return "incorrect_abstention"
    if any(component.accepted and component.correct is not True for component in components):
        return "incorrect_answer"
    if any(component.expected_answerable and not component.accepted for component in components):
        return "incomplete_answer"
    return "correct_answer"


def score_record(
    record: GoldRecord,
    observed: ObservedResponse,
    units: Mapping[str, UnitView],
    pages: Mapping[int, str],
) -> RecordScore:
    """Score one response against its gold record. ``units`` and ``pages`` must hold every unit and page the response names."""
    count = len(observed.components)
    if [component.index for component in observed.components] != list(range(1, count + 1)):
        raise EvaluationError(f"{record.record_id}: the response components are not numbered 1 to {count}")
    if any(evidence.component > count for evidence in record.evidence) or any(
        answer.component > count for answer in record.answers
    ):
        raise EvaluationError(f"{record.record_id}: a gold component is outside the response's {count} components")

    evidence_by_id = {evidence.evidence_id: evidence for evidence in observed.evidence}
    retrieval_by_index = {retrieval.component: retrieval for retrieval in observed.retrieval}
    components: list[ComponentScore] = []
    measures: list[RetrievalMeasure] = []
    for index in range(1, count + 1):
        observed_component = observed.components[index - 1]
        gold_evidence = [evidence for evidence in record.evidence if evidence.component == index]
        gold_quotes = [evidence.quote for evidence in gold_evidence]
        gold_pages = [evidence.pdf_page for evidence in gold_evidence]
        gold_answers = {normalize(answer.text) for answer in record.answers if answer.component == index}
        expected_answerable = record.answerable and bool(gold_quotes)
        accepted = observed_component.accepted
        cited = [evidence for evidence in observed.evidence if index in evidence.components]
        supported = any(_quotes_gold(evidence, gold_quotes) for evidence in cited)
        cites_gold_page = any(evidence.pdf_page in gold_pages for evidence in cited)

        correct: bool | None = None
        if accepted:
            if not expected_answerable:
                correct = False
            elif gold_answers:
                correct = any(
                    span.component == index
                    and normalize(span.text) in gold_answers
                    and _span_carries_gold(span, evidence_by_id, gold_quotes)
                    for span in observed.spans
                )
            else:
                correct = supported

        if index not in retrieval_by_index:
            raise EvaluationError(f"{record.record_id}: component {index} has no retrieval summary")
        retrieval = retrieval_by_index[index]
        ranks = {evidence_id: rank for rank, evidence_id in retrieval.entries}
        best_rank = min(
            (ranks[evidence_id] for evidence_id in observed_component.evidence_ids if evidence_id in ranks),
            default=None,
        )
        if gold_quotes:
            measures.append(measure_retrieval(index, retrieval, gold_quotes, gold_pages, units))
        components.append(
            ComponentScore(
                index=index,
                expected_answerable=expected_answerable,
                accepted=accepted,
                correct=correct,
                cites_gold_page=cites_gold_page if accepted and expected_answerable else None,
                supported=supported if accepted and expected_answerable else None,
                unsupported=(
                    not any(evidence_id in observed_component.verified_ids for evidence_id in observed_component.evidence_ids)
                    if accepted
                    else None
                ),
                best_rank=best_rank if accepted else None,
            )
        )

    answer_items = []
    for answer in record.answers:
        spans = [span for span in observed.spans if span.component == answer.component]
        answer_items.append(
            AnswerItemScore(
                component=answer.component,
                exact=any(exact_match(span.text, answer.text) for span in spans),
                f1=max((token_f1(span.text, answer.text) for span in spans), default=0.0),
            )
        )

    quote_checks: list[bool] = []
    unquoted = 0
    for evidence in observed.evidence:
        if evidence.quote is None:
            unquoted += 1
            continue
        page = _page(pages, evidence.pdf_page)
        quote_checks.append(
            evidence.source_start is not None
            and evidence.source_end is not None
            and page[evidence.source_start : evidence.source_end] == evidence.quote
        )
    span_checks = tuple(
        _page(pages, span.pdf_page)[span.start : span.end] == span.text for span in observed.spans
    )
    accepted_any = any(component.accepted for component in components)
    ranked = [component.best_rank for component in components if component.best_rank is not None]
    return RecordScore(
        record_id=record.record_id,
        category=str(record.category),
        question_type=observed.question_type,
        expected_status=str(record.expected_status),
        status=observed.status,
        answerable=record.answerable,
        status_match=observed.status == str(record.expected_status),
        outcome=_outcome(record.answerable, components),
        accepted=accepted_any,
        best_rank=min(ranked) if accepted_any and ranked else None,
        components=tuple(components),
        retrieval=tuple(measures),
        answer_items=tuple(answer_items),
        quote_checks=tuple(quote_checks),
        unquoted_items=unquoted,
        span_checks=span_checks,
    )


def _outcome_block(scores: Sequence[RecordScore]) -> dict[str, object]:
    counts = Counter(score.outcome for score in scores)
    total = len(scores)
    answerable = sum(1 for score in scores if score.answerable)
    unanswerable = total - answerable
    accepted = sum(1 for score in scores if score.accepted)
    wrong_accepted = counts["incorrect_answer"] + counts["false_acceptance"]
    rates = {
        "coverage": rate(accepted, total),
        "correct_answer_rate": rate(counts["correct_answer"], answerable),
        "incomplete_answer_rate": rate(counts["incomplete_answer"], answerable),
        "incorrect_abstention_rate": rate(counts["incorrect_abstention"], answerable),
        "correct_abstention_rate": rate(counts["correct_abstention"], unanswerable),
        "false_acceptance_rate": rate(counts["false_acceptance"], unanswerable),
        "incorrect_accepted_answer_rate": rate(wrong_accepted, total),
        "selective_risk": rate(wrong_accepted, accepted),
    }
    return {
        "total": total,
        "answerable": answerable,
        "unanswerable": unanswerable,
        "accepted": accepted,
        "counts": {name: counts.get(name, 0) for name in OUTCOMES},
        "rates": {name: value.as_dict() for name, value in rates.items()},
    }


def _groups(scores: Sequence[RecordScore], key: Callable[[RecordScore], str]) -> dict[str, object]:
    groups: dict[str, list[RecordScore]] = {}
    for score in scores:
        groups.setdefault(key(score), []).append(score)
    return {name: _outcome_block(groups[name]) for name in sorted(groups)}


def _component_block(scores: Sequence[RecordScore]) -> dict[str, object]:
    components = [component for score in scores for component in score.components]
    accepted = [component for component in components if component.accepted]
    expected = [component for component in components if component.expected_answerable]
    incorrect = [component for component in accepted if component.correct is not True]
    missed = [component for component in expected if not component.accepted]
    return {
        "total": len(components),
        "accepted": len(accepted),
        "expected_answerable": len(expected),
        "incorrect_accepted": len(incorrect),
        "missed": len(missed),
        "incorrect_rate": rate(len(incorrect), len(accepted)).as_dict(),
        "missed_rate": rate(len(missed), len(expected)).as_dict(),
    }


def retrieval_summary(measures: Sequence[RetrievalMeasure]) -> dict[str, object]:
    """The retrieval block of a run, from its measures (ARCHITECTURE §17.7). The benchmark baselines use it too (§18.5).

    A depth that no measure searched has n = 0 and value None. It is never reported as 0 (ARCHITECTURE §17.9).
    """
    block: dict[str, object] = {
        "measures": len(measures),
        "mrr": mean_of([reciprocal_rank(measure.hits) for measure in measures]).as_dict(),
    }
    for k in RETRIEVAL_KS:
        eligible = [measure for measure in measures if k <= measure.k_cut]
        block[f"recall_at_{k}"] = mean_of([recall_at_k(measure.first_ranks, k) for measure in eligible]).as_dict()
        block[f"precision_at_{k}"] = mean_of([precision_at_k(measure.hits, k) for measure in eligible]).as_dict()
        block[f"ndcg_at_{k}"] = mean_of(
            [ndcg_at_k(measure.credits, len(measure.first_ranks), k) for measure in eligible]
        ).as_dict()
    return block


def _retrieval_block(scores: Sequence[RecordScore]) -> dict[str, object]:
    return retrieval_summary([measure for score in scores for measure in score.retrieval])


def _evidence_block(scores: Sequence[RecordScore]) -> dict[str, object]:
    quote_checks = [ok for score in scores for ok in score.quote_checks]
    span_checks = [ok for score in scores for ok in score.span_checks]
    components = [component for score in scores for component in score.components]
    accepted = [component for component in components if component.accepted]
    accepted_expected = [component for component in accepted if component.expected_answerable]
    return {
        "quotation_accuracy": rate(sum(quote_checks), len(quote_checks)).as_dict(),
        "unquoted_items": sum(score.unquoted_items for score in scores),
        "answer_span_integrity": rate(sum(span_checks), len(span_checks)).as_dict(),
        "citation_page_accuracy": rate(
            sum(1 for component in accepted_expected if component.cites_gold_page), len(accepted_expected)
        ).as_dict(),
        "evidence_support": rate(
            sum(1 for component in accepted_expected if component.supported), len(accepted_expected)
        ).as_dict(),
        "unsupported_answer_rate": rate(
            sum(1 for component in accepted if component.unsupported), len(accepted)
        ).as_dict(),
    }


def _answer_block(scores: Sequence[RecordScore]) -> dict[str, object]:
    items = [item for score in scores for item in score.answer_items]
    return {
        "exact_match": rate(sum(1 for item in items if item.exact), len(items)).as_dict(),
        "token_f1": mean_of([item.f1 for item in items]).as_dict(),
        "status_accuracy": rate(sum(1 for score in scores if score.status_match), len(scores)).as_dict(),
        "status_pairs": dict(sorted(Counter(f"{score.expected_status}->{score.status}" for score in scores).items())),
    }


def _risk_block(scores: Sequence[RecordScore]) -> dict[str, object]:
    items = [
        ((score.best_rank if score.best_rank is not None else UNRANKED, score.record_id), score.outcome in ERROR_OUTCOMES)
        for score in scores
        if score.accepted
    ]
    points = risk_coverage(items, len(scores))
    return {
        "ordering": "best retrieval rank of the accepted evidence, then record_id (an ordering, not a probability; SPEC §9)",
        "points": [point.as_dict() for point in points],
    }


def build_metrics(scores: Sequence[RecordScore]) -> dict[str, object]:
    """All metrics of one run, from the per-record scores. Pure: the same scores give the same metrics."""
    return {
        "outcomes": _outcome_block(scores),
        "components": _component_block(scores),
        "retrieval": _retrieval_block(scores),
        "evidence": _evidence_block(scores),
        "answers": _answer_block(scores),
        "breakdown": {
            "category": _groups(scores, lambda score: score.category),
            "question_type": _groups(scores, lambda score: score.question_type),
        },
        "risk_coverage": _risk_block(scores),
    }

"""Extractive selection of candidate passages for each question component (SPEC §6; ARCHITECTURE §14).

A candidate is a verbatim passage that a rule connects to a question component. It is not an answer. Only a
rule-determined value or marker is given as an answer span, and every other type carries ``no_answer_span``.
Verification (P6) and the decision (P7) decide what a candidate may support.

The rules are listed in ``RULE_IDS``. Each candidate records its rule, and the retrieval candidate it came from is
kept by reference (D46), so the scores and the expansion record stay with retrieval.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.document_structure.models import ContentType, EvidenceUnit
from app.evidence.errors import SelectionError
from app.evidence.markers import find_markers
from app.evidence.segment import sentence_spans
from app.evidence.values import Value, ValueKind, find_values
from app.question_processing.analysis import QuestionAnalysis, QuestionComponent, QuestionType
from app.retrieval.bm25 import RetrievalCandidate, RetrievalResult
from app.retrieval.forms import span_matches_word
from app.retrieval.phrase import build_phrase_query, span_matches

REPLACEMENT_CHARACTER = "\ufffd"

RULE_IDS: dict[QuestionType, str] = {
    QuestionType.WHAT: "what.sentence.v1",
    QuestionType.WHO: "who.sentence.v1",
    QuestionType.WHERE: "where.sentence.v1",
    QuestionType.WHICH: "which.sentence.v1",
    QuestionType.WHEN: "when.date_or_period.v1",
    QuestionType.HOW_MANY: "how_many.value_with_unit.v1",
    QuestionType.WHETHER: "whether.permission_marker.v1",
    QuestionType.CONDITIONS: "conditions.passage.v1",
    QuestionType.COMPARISON: "comparison.subject_sentence.v1",
}

_DERIVED_ROW = "derived_row"
_CROSSES_SPAN = "crosses_source_span"


class ComponentStatus(StrEnum):
    """What selection found for one component. None of these is a verdict on the answer (P6 and P7 decide)."""

    CANDIDATES = "candidates"
    EXPANSION_ONLY = "expansion_only"
    NO_CANDIDATES = "no_candidates"
    UNSUPPORTED = "unsupported"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class AnswerCandidate:
    """A verbatim passage for one component.

    ``pdf_page`` and ``section_id`` are the citation (SPEC §6). ``quote`` equals the page's raw text from
    ``page_start`` to ``page_end``. ``answer_span`` is set only when a
    rule determines it, and its offsets are page offsets too. ``values`` lists the values in the quote, with
    offsets relative to the quote.
    """

    component_id: str
    question_type: QuestionType
    retrieval: RetrievalCandidate
    pdf_page: int
    section_id: str | None
    rule_id: str
    granularity: str
    quote: str
    page_start: int
    page_end: int
    answer_span: str | None
    answer_page_start: int | None
    answer_page_end: int | None
    answer_kind: str | None
    values: tuple[Value, ...]
    negated: bool
    attribute_hits: tuple[str, ...]
    flags: tuple[str, ...]

    @property
    def evidence_id(self) -> str:
        return self.retrieval.evidence_id

    @property
    def expansion_only(self) -> bool:
        """True when only a reviewed rule reached this passage. It is never support (D38)."""
        return self.retrieval.expansion_only


@dataclass(frozen=True)
class DroppedCandidate:
    """A retrieved unit that produced no candidate, and why. Nothing is dropped without a record (D48, D49)."""

    evidence_id: str
    reason: str


@dataclass(frozen=True)
class ComponentSelection:
    """The result for one component. It is present even when it has no candidates (D45)."""

    component_id: str
    question_type: QuestionType
    status: ComponentStatus
    reasons: tuple[str, ...]
    candidates: tuple[AnswerCandidate, ...]
    dropped: tuple[DroppedCandidate, ...]


@dataclass(frozen=True)
class SelectionResult:
    question: str
    components: tuple[ComponentSelection, ...]


def _page_offsets(unit: EvidenceUnit, start: int, end: int) -> tuple[int, int] | None:
    """Map offsets in ``unit.raw_text`` to offsets in the page's raw text. None when the range crosses a join.

    ``raw_text`` is the newline join of the unit's source spans (ARCHITECTURE §11), so each span begins one
    character after the end of the span before it.
    """
    cursor = 0
    for page_start, page_end in unit.source_spans:
        length = page_end - page_start
        if cursor <= start and end <= cursor + length:
            return page_start + (start - cursor), page_start + (end - cursor)
        cursor += length + 1
    return None


def unit_page_offsets(unit: EvidenceUnit, start: int, end: int) -> tuple[int, int] | None:
    """Public form of :func:`_page_offsets` for the P7 conflict screen (ARCHITECTURE §16.2). None when the range
    crosses a join, so the text cannot be quoted."""
    return _page_offsets(unit, start, end)


def _values_of(text: str, count_nouns: tuple[str, ...]) -> tuple[Value, ...]:
    return find_values(text, count_nouns=count_nouns)


def _expected_present(question_type: QuestionType, values: tuple[Value, ...], text: str) -> bool:
    """The rule's responsiveness test. It decides whether a passage is a candidate at all, not whether it answers."""
    if question_type == QuestionType.WHEN:
        return any(value.kind in (ValueKind.DATE, ValueKind.PERIOD) for value in values)
    if question_type == QuestionType.HOW_MANY:
        return any(_is_quantity(value) for value in values)
    if question_type == QuestionType.WHETHER:
        return bool(find_markers(text, "permission"))
    if question_type == QuestionType.CONDITIONS:
        return bool(find_markers(text, "condition"))
    return True


def _is_quantity(value: Value) -> bool:
    if value.kind in (ValueKind.PERCENT, ValueKind.CURRENCY):
        return True
    return value.kind == ValueKind.NUMBER and value.unit is not None


_EXPECTED_REASON: dict[QuestionType, str] = {
    QuestionType.WHEN: "a date or period",
    QuestionType.HOW_MANY: "a number with a unit, a percentage or a currency amount",
    QuestionType.WHETHER: "a permission or prohibition marker",
    QuestionType.CONDITIONS: "a condition marker",
}


def _candidate(
    component: QuestionComponent,
    retrieval: RetrievalCandidate,
    unit: EvidenceUnit,
    start: int,
    end: int,
    granularity: str,
    page_range: tuple[int, int],
    count_nouns: tuple[str, ...],
) -> AnswerCandidate:
    raw = unit.raw_text
    text = raw[start:end]
    question_type = component.question_type
    values = _values_of(text, count_nouns)
    flags: list[str] = []
    if unit.content_type == ContentType.TABLE_CELL:
        flags.append("table_cell")
    if "comparison_subject" in component.flags:
        flags.append("comparison_subject")
    if question_type == QuestionType.WHICH and find_markers(text, "list"):
        flags.append("list_marker")
    if REPLACEMENT_CHARACTER in text:
        flags.append("replacement_character")

    answer_text: str | None = None
    answer_range: tuple[int, int] | None = None
    answer_kind: str | None = None
    negated = False
    rule_id = RULE_IDS[question_type]

    if question_type in (QuestionType.WHEN, QuestionType.HOW_MANY):
        if question_type == QuestionType.WHEN:
            eligible = [value for value in values if value.kind in (ValueKind.DATE, ValueKind.PERIOD)]
        else:
            eligible = [value for value in values if _is_quantity(value)]
        if unit.content_type == ContentType.TABLE_CELL:
            flags.append("no_answer_span")
        elif len(eligible) == 1:
            only = eligible[0]
            answer_text = only.text
            answer_range = (start + only.start, start + only.end)
            answer_kind = only.kind.value
        else:
            flags.append("multiple_values")
    elif question_type == QuestionType.WHETHER:
        markers = find_markers(text, "permission")
        if unit.content_type == ContentType.TABLE_CELL:
            flags.append("no_answer_span")
        elif len(markers) == 1:
            answer_text = markers[0].text
            answer_range = (start + markers[0].start, start + markers[0].end)
            answer_kind = "permission_marker"
            negated = markers[0].negative
        else:
            flags.append("multiple_markers")
    else:
        flags.append("no_answer_span")

    answer_page: tuple[int, int] | None = None
    if answer_range is not None:
        answer_page = _page_offsets(unit, answer_range[0], answer_range[1])
        if answer_page is None:
            # Inside a sentence that already maps to one span, so this should not happen. Refuse, do not guess.
            raise SelectionError(f"the answer span of {unit.evidence_id} does not map to one source span")

    attribute_hits = tuple(
        attribute for attribute in component.attribute_terms if span_matches(text, build_phrase_query(attribute))
    )
    return AnswerCandidate(
        component_id=component.component_id,
        question_type=question_type,
        retrieval=retrieval,
        pdf_page=unit.pdf_page,
        section_id=unit.section_id,
        rule_id=rule_id,
        granularity=granularity,
        quote=text,
        page_start=page_range[0],
        page_end=page_range[1],
        answer_span=answer_text,
        answer_page_start=None if answer_page is None else answer_page[0],
        answer_page_end=None if answer_page is None else answer_page[1],
        answer_kind=answer_kind,
        values=values,
        negated=negated,
        attribute_hits=attribute_hits,
        flags=tuple(flags),
    )


@dataclass
class _Counts:
    units: int = 0
    with_targets: int = 0
    with_expected: int = 0
    derived: int = 0
    crossed: int = 0


def _select_for_component(
    component: QuestionComponent,
    retrieved: Sequence[RetrievalCandidate],
    units: Mapping[str, EvidenceUnit],
) -> tuple[list[AnswerCandidate], list[DroppedCandidate], _Counts]:
    count_nouns = component.target_terms
    question_type = component.question_type
    candidates: list[AnswerCandidate] = []
    dropped: list[DroppedCandidate] = []
    counts = _Counts()

    for retrieval in retrieved:
        unit = units.get(retrieval.evidence_id)
        if unit is None:
            raise SelectionError(f"no unit was given for {retrieval.evidence_id}, which the retrieval returned")
        if unit.derived:
            dropped.append(DroppedCandidate(retrieval.evidence_id, _DERIVED_ROW))
            counts.derived += 1
            continue
        counts.units += 1
        raw = unit.raw_text
        if question_type == QuestionType.CONDITIONS or unit.content_type == ContentType.TABLE_CELL:
            pieces = [(0, len(raw), "passage")]
        else:
            pieces = [(start, end, "sentence") for start, end in sentence_spans(raw)]

        crossed = False
        for start, end, granularity in pieces:
            text = raw[start:end]
            if not all(span_matches_word(text, term) for term in component.target_terms):
                continue
            counts.with_targets += 1
            values = _values_of(text, count_nouns)
            if not _expected_present(question_type, values, text):
                continue
            counts.with_expected += 1
            page_range = _page_offsets(unit, start, end)
            if page_range is None:
                crossed = True
                continue
            candidates.append(
                _candidate(component, retrieval, unit, start, end, granularity, page_range, count_nouns)
            )
        if crossed:
            dropped.append(DroppedCandidate(retrieval.evidence_id, _CROSSES_SPAN))
            counts.crossed += 1
    return candidates, dropped, counts


def _no_candidate_reasons(
    component: QuestionComponent, retrieved: Sequence[RetrievalCandidate], counts: _Counts
) -> tuple[str, ...]:
    if not retrieved:
        return ("the search returned no unit for this query",)
    if counts.derived == len(retrieved):
        return ("every retrieved unit is a generated table row, which is never quoted",)
    if counts.with_targets == 0:
        return (f"no retrieved sentence contains all of: {', '.join(component.target_terms)}",)
    if counts.crossed and counts.with_expected == 0:
        return ("the matching text crosses a join between source spans, so it cannot be quoted verbatim",)
    expected = _EXPECTED_REASON.get(component.question_type)
    if expected is not None and counts.with_expected == 0:
        unit_word = "passage" if component.question_type == QuestionType.CONDITIONS else "sentence"
        return (f"no {unit_word} with every target term also has {expected}",)
    return ()


def _status(
    component: QuestionComponent,
    candidates: list[AnswerCandidate],
    retrieved: Sequence[RetrievalCandidate],
    counts: _Counts,
) -> tuple[ComponentStatus, tuple[str, ...]]:
    if candidates:
        if any(candidate.retrieval.via == "original" for candidate in candidates):
            return ComponentStatus.CANDIDATES, ()
        return (
            ComponentStatus.EXPANSION_ONLY,
            ("only reviewed rules reached these passages, so they are not support (D38)",),
        )
    return ComponentStatus.NO_CANDIDATES, _no_candidate_reasons(component, retrieved, counts)


def select_candidates(
    analysis: QuestionAnalysis,
    retrieved: Mapping[str, RetrievalResult],
    units: Mapping[str, EvidenceUnit],
) -> SelectionResult:
    """Select verbatim candidates for every component of ``analysis`` (ARCHITECTURE §14).

    ``retrieved`` maps each searchable component ID to the result of ``search()`` run with that component's
    ``retrieval_query``. ``units`` maps evidence IDs to the units the retrieval returned. Raises
    :class:`SelectionError` when a searchable component has no result, when a result answers a different query,
    or when a returned unit is missing. Unsearchable components are reported, never searched.
    """
    selections: list[ComponentSelection] = []
    for component in analysis.components:
        if not component.searchable:
            status = (
                ComponentStatus.UNSUPPORTED
                if component.question_type == QuestionType.UNSUPPORTED
                else ComponentStatus.AMBIGUOUS
            )
            selections.append(
                ComponentSelection(
                    component_id=component.component_id,
                    question_type=component.question_type,
                    status=status,
                    reasons=(component.reason or "",),
                    candidates=(),
                    dropped=(),
                )
            )
            continue
        result = retrieved.get(component.component_id)
        if result is None:
            raise SelectionError(f"no retrieval result was given for component {component.component_id}")
        if result.query != component.retrieval_query:
            raise SelectionError(
                f"the retrieval result for {component.component_id} answers {result.query!r}, "
                f"not {component.retrieval_query!r}"
            )
        candidates, dropped, counts = _select_for_component(component, result.candidates, units)
        status, reasons = _status(component, candidates, result.candidates, counts)
        selections.append(
            ComponentSelection(
                component_id=component.component_id,
                question_type=component.question_type,
                status=status,
                reasons=reasons,
                candidates=tuple(candidates),
                dropped=tuple(dropped),
            )
        )
    return SelectionResult(question=analysis.question, components=tuple(selections))

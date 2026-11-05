"""The SPEC §7 checks and the P5 flag check, one function each (ARCHITECTURE §15).

Each function takes a ``Claim``: the candidate with the stored text it points to. The candidate is treated as a claim.
The functions re-read what they need, and they recompute values, markers, polarity and word matches from the text.
Nothing is copied from the candidate's ``values``, ``attribute_hits`` or ``negated``. A mismatch is a FAIL.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.common.errors import StorageError
from app.document_structure.models import EvidenceUnit
from app.evidence.markers import find_markers
from app.evidence.selection import AnswerCandidate
from app.evidence.values import Value, ValueKind, find_values
from app.ingestion.models import QualityStatus
from app.question_processing.analysis import QuestionComponent, QuestionType
from app.retrieval.forms import span_matches_word
from app.retrieval.phrase import build_phrase_query, span_matches
from app.retrieval.terms import Term
from app.storage import Store
from app.verification.report import CheckName, CheckResult, CheckStatus
from app.verification.terms import find_occurrences
from app.verification.vocabulary import (
    ANSWER_TYPES,
    BLOCKING_FLAG_REASONS,
    EXPECTED_RULE_IDS,
    HEDGE,
    NEGATION,
    STRONG_QUALIFIERS,
)


@dataclass(frozen=True)
class Claim:
    """A candidate and the stored text it points to.

    ``page_text`` is None when the store holds no text for the page. ``unit`` is None when the store holds no unit
    with the candidate's evidence ID in this document. ``question_terms`` are the number, date and identifier terms
    of the component's own text, read by P4's term rule.
    """

    candidate: AnswerCandidate
    component: QuestionComponent
    store: Store
    document_id: str
    page_text: str | None
    unit: EvidenceUnit | None
    question_terms: tuple[Term, ...]


def _result(name: CheckName, status: CheckStatus, reason: str) -> CheckResult:
    return CheckResult(name=name, rule_id=f"verify.{name.value}.v1", status=status, reason=reason)


def _is_quantity(value: Value) -> bool:
    if value.kind in (ValueKind.PERCENT, ValueKind.CURRENCY):
        return True
    return value.kind == ValueKind.NUMBER and value.unit is not None


def _eligible(claim: Claim) -> list[tuple[str, int, int, bool, str]]:
    """The values or markers that the question type needs, read again from the quote.

    Each item is (kind, start, end, negative, text), with offsets relative to the quote. P5's rule is applied again
    here on purpose: the candidate's own answer is only a claim to be compared with this result.
    """
    quote = claim.candidate.quote
    question_type = claim.candidate.question_type
    if question_type == QuestionType.WHETHER:
        return [("permission_marker", m.start, m.end, m.negative, m.text) for m in find_markers(quote, "permission")]
    values = find_values(quote, count_nouns=claim.component.target_terms)
    if question_type == QuestionType.WHEN:
        chosen = [value for value in values if value.kind in (ValueKind.DATE, ValueKind.PERIOD)]
    else:
        chosen = [value for value in values if _is_quantity(value)]
    return [(value.kind.value, value.start, value.end, False, value.text) for value in chosen]


def _negation_hits(text: str) -> list[tuple[int, int, str]]:
    hits = [(m.start(), m.end(), m.group(0)) for pattern in (NEGATION, HEDGE) for m in pattern.finditer(text)]
    return sorted(hits)


def _first_negation(text: str) -> str | None:
    hits = _negation_hits(text)
    return hits[0][2] if hits else None


def _first_negation_outside(text: str, start: int, end: int) -> str | None:
    for first, last, word in _negation_hits(text):
        if last <= start or end <= first:
            return word
    return None


def _page_codes(claim: Claim) -> tuple[str, ...] | None:
    try:
        return claim.store.page_warning_codes(claim.document_id, claim.candidate.pdf_page)
    except StorageError:
        return None


def check_quotation(claim: Claim) -> CheckResult:
    """SPEC §7 check 1. The quote is the stored page text at its offsets (source integrity only, not support)."""
    name = CheckName.QUOTATION
    candidate = claim.candidate
    if not candidate.quote:
        return _result(name, CheckStatus.FAIL, "the quote is empty")
    if claim.page_text is None:
        return _result(name, CheckStatus.FAIL, f"the store holds no text for page {candidate.pdf_page}")
    start, end = candidate.page_start, candidate.page_end
    if not 0 <= start < end <= len(claim.page_text):
        return _result(name, CheckStatus.FAIL, f"the offsets {start} to {end} are outside the stored page text")
    if claim.page_text[start:end] != candidate.quote:
        return _result(name, CheckStatus.FAIL, "the quote is not the stored page text at its offsets")
    return _result(name, CheckStatus.PASS, "the quote equals the stored page text at its offsets")


def check_location(claim: Claim) -> CheckResult:
    """SPEC §7 check 2. The unit, its page and section, its quality, its rule and the quote's source span agree."""
    name = CheckName.LOCATION
    candidate, unit = claim.candidate, claim.unit
    if unit is None:
        return _result(name, CheckStatus.FAIL, f"the store holds no unit {candidate.evidence_id} in this document")
    problems: list[str] = []
    if unit.derived:
        problems.append("it is a derived table row, which is never quoted (D28)")
    if not unit.body_retrieval:
        problems.append("it is header or footer text, not body text")
    if unit.pdf_page != candidate.pdf_page:
        problems.append(f"the unit is on page {unit.pdf_page}, not page {candidate.pdf_page}")
    if unit.section_id != candidate.section_id:
        problems.append("the section differs from the section of the stored unit")
    retrieval = candidate.retrieval
    if retrieval.pdf_page != unit.pdf_page or retrieval.ordinal != unit.ordinal:
        problems.append("the retrieval record names a different position from the stored unit")
    if retrieval.extraction_quality != unit.extraction_quality.value:
        problems.append("the extraction quality differs from the stored unit")
    if retrieval.derived != unit.derived:
        problems.append("the derived flag differs from the stored unit")
    if candidate.rule_id != EXPECTED_RULE_IDS.get(candidate.question_type):
        problems.append(f"rule {candidate.rule_id} does not belong to this question type")
    start, end = candidate.page_start, candidate.page_end
    inside = any(first <= start and end <= last for first, last in unit.source_spans)
    if not inside or start >= end:
        problems.append("the quote is not inside one source span of the unit")
    if problems:
        return _result(name, CheckStatus.FAIL, "; ".join(problems))
    return _result(
        name,
        CheckStatus.PASS,
        f"body text on page {unit.pdf_page}, with the quote inside one of the unit's source spans",
    )


def check_answer_span(claim: Claim) -> CheckResult:
    """SPEC §7 check 3. A passage-only type never has a span. An answer type's span is the one value or marker of
    the passage, at its stored offsets, of the stored kind."""
    name = CheckName.ANSWER_SPAN
    candidate = claim.candidate
    if candidate.question_type not in ANSWER_TYPES:
        if candidate.answer_span is not None:
            return _result(name, CheckStatus.FAIL, "a passage-only question type carries an answer span")
        return _result(
            name,
            CheckStatus.UNRESOLVED,
            "passage only: no rule gives an answer span for this question type (SPEC §6)",
        )
    if candidate.answer_span is None:
        reasons = [BLOCKING_FLAG_REASONS[flag] for flag in candidate.flags if flag in BLOCKING_FLAG_REASONS]
        detail = "; ".join(reasons) if reasons else "the passage has no value or marker of the required kind"
        return _result(name, CheckStatus.UNRESOLVED, f"no answer span: {detail}")
    if candidate.answer_page_start is None or candidate.answer_page_end is None:
        return _result(name, CheckStatus.FAIL, "the stored span has no page offsets")
    first, last = candidate.answer_page_start, candidate.answer_page_end
    if not candidate.page_start <= first < last <= candidate.page_end:
        return _result(name, CheckStatus.FAIL, "the stored span lies outside the quote")
    if claim.page_text is None or claim.page_text[first:last] != candidate.answer_span:
        return _result(name, CheckStatus.FAIL, "the stored span is not the page text at its offsets")
    eligible = _eligible(claim)
    if len(eligible) != 1:
        return _result(
            name,
            CheckStatus.FAIL,
            f"the passage holds {len(eligible)} values or markers of the required kind, so no single span is supported",
        )
    kind, rel_start, rel_end, _negative, text = eligible[0]
    if (rel_start, rel_end) != (first - candidate.page_start, last - candidate.page_start):
        return _result(name, CheckStatus.FAIL, "the stored span is not at the one value or marker of the passage")
    if text != candidate.answer_span:
        return _result(name, CheckStatus.FAIL, "the stored span text differs from the value read from the passage")
    if kind != candidate.answer_kind:
        return _result(
            name,
            CheckStatus.FAIL,
            f"the stored kind {candidate.answer_kind} differs from the passage's kind {kind}",
        )
    return _result(
        name,
        CheckStatus.PASS,
        f"the span is the only value of the required kind in the passage ({kind}), at its stored offsets",
    )


def check_entity(claim: Claim) -> CheckResult:
    """SPEC §7 check 4. Every target word, or a word form (P13, D131), occurs in the quote (P3's exact check, D33)."""
    name = CheckName.ENTITY
    if claim.candidate.expansion_only:
        return _result(
            name,
            CheckStatus.FAIL,
            "the passage was reached only through a reviewed rule; an expansion is never support (D38)",
        )
    targets = claim.component.target_terms
    if not targets:
        return _result(name, CheckStatus.UNRESOLVED, "the question has no target word")
    quote = claim.candidate.quote
    missing = [word for word in targets if not span_matches_word(quote, word)]
    if missing:
        words = ", ".join(missing)
        return _result(name, CheckStatus.FAIL, f"the passage does not contain the question's word(s): {words}")
    return _result(
        name,
        CheckStatus.PASS,
        f"every target word of the question occurs in the passage: {', '.join(targets)}",
    )


def check_attribute(claim: Claim) -> CheckResult:
    """SPEC §7 check 5. At least one property word of the question occurs in the quote. Synonyms are not used."""
    name = CheckName.ATTRIBUTE
    attributes = claim.component.attribute_terms
    if not attributes:
        return _result(name, CheckStatus.NOT_APPLICABLE, "the question has no property word")
    quote = claim.candidate.quote
    hits = [word for word in attributes if span_matches(quote, build_phrase_query(word))]
    if hits:
        return _result(name, CheckStatus.PASS, f"property word(s) of the question in the passage: {', '.join(hits)}")
    return _result(
        name,
        CheckStatus.UNRESOLVED,
        f"no property word of the question ({', '.join(attributes)}) occurs in the passage; synonyms are not used",
    )


def check_value(claim: Claim) -> CheckResult:
    """SPEC §7 check 6. Each number, date or identifier of the question occurs in the quote, with its sign (D63)."""
    name = CheckName.VALUE
    if claim.candidate.expansion_only:
        return _result(
            name,
            CheckStatus.FAIL,
            "the passage was reached only through a reviewed rule; an expansion is never support (D38)",
        )
    if not claim.question_terms:
        return _result(name, CheckStatus.NOT_APPLICABLE, "the question has no number, percentage, date or identifier")
    quote = claim.candidate.quote
    present: list[str] = []
    absent: list[str] = []
    negative_only: list[str] = []
    for term in claim.question_terms:
        occurrences = find_occurrences(quote, term.text)
        if any(not occurrence.negative for occurrence in occurrences):
            present.append(term.text)
        elif occurrences:
            negative_only.append(term.text)
        else:
            absent.append(term.text)
    if negative_only:
        return _result(
            name,
            CheckStatus.FAIL,
            f"the passage has {', '.join(negative_only)} only with a minus sign, which the question does not",
        )
    if absent:
        names = ", ".join(absent)
        return _result(name, CheckStatus.UNRESOLVED, f"the question's value(s) do not occur in the passage: {names}")
    return _result(name, CheckStatus.PASS, f"every value of the question occurs in the passage: {', '.join(present)}")


def check_context(claim: Claim) -> CheckResult:
    """SPEC §7 check 7. The immediate neighbours (``prev_id``, ``next_id``) do not qualify the passage.

    The order of a page that is not verified is not trusted (Q11, D62), so such a page is UNRESOLVED without any
    neighbour being read.
    """
    name = CheckName.CONTEXT
    unit = claim.unit
    if unit is None:
        return _result(name, CheckStatus.UNRESOLVED, "the unit cannot be read (see the location check)")
    if unit.extraction_quality != QualityStatus.VERIFIED:
        return _result(
            name,
            CheckStatus.UNRESOLVED,
            f"the page is {unit.extraction_quality.value}, so its reading order is not verified and its neighbours "
            "are not read (D62)",
        )
    neighbours = [evidence_id for evidence_id in (unit.prev_id, unit.next_id) if evidence_id is not None]
    for evidence_id in neighbours:
        neighbour = claim.store.load_unit(claim.document_id, evidence_id)
        if neighbour is None:
            return _result(name, CheckStatus.UNRESOLVED, f"the neighbouring unit {evidence_id} cannot be read")
        if neighbour.extraction_quality != QualityStatus.VERIFIED:
            return _result(
                name,
                CheckStatus.UNRESOLVED,
                f"the neighbouring unit {evidence_id} is on a page that is not verified (D62)",
            )
        qualifier = STRONG_QUALIFIERS.search(neighbour.raw_text)
        if qualifier is not None:
            return _result(
                name,
                CheckStatus.UNRESOLVED,
                f"the neighbouring unit qualifies the passage with '{qualifier.group(0)}'",
            )
    return _result(
        name,
        CheckStatus.PASS,
        f"no strong qualifier in the {len(neighbours)} neighbouring unit(s) of a verified page",
    )


def check_negation(claim: Claim) -> CheckResult:
    """SPEC §7 check 8. A whether answer has one marker whose polarity matches the stored polarity, and no other
    negation or hedge word. Other types have no negation or hedge word in the quote."""
    name = CheckName.NEGATION
    candidate = claim.candidate
    if candidate.expansion_only:
        return _result(
            name,
            CheckStatus.FAIL,
            "the passage was reached only through a reviewed rule; an expansion is never support (D38)",
        )
    quote = candidate.quote
    if candidate.question_type == QuestionType.WHETHER:
        if claim.component.negated:
            return _result(
                name,
                CheckStatus.UNRESOLVED,
                "the question is negated, and its polarity is not compared with the passage by rules",
            )
        markers = find_markers(quote, "permission")
        if len(markers) != 1:
            return _result(
                name,
                CheckStatus.UNRESOLVED,
                f"the passage has {len(markers)} permission markers, so its polarity is not single",
            )
        marker = markers[0]
        if marker.negative != candidate.negated:
            return _result(
                name,
                CheckStatus.FAIL,
                f"the stored polarity differs from the passage's marker '{marker.text}'",
            )
        outside = _first_negation_outside(quote, marker.start, marker.end)
        if outside is not None:
            return _result(
                name,
                CheckStatus.UNRESOLVED,
                f"'{outside}' is in the passage outside the marker, so its scope is not checked",
            )
        kind = "prohibition" if marker.negative else "permission"
        return _result(
            name,
            CheckStatus.PASS,
            f"one {kind} marker ('{marker.text}') and no other negation or hedge word in the passage",
        )
    word = _first_negation(quote)
    if word is not None:
        return _result(
            name,
            CheckStatus.UNRESOLVED,
            f"'{word}' is in the passage, and its scope is not checked by rules",
        )
    return _result(name, CheckStatus.PASS, "no negation or hedge word in the passage")


def check_condition(claim: Claim) -> CheckResult:
    """SPEC §7 check 9. The passage states no condition, exception or qualifier (D62)."""
    name = CheckName.CONDITION
    if claim.candidate.expansion_only:
        return _result(
            name,
            CheckStatus.FAIL,
            "the passage was reached only through a reviewed rule; an expansion is never support (D38)",
        )
    quote = claim.candidate.quote
    found = [marker.text for marker in find_markers(quote, "condition")]
    found += [qualifier.group(0) for qualifier in STRONG_QUALIFIERS.finditer(quote)]
    if found:
        return _result(
            name,
            CheckStatus.UNRESOLVED,
            f"the passage states a condition or exception: {', '.join(dict.fromkeys(found))}",
        )
    return _result(name, CheckStatus.PASS, "no condition, exception or qualifier marker in the passage")


def check_source_quality(claim: Claim) -> CheckResult:
    """SPEC §7 check 11. Only a verified page counts as clean (D62). A flagged page is UNRESOLVED, with its issues."""
    name = CheckName.SOURCE_QUALITY
    unit = claim.unit
    if unit is None:
        return _result(name, CheckStatus.UNRESOLVED, "the unit cannot be read (see the location check)")
    quality = unit.extraction_quality
    if quality == QualityStatus.VERIFIED:
        return _result(name, CheckStatus.PASS, "the page is verified")
    codes = _page_codes(claim)
    if codes is None:
        detail = "its stored issues cannot be read"
    elif codes:
        detail = f"its stored issues are {', '.join(codes)}"
    else:
        detail = "no issue is stored for it"
    return _result(
        name,
        CheckStatus.UNRESOLVED,
        f"the page is {quality.value}; only a verified page counts as clean (D62); {detail}",
    )


def check_candidate_flags(claim: Claim) -> CheckResult:
    """The P5 flags (D64). Every blocking flag, and every unknown flag, gives UNRESOLVED."""
    name = CheckName.CANDIDATE_FLAGS
    flags = claim.candidate.flags
    if not flags:
        return _result(name, CheckStatus.PASS, "the candidate has no P5 flag")
    reasons = [BLOCKING_FLAG_REASONS.get(flag, f"unknown flag '{flag}'") for flag in flags]
    return _result(name, CheckStatus.UNRESOLVED, "; ".join(reasons))


# Every check that the verifier runs. The conflict check is not here: it is pending in the decision step (D66).
CHECKS: dict[CheckName, Callable[[Claim], CheckResult]] = {
    CheckName.QUOTATION: check_quotation,
    CheckName.LOCATION: check_location,
    CheckName.ANSWER_SPAN: check_answer_span,
    CheckName.ENTITY: check_entity,
    CheckName.ATTRIBUTE: check_attribute,
    CheckName.VALUE: check_value,
    CheckName.CONTEXT: check_context,
    CheckName.NEGATION: check_negation,
    CheckName.CONDITION: check_condition,
    CheckName.SOURCE_QUALITY: check_source_quality,
    CheckName.CANDIDATE_FLAGS: check_candidate_flags,
}

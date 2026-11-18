"""Check that an extracted clause has the subject and scope specified by its question."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.document_structure.models import ContentType, EvidenceUnit
from app.evidence.extractive import (
    Intent,
    Span,
    cell_keys,
    extract_span,
    intent_for,
    keywords,
    sentence_ranges,
    table_number,
    word_key,
)
from app.question_processing.analysis import QuestionType
from app.retrieval.phrase import build_phrase_query, span_matches
from app.retrieval.terms import extract_terms
from app.verification.checks import Claim, answer_offsets
from app.verification.report import CheckName, CheckResult, CheckStatus
from app.verification.terms import find_occurrences

PROSE = frozenset(
    {ContentType.PARAGRAPH, ContentType.LIST_ITEM, ContentType.PAGE_TEXT, ContentType.FOOTNOTE, ContentType.CAPTION}
)
_CLAUSE_TYPES = frozenset(
    {QuestionType.WHAT, QuestionType.WHICH, QuestionType.HOW, QuestionType.WHERE, QuestionType.WHO}
)
_NEGATION = re.compile(r"\b(?:not|never|cannot|no(?!\s+(?:later|more|fewer)\s+than)|\w+n['’]t)\b", re.I)
_QUALIFIER = re.compile(r"\b(?:unless|except(?:ion)?s?|only\s+if|provided\s+that|does?\s+not\s+apply)\b", re.I)
_FOLLOWING_LIMITATION = re.compile(r"^\s*(?:(?:an?\s+|the\s+)?exceptions?\b|unless\b|only\s+if\b)", re.I)
_EXAMPLE = re.compile(
    r"^\s*(?:for\s+(?:example|instance)\b|an?\s+(?:[\w-]+\s+){0,6}example\b|suppose\b|assume\b|hypothetical\b)", re.I
)
_TITLE = re.compile(r"^(?P<title>[^.?!:;\n]{2,65})\n\s*\n")
_PRONOUN_OPEN = re.compile(r"^(?:it|they|these|those)\b", re.I)
_PERMISSION_WORDS = frozenset(
    word_key(word) for word in ("permitted", "allowed", "authorized", "forbidden", "prohibited")
)


@dataclass(frozen=True)
class Grounding:
    span: Span
    local: frozenset[str]
    scope: frozenset[str]


def _literal_in(text: str, literal: str) -> bool:
    return span_matches(text, build_phrase_query(literal))


def literal_scope(intent: Intent, quote: str, unit: EvidenceUnit) -> bool:
    """Keep the question's explicit identifiers and values, including its signed values."""
    cell = unit.content_type == ContentType.TABLE_CELL
    if cell:
        if intent.table is None or table_number(unit) != intent.table or not unit.row_index:
            return False
        source = " ".join((quote, unit.row_header or "", unit.col_header or ""))
    else:
        source = quote
    if any(not _literal_in(source, code) for code in intent.codes):
        return False
    for term in extract_terms(intent.core):
        literal = term.text.casefold()
        if literal == intent.table or any(literal in code for code in intent.codes):
            continue
        left = intent.core[max(0, term.start - 2) : term.start]
        signed = bool(re.search(r"(?:^|[^\w)])[-−–]$", left))
        if not any(hit.negative == signed for hit in find_occurrences(source, term.text)):
            return False
    return True


def aligned_clause(intent: Intent, quote: str, unit: EvidenceUnit) -> Grounding | None:
    """Match either the clause itself or a clause with unambiguous local heading/table context."""
    if not unit.body_retrieval or unit.derived:
        return None
    cell = unit.content_type == ContentType.TABLE_CELL
    if not cell and (unit.content_type not in PROSE or intent.table is not None):
        return None
    if _EXAMPLE.match(quote):
        if not re.search(r"\bexample\b", intent.core, re.I) and not (
            intent.component.question_type == QuestionType.HOW_MANY
            and extract_terms(intent.core)
            and intent.keys <= keywords(quote)
        ):
            return None
    if not literal_scope(intent, quote, unit):
        return None
    local = keywords(quote) & intent.keys
    heading = unit.heading_text.rsplit(" > ", 1)[-1]
    title = _TITLE.match(unit.raw_text)
    title_keys = keywords(title["title"]) if title and local & keywords(title["title"]) else frozenset()
    scope = ((cell_keys(unit) if cell else keywords(heading) | title_keys) & intent.keys) - local
    if cell:
        if len(local | scope) < 2 or not local and len(scope) < 3:
            return None
    elif not local or (len(local) < min(2, len(intent.keys)) and not scope):
        return None
    keys = local | scope
    if not intent.required <= keywords(quote) | (cell_keys(unit) if cell else frozenset()):
        return None
    if intent.component.question_type == QuestionType.WHERE and not intent.keys <= keys:
        return None
    if intent.permission and intent.component.question_type == QuestionType.WHETHER:
        if not (intent.keys - _PERMISSION_WORDS) <= local:
            return None
    if (
        intent.component.question_type in {QuestionType.HOW, QuestionType.WHETHER}
        and _PRONOUN_OPEN.match(quote)
        and not intent.keys <= local
    ):
        return None
    if "target_inherited" in intent.component.flags and not keywords(" ".join(intent.component.target_terms)) <= keys:
        return None
    if not intent.codes and not cell and len(keys) * 2 < len(intent.keys):
        return None
    if intent.component.condition_terms and not set(intent.component.condition_terms) <= set(quote.lower().split()):
        return None
    span = extract_span(intent, quote, unit)
    if span is None:
        return None
    if span.kind == "clause" and not cell and len(local) < min(2, len(intent.keys)):
        return None
    if not polarity_agrees(intent, quote, span):
        return None
    return Grounding(span, local, scope)


def polarity_agrees(intent: Intent, quote: str, span: Span) -> bool:
    negative = list(_NEGATION.finditer(quote))
    question_type = intent.component.question_type
    if intent.negated:
        return question_type in _CLAUSE_TYPES and bool(negative or word_key("missing") in keywords(quote))
    if question_type == QuestionType.WHETHER:
        return all(span.start <= match.start() < span.end for match in negative)
    if question_type == QuestionType.HOW and span.kind in {"predicate", "method", "clause"}:
        return all(span.start <= match.start() < span.end for match in negative)
    return not negative


def changes_scope(intent: Intent, text: str) -> bool:
    """A nearby qualification needs review if it refers to the same subject or opens with an exception."""
    return bool(_FOLLOWING_LIMITATION.match(text)) or (
        bool(_QUALIFIER.search(text)) and len(keywords(text) & intent.keys) >= min(2, len(intent.keys))
    )


def _context_agrees(claim: Claim, intent: Intent, unit: EvidenceUnit) -> bool:
    if unit.content_type == ContentType.TABLE_CELL:
        return True
    candidate = claim.candidate
    start = unit.raw_text.find(candidate.quote)
    if start < 0:
        return False
    before = unit.raw_text[:start]
    after = unit.raw_text[start + len(candidate.quote) :]
    ranges = sentence_ranges(before)
    preceding = before[slice(*ranges[-1])] if ranges else ""
    ranges = sentence_ranges(after)
    following = after[slice(*ranges[0])] if ranges else ""
    if changes_scope(intent, preceding) or changes_scope(intent, following):
        return False
    for evidence_id in (unit.prev_id, unit.next_id):
        if evidence_id is None:
            continue
        neighbour = claim.store.load_unit(claim.document_id, evidence_id)
        if neighbour is None:
            return False
        if neighbour.section_id == unit.section_id and neighbour.content_type in PROSE:
            if changes_scope(intent, neighbour.raw_text):
                return False
    return True


def extractive_checks(claim: Claim) -> dict[CheckName, CheckResult]:
    """Re-derive the answer from the quote and stored scope during verification."""
    intent = intent_for(claim.component)
    candidate = claim.candidate
    unit = claim.unit
    ground = aligned_clause(intent, candidate.quote, unit) if unit is not None else None
    offsets = answer_offsets(claim)

    def check(name: CheckName, passed: bool, reason: str, failure: str, *, hard: bool = False) -> CheckResult:
        status = CheckStatus.PASS if passed else CheckStatus.FAIL if hard else CheckStatus.UNRESOLVED
        return CheckResult(
            name=name,
            rule_id=f"verify.{name.value}.extractive.v1",
            status=status,
            reason=reason if passed else failure,
        )

    expected = ground.span if ground else None
    return {
        CheckName.ANSWER_SPAN: offsets
        if offsets.status != CheckStatus.PASS
        else check(
            CheckName.ANSWER_SPAN,
            expected is not None
            and (candidate.page_start + expected.start, candidate.page_start + expected.end, expected.kind)
            == (candidate.answer_page_start, candidate.answer_page_end, candidate.answer_kind),
            "the clause rule reproduces the verbatim answer span",
            "the answer span differs from the span read by the clause rule",
            hard=True,
        ),
        CheckName.ENTITY: check(
            CheckName.ENTITY,
            ground is not None and not candidate.expansion_only,
            "the clause matches the question's subject and scope",
            "the subject or scope is unresolved",
            hard=True,
        ),
        CheckName.ATTRIBUTE: check(
            CheckName.ATTRIBUTE,
            ground is not None,
            "the clause rule identifies the requested relationship",
            "the requested relationship is unresolved",
        ),
        CheckName.VALUE: check(
            CheckName.VALUE,
            unit is not None and literal_scope(intent, candidate.quote, unit),
            "numerals and identifiers in the question agree with the source",
            "a required numeral or identifier differs",
            hard=True,
        ),
        CheckName.CONTEXT: check(
            CheckName.CONTEXT,
            unit is not None and _context_agrees(claim, intent, unit),
            "nearby text contains no qualification of the clause",
            "nearby text may qualify the proposed answer",
        ),
        CheckName.NEGATION: check(
            CheckName.NEGATION,
            expected is not None and polarity_agrees(intent, candidate.quote, expected),
            "the answer retains the polarity of the source clause",
            "the polarity or scope of negation is unclear",
        ),
        CheckName.CONDITION: check(
            CheckName.CONDITION,
            ground is not None,
            "the clause has no unresolved condition",
            "the clause has an unresolved condition or scope",
        ),
    }

"""The response model (SPEC §10; ARCHITECTURE §16.5, §16.7).

Every section is typed and frozen, and extra fields are refused. The model validates the invariants that the decision
depends on: an answer is never shown without a status that allows one, and every answer span is a verbatim slice of
an evidence quote at its page offsets. Retrieval scores, verification results and decision reasons are separate
sections, and BM25 is shown only as a raw rank value, never as a probability.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.conflict.detector import ConflictRelation, Impact
from app.ingestion.models import ExtractionMethod, QualityStatus

ENGINE_VERSION = "decision.v1"


class DecisionStatus(StrEnum):
    """The six outcomes of SPEC §9."""

    ANSWERED = "ANSWERED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    AMBIGUOUS_QUERY = "AMBIGUOUS_QUERY"
    CONFLICT = "CONFLICT"
    SOURCE_UNVERIFIED = "SOURCE_UNVERIFIED"
    PARTIAL = "PARTIAL"


class ReasonCode(StrEnum):
    """Why a status was chosen. The plain-text reasons carry the details."""

    ANSWER_VERIFIED = "answer_verified"
    RELAXED_GATE_USED = "relaxed_gate_used"
    UNSUPPORTED_QUESTION = "unsupported_question"
    AMBIGUOUS_QUESTION = "ambiguous_question"
    NO_CANDIDATES = "no_candidates"
    EXPANSION_ONLY = "expansion_only"
    NO_VERIFIED_ANSWER = "no_verified_answer"
    VERIFICATION_FAILED = "verification_failed"
    VERIFICATION_UNRESOLVED = "verification_unresolved"
    SOURCE_QUALITY = "source_quality"
    CONFLICT_CONFIRMED = "conflict_confirmed"
    CONFLICT_SUPERSESSION = "conflict_supersession"
    SCOPE_DIFFERS = "scope_differs"
    DATE_DIFFERS = "date_differs"
    POTENTIAL_DISCREPANCY = "potential_discrepancy"


class ItemRole(StrEnum):
    """How an evidence item is used: the answer, a passage shown for inspection, or one side of a conflict."""

    ANSWER = "answer"
    PASSAGE = "passage"
    CONFLICTING = "conflicting"


_RELATION_CODES: dict[ConflictRelation, ReasonCode] = {
    ConflictRelation.CONFIRMED_INCOMPATIBLE: ReasonCode.CONFLICT_CONFIRMED,
    ConflictRelation.EXPLICIT_SUPERSESSION: ReasonCode.CONFLICT_SUPERSESSION,
    ConflictRelation.DIFFERENT_SCOPE: ReasonCode.SCOPE_DIFFERS,
    ConflictRelation.DATED_CHANGE: ReasonCode.DATE_DIFFERS,
    ConflictRelation.POTENTIAL_DISCREPANCY: ReasonCode.POTENTIAL_DISCREPANCY,
}


def relation_reason_code(relation: ConflictRelation) -> ReasonCode | None:
    """The reason code that a relation contributes, or None for an agreement."""
    return _RELATION_CODES.get(relation)


# The precedence of SPEC §9 when no component is answered: a conflict is shown before anything else.
_NOT_ANSWERED_PRECEDENCE: tuple[DecisionStatus, ...] = (
    DecisionStatus.CONFLICT,
    DecisionStatus.SOURCE_UNVERIFIED,
    DecisionStatus.AMBIGUOUS_QUERY,
    DecisionStatus.INSUFFICIENT_EVIDENCE,
)


def aggregate_status(statuses: Sequence[DecisionStatus]) -> DecisionStatus:
    """The status of the whole question from its components (ARCHITECTURE §16.5).

    ANSWERED when every component is answered. PARTIAL when some are answered and some are not. Otherwise the first
    status of the SPEC §9 precedence that any component has.
    """
    if not statuses:
        raise ValueError("a question has at least one component")
    if all(status == DecisionStatus.ANSWERED for status in statuses):
        return DecisionStatus.ANSWERED
    if any(status == DecisionStatus.ANSWERED for status in statuses):
        return DecisionStatus.PARTIAL
    for status in _NOT_ANSWERED_PRECEDENCE:
        if status in statuses:
            return status
    raise ValueError(f"no precedence rule applies to {list(statuses)}")


class EvidenceItem(BaseModel):
    """A passage of the document. ``quote`` is verbatim: ``source_end - source_start == len(quote)``. It is None only
    for a conflicting passage that crosses a join between source spans, which cannot be quoted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(min_length=1)
    pdf_page: int = Field(ge=1)
    printed_page: str | None
    section: str | None
    quote: str | None
    source_start: int | None = Field(default=None, ge=0)
    source_end: int | None = Field(default=None, ge=0)
    quality_status: QualityStatus
    extraction_method: ExtractionMethod
    roles: tuple[ItemRole, ...]
    component_ids: tuple[str, ...]

    @model_validator(mode="after")
    def _offsets_match_quote(self) -> EvidenceItem:
        if self.quote is None:
            if self.source_start is not None or self.source_end is not None:
                raise ValueError("an unquotable passage has no source offsets")
            return self
        if self.source_start is None or self.source_end is None:
            raise ValueError("a quoted passage needs its source offsets")
        if self.source_end - self.source_start != len(self.quote):
            raise ValueError("the source offsets do not match the length of the quote")
        return self


class AnswerSpan(BaseModel):
    """A value or marker that a rule determined, with its offsets in the page's raw text (SPEC §6)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)
    component_id: str = Field(min_length=1)
    pdf_page: int = Field(ge=1)
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def _ordered(self) -> AnswerSpan:
        if self.end <= self.start:
            raise ValueError("an answer span must end after it starts")
        return self


class ComponentOutcome(BaseModel):
    """The status of one component of the question (SPEC §9, PARTIAL)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    component_id: str
    text: str
    question_type: str
    status: DecisionStatus
    reason_codes: tuple[ReasonCode, ...]
    reasons: tuple[str, ...]
    evidence_ids: tuple[str, ...]


class CheckOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    status: str
    reason: str


class CandidateVerification(BaseModel):
    """The verifier's report for one candidate, with whether the policy accepted it (ARCHITECTURE §16.1)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str
    component_id: str
    verdict: str
    accepted: bool
    checks: tuple[CheckOutcome, ...]
    reasons: tuple[str, ...]


class RetrievalEntry(BaseModel):
    """One candidate of the search. ``raw_bm25`` is the FTS5 rank value: lower is better, uncalibrated, and never a
    probability (SPEC §9)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rank: int = Field(ge=1)
    evidence_id: str
    via: str
    rule_ids: tuple[str, ...]
    raw_bm25: float


class RetrievalSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    component_id: str
    query: str
    k: int = Field(ge=1)
    expansion_k: int = Field(ge=0)
    context_window: int = Field(ge=0)
    statistics: str
    rules_fingerprint: str
    original_hits: int = Field(ge=0)
    expansion_hits: int = Field(ge=0)
    duplicates_removed: int = Field(ge=0)
    entries: tuple[RetrievalEntry, ...]


class ConflictFinding(BaseModel):
    """A difference between two passages that the screen reported. It is never resolved silently (SPEC §8)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    component_id: str
    relation: ConflictRelation
    impact: Impact
    first_evidence_id: str
    second_evidence_id: str
    first_claim: str
    second_claim: str
    first_quote: str | None
    second_quote: str | None
    reason: str


class ScreenSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    component_id: str
    screened: bool
    units_with_every_word: int = Field(ge=0)
    pieces_matched: int = Field(ge=0)
    pieces_with_claims: int = Field(ge=0)
    agreeing_pairs: int = Field(ge=0)
    relations: int = Field(ge=0)
    derived_pieces: int = Field(ge=0)
    unquotable_pieces: int = Field(ge=0)
    note: str


class PolicySummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    calibrated: bool
    sha256: str
    gates: dict[str, bool]


class QAResponse(BaseModel):
    """The answer to one question about one document (SPEC §10).

    Invariants, checked when the model is built: answer spans appear only for ANSWERED or PARTIAL; ANSWERED means every
    component is answered; PARTIAL means a mix; the status is the aggregate of the component statuses; every answer
    span names a quoted evidence item and matches its quote at the span's offsets.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: DecisionStatus
    question: str
    answer_spans: tuple[AnswerSpan, ...]
    evidence: tuple[EvidenceItem, ...]
    warnings: tuple[str, ...]
    reason_codes: tuple[ReasonCode, ...]
    components: tuple[ComponentOutcome, ...]
    retrieval: tuple[RetrievalSummary, ...]
    verification: tuple[CandidateVerification, ...]
    conflicts: tuple[ConflictFinding, ...]
    screening: tuple[ScreenSummary, ...]
    policy: PolicySummary
    engine_version: str = ENGINE_VERSION

    @model_validator(mode="after")
    def _check_invariants(self) -> QAResponse:
        answered = [component.status == DecisionStatus.ANSWERED for component in self.components]
        if self.answer_spans and self.status not in (DecisionStatus.ANSWERED, DecisionStatus.PARTIAL):
            raise ValueError(f"{self.status.value} must not carry an answer span")
        if self.components and aggregate_status([component.status for component in self.components]) != self.status:
            raise ValueError("the status is not the aggregate of the component statuses")
        if self.status == DecisionStatus.ANSWERED and not self.answer_spans:
            raise ValueError("ANSWERED needs at least one answer span")
        if self.status == DecisionStatus.PARTIAL and (not any(answered) or all(answered) or not self.answer_spans):
            raise ValueError("PARTIAL needs answered and unanswered components and at least one answer span")
        known = {item.evidence_id for item in self.evidence}
        for component in self.components:
            missing = [evidence_id for evidence_id in component.evidence_ids if evidence_id not in known]
            if missing:
                raise ValueError(f"component {component.component_id} names evidence not in the response: {missing}")
        for span in self.answer_spans:
            if not any(_span_matches_item(span, item) for item in self.evidence):
                raise ValueError(f"answer span {span.text!r} is not a verbatim slice of its evidence quote")
        return self


def _span_matches_item(span: AnswerSpan, item: EvidenceItem) -> bool:
    if item.evidence_id != span.evidence_id or item.quote is None or item.source_start is None:
        return False
    if item.pdf_page != span.pdf_page:
        return False
    if span.start < item.source_start or span.end > item.source_start + len(item.quote):
        return False
    offset = span.start - item.source_start
    return item.quote[offset : offset + (span.end - span.start)] == span.text

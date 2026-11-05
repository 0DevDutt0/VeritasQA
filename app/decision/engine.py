"""The decision step: one validated answer per question (SPEC §9, §10; ARCHITECTURE §16).

``answer`` runs the pipeline of ARCHITECTURE §16 for one document: analysis, search, selection, verification, conflict
screening, the component status, the overall status, and the response. It does not raise for "no answer". A question
without supported evidence returns a status and the passages that were examined.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.conflict import ConflictConfig, load_conflict_config
from app.conflict.detector import ConflictScreen, Impact, Relation, screen_component
from app.decision.errors import DecisionError
from app.decision.policy import GATE_OF_CHECK, AcceptancePolicy, accepts, load_policy, relaxed_checks
from app.decision.response import (
    ENGINE_VERSION,
    AnswerSpan,
    CandidateVerification,
    CheckOutcome,
    ComponentOutcome,
    ConflictFinding,
    DecisionStatus,
    EvidenceItem,
    ItemRole,
    PolicySummary,
    QAResponse,
    ReasonCode,
    RetrievalEntry,
    RetrievalSummary,
    ScreenSummary,
    aggregate_status,
    relation_reason_code,
)
from app.document_structure.models import EvidenceUnit
from app.evidence.selection import AnswerCandidate, ComponentSelection, ComponentStatus, select_candidates
from app.ingestion.models import QualityStatus
from app.question_processing.analysis import QuestionAnalysis, QuestionComponent, QuestionType, analyze
from app.retrieval.bm25 import RetrievalResult, search
from app.retrieval.config import RetrievalConfig, load_retrieval_config
from app.retrieval.rules import RuleSet
from app.storage import Store
from app.storage.store import PageRow
from app.verification import CheckName, CheckStatus, VerificationReport, verify
from app.verification.vocabulary import ANSWER_TYPES

SCREEN_NOTE = (
    "Units that contain every target word of the question, checked sentence by sentence with the exact check. A passage "
    "without every target word is not compared (no synonyms in V1, D58)."
)
UNSCREENED_NOTE = "Not screened: the component is not an answer type with a target word."
PASSAGE_NOTE = (
    "Shown for inspection. No rule gives a verified answer for this kind of question (SPEC §6), so none is claimed."
)
_OPEN = (CheckStatus.FAIL, CheckStatus.UNRESOLVED)


@dataclass(frozen=True)
class _Judgement:
    """One candidate, its verifier report and the policy's decision on it."""

    candidate: AnswerCandidate
    report: VerificationReport
    accepted: bool
    relaxed: tuple[CheckName, ...]


@dataclass(frozen=True)
class _Decided:
    """One component's status, with the judgements and the screen it was decided from."""

    component: QuestionComponent
    selection: ComponentSelection
    judgements: tuple[_Judgement, ...]
    screen: ConflictScreen
    status: DecisionStatus
    reason_codes: tuple[ReasonCode, ...]
    reasons: tuple[str, ...]


@dataclass
class _Row:
    evidence_id: str
    pdf_page: int
    ordinal: int
    printed_page: str | None
    heading: str
    quality: str
    quote: str | None
    start: int | None
    end: int | None
    roles: list[ItemRole]
    components: list[str]


class _EvidenceTable:
    """The passages of one response: one row per quoted span. A span used by two components is one row."""

    def __init__(self, store: Store, document_id: str) -> None:
        self._store = store
        self._document_id = document_id
        self._rows: dict[tuple[str, int | None, int | None], _Row] = {}
        self._methods: dict[int, str] = {}

    def add(
        self,
        *,
        evidence_id: str,
        pdf_page: int,
        ordinal: int,
        printed_page: str | None,
        heading: str,
        quality: str,
        quote: str | None,
        start: int | None,
        end: int | None,
        role: ItemRole,
        component_id: str,
    ) -> None:
        key = (evidence_id, start, end)
        row = self._rows.get(key)
        if row is None:
            row = _Row(evidence_id, pdf_page, ordinal, printed_page, heading, quality, quote, start, end, [], [])
            self._rows[key] = row
        if role not in row.roles:
            row.roles.append(role)
        if component_id not in row.components:
            row.components.append(component_id)

    def _method(self, pdf_page: int) -> str:
        if pdf_page not in self._methods:
            self._methods[pdf_page] = self._store.page_extraction_method(self._document_id, pdf_page)
        return self._methods[pdf_page]

    def items(self) -> tuple[EvidenceItem, ...]:
        ordered = sorted(
            self._rows.values(),
            key=lambda row: (row.pdf_page, row.ordinal, -1 if row.start is None else row.start, row.evidence_id),
        )
        return tuple(
            EvidenceItem(
                evidence_id=row.evidence_id,
                pdf_page=row.pdf_page,
                printed_page=row.printed_page,
                section=row.heading or None,
                quote=row.quote,
                source_start=row.start,
                source_end=row.end,
                quality_status=row.quality,
                extraction_method=self._method(row.pdf_page),
                roles=tuple(row.roles),
                component_ids=tuple(row.components),
            )
            for row in ordered
        )


def answer(
    store: Store,
    document_id: str,
    question: str,
    policy: AcceptancePolicy | None = None,
    *,
    retrieval_config: RetrievalConfig | None = None,
    rules: RuleSet | None = None,
    conflict_config: ConflictConfig | None = None,
) -> QAResponse:
    """Answer one question about one document (ARCHITECTURE §16).

    ``policy``, ``retrieval_config`` and ``conflict_config`` default to the files in ``config/``. ``rules`` defaults to
    the retrieval rule file (no rule is approved in V1, D43). Read only: the store is not changed. Raises
    :class:`app.question_processing.errors.QuestionError` for an empty question and
    :class:`app.common.errors.StorageError` for an unknown document.
    """
    active_policy = policy if policy is not None else load_policy()
    active_conflicts = conflict_config if conflict_config is not None else load_conflict_config()
    settings = retrieval_config if retrieval_config is not None else load_retrieval_config()
    analysis = analyze(question)
    retrieved, units = _retrieve(store, document_id, analysis, settings, rules)
    selection = select_candidates(analysis, retrieved, units)
    decided: list[_Decided] = []
    for component, component_selection in zip(analysis.components, selection.components):
        judgements = tuple(
            _judge(candidate, analysis, store, document_id, active_policy)
            for candidate in component_selection.candidates
        )
        screen = screen_component(store, document_id, component, active_conflicts)
        decided.append(_decide(component, component_selection, judgements, screen))
    response = _respond(analysis, decided, retrieved, units, store, document_id, active_policy)
    notice = _unread_page_notice(store.page_rows(document_id))
    if notice is None:
        return response
    return response.model_copy(update={"warnings": response.warnings + (notice,)})


def _unread_page_notice(rows: Sequence[PageRow]) -> str | None:
    """A warning that names every page whose text could not be fully read, or ``None`` when every page is readable.

    An unread page has quality ``unverified``: its stored text may be incomplete, and its images are not read. Nothing on
    such a page is accepted as evidence (SOURCE_UNVERIFIED). The status and the answer spans do not change (D123).
    """
    unread = [row.pdf_page for row in rows if row.quality_status == QualityStatus.UNVERIFIED.value]
    if not unread:
        return None
    pages = ", ".join(str(page) for page in unread)
    if len(unread) == 1:
        subject, pronoun = f"Page {pages}", "it"
    else:
        subject, pronoun = f"Pages {pages}", "them"
    return (
        f"{subject} could not be fully read: the stored text may be incomplete, and images on {pronoun} are not read. "
        f"Nothing on {pronoun} is accepted as evidence."
    )


def _retrieve(
    store: Store,
    document_id: str,
    analysis: QuestionAnalysis,
    settings: RetrievalConfig,
    rules: RuleSet | None,
) -> tuple[dict[str, RetrievalResult], dict[str, EvidenceUnit]]:
    retrieved: dict[str, RetrievalResult] = {}
    units: dict[str, EvidenceUnit] = {}
    for component in analysis.components:
        if not component.searchable:
            continue
        result = search(store, document_id, component.retrieval_query, config=settings, rules=rules)
        retrieved[component.component_id] = result
        for candidate in result.candidates:
            if candidate.evidence_id not in units:
                unit = store.load_unit(document_id, candidate.evidence_id)
                if unit is not None:
                    units[candidate.evidence_id] = unit
    return retrieved, units


def _judge(
    candidate: AnswerCandidate,
    analysis: QuestionAnalysis,
    store: Store,
    document_id: str,
    policy: AcceptancePolicy,
) -> _Judgement:
    report = verify(candidate, analysis, store, document_id)
    accepted = accepts(report, policy)
    return _Judgement(candidate, report, accepted, relaxed_checks(report, policy) if accepted else ())


def _relations(screen: ConflictScreen, impact: Impact) -> list[Relation]:
    return [relation for relation in screen.relations if relation.impact == impact]


def _codes_of(relations: list[Relation]) -> tuple[ReasonCode, ...]:
    codes: list[ReasonCode] = []
    for relation in relations:
        code = relation_reason_code(relation.kind)
        if code is not None and code not in codes:
            codes.append(code)
    return tuple(codes)


def _reasons_of(relations: list[Relation]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(relation.reason for relation in relations))


def _source_blocked(report: VerificationReport) -> bool:
    """True when the only open checks come from the page's quality: source quality, and context, which D62 reads from
    the same page status. The rule reads the check statuses, never the text of the reasons."""
    open_names = {check.name for check in report.checks if check.status in _OPEN}
    return CheckName.SOURCE_QUALITY in open_names and open_names <= {CheckName.SOURCE_QUALITY, CheckName.CONTEXT}


def _check_reasons(judgements: tuple[_Judgement, ...]) -> tuple[str, ...]:
    reasons: list[str] = []
    for judgement in judgements:
        for check in judgement.report.checks:
            if check.status in _OPEN:
                reasons.append(f"{check.name.value}: {check.reason}")
    return tuple(dict.fromkeys(reasons))


def _decide(
    component: QuestionComponent,
    selection: ComponentSelection,
    judgements: tuple[_Judgement, ...],
    screen: ConflictScreen,
) -> _Decided:
    """The status of one component, by the rules of ARCHITECTURE §16.4."""

    def decided(status: DecisionStatus, codes: tuple[ReasonCode, ...], reasons: tuple[str, ...]) -> _Decided:
        return _Decided(component, selection, judgements, screen, status, codes, reasons)

    if not component.searchable:
        code = (
            ReasonCode.UNSUPPORTED_QUESTION
            if component.question_type == QuestionType.UNSUPPORTED
            else ReasonCode.AMBIGUOUS_QUESTION
        )
        return decided(DecisionStatus.AMBIGUOUS_QUERY, (code,), (component.reason or "the question cannot be searched",))
    conflict = _relations(screen, Impact.CONFLICT)
    source = _relations(screen, Impact.SOURCE)
    ambiguous = _relations(screen, Impact.AMBIGUOUS)
    accepted = [judgement for judgement in judgements if judgement.accepted]
    if conflict:
        return decided(DecisionStatus.CONFLICT, _codes_of(conflict), _reasons_of(conflict))
    if source:
        reasons = _reasons_of(source) + _check_reasons(judgements)
        return decided(DecisionStatus.SOURCE_UNVERIFIED, (ReasonCode.SOURCE_QUALITY,) + _codes_of(source), reasons)
    if accepted:
        if ambiguous:
            return decided(DecisionStatus.AMBIGUOUS_QUERY, _codes_of(ambiguous), _reasons_of(ambiguous))
        codes: tuple[ReasonCode, ...] = (ReasonCode.ANSWER_VERIFIED,)
        reasons = (
            f"{len(accepted)} passage(s) pass every required check, and no other passage of the document gives a "
            "different value for the same subject",
        )
        if any(judgement.relaxed for judgement in accepted):
            codes = codes + (ReasonCode.RELAXED_GATE_USED,)
            reasons = reasons + ("an open check was relaxed by the acceptance policy (see the warnings)",)
        return decided(DecisionStatus.ANSWERED, codes, reasons)
    source_only = tuple(judgement for judgement in judgements if _source_blocked(judgement.report))
    if source_only:
        return decided(DecisionStatus.SOURCE_UNVERIFIED, (ReasonCode.SOURCE_QUALITY,), _check_reasons(source_only))
    if ambiguous:
        return decided(DecisionStatus.AMBIGUOUS_QUERY, _codes_of(ambiguous), _reasons_of(ambiguous))
    codes, reasons = _insufficient(component, selection, judgements)
    return decided(DecisionStatus.INSUFFICIENT_EVIDENCE, codes, reasons)


def _insufficient(
    component: QuestionComponent,
    selection: ComponentSelection,
    judgements: tuple[_Judgement, ...],
) -> tuple[tuple[ReasonCode, ...], tuple[str, ...]]:
    if not selection.candidates:
        return (ReasonCode.NO_CANDIDATES,), selection.reasons or ("no passage was found for this question",)
    if selection.status == ComponentStatus.EXPANSION_ONLY:
        return (ReasonCode.EXPANSION_ONLY,), selection.reasons
    if component.question_type not in ANSWER_TYPES:
        return (ReasonCode.NO_VERIFIED_ANSWER,), (PASSAGE_NOTE,)
    failed = any(check.status == CheckStatus.FAIL for judgement in judgements for check in judgement.report.checks)
    code = ReasonCode.VERIFICATION_FAILED if failed else ReasonCode.VERIFICATION_UNRESOLVED
    return (code,), _check_reasons(judgements)


def _overall_codes(decided: list[_Decided]) -> tuple[ReasonCode, ...]:
    codes: list[ReasonCode] = []
    for item in decided:
        for code in item.reason_codes:
            if code not in codes:
                codes.append(code)
    return tuple(codes)


def _answer_span(candidate: AnswerCandidate, component_id: str) -> AnswerSpan:
    if candidate.answer_span is None or candidate.answer_page_start is None or candidate.answer_page_end is None:
        raise DecisionError(f"internal: the accepted candidate {candidate.evidence_id} has no answer span")
    return AnswerSpan(
        text=candidate.answer_span,
        evidence_id=candidate.evidence_id,
        component_id=component_id,
        pdf_page=candidate.pdf_page,
        start=candidate.answer_page_start,
        end=candidate.answer_page_end,
    )


def _verification_entry(judgement: _Judgement, component_id: str) -> CandidateVerification:
    return CandidateVerification(
        evidence_id=judgement.candidate.evidence_id,
        component_id=component_id,
        verdict=judgement.report.verdict.value,
        accepted=judgement.accepted,
        checks=tuple(
            CheckOutcome(name=check.name.value, status=check.status.value, reason=check.reason)
            for check in judgement.report.checks
        ),
        reasons=judgement.report.reasons,
    )


def _conflict_entry(relation: Relation, screen: ConflictScreen, component_id: str) -> ConflictFinding:
    first = screen.pieces[relation.first]
    second = screen.pieces[relation.second]
    return ConflictFinding(
        component_id=component_id,
        relation=relation.kind,
        impact=relation.impact,
        first_evidence_id=first.evidence_id,
        second_evidence_id=second.evidence_id,
        first_claim=relation.first_claim,
        second_claim=relation.second_claim,
        first_quote=first.text if first.quotable else None,
        second_quote=second.text if second.quotable else None,
        reason=relation.reason,
    )


def _screen_entry(screen: ConflictScreen) -> ScreenSummary:
    counts = screen.counts
    return ScreenSummary(
        component_id=screen.component_id,
        screened=screen.screened,
        units_with_every_word=counts.units_with_every_word,
        pieces_matched=counts.pieces_matched,
        pieces_with_claims=counts.pieces_with_claims,
        agreeing_pairs=screen.agreeing_pairs,
        relations=len(screen.relations),
        derived_pieces=counts.derived_pieces,
        unquotable_pieces=counts.unquotable_pieces,
        note=SCREEN_NOTE if screen.screened else UNSCREENED_NOTE,
    )


def _retrieval_summary(component_id: str, result: RetrievalResult) -> RetrievalSummary:
    trace = result.trace
    return RetrievalSummary(
        component_id=component_id,
        query=result.query,
        k=trace.k,
        expansion_k=trace.expansion_k,
        context_window=trace.context_window,
        statistics=trace.statistics,
        rules_fingerprint=trace.rules_fingerprint,
        original_hits=trace.original_hits,
        expansion_hits=trace.expansion_hits,
        duplicates_removed=trace.duplicates_removed,
        entries=tuple(
            RetrievalEntry(
                rank=candidate.rank,
                evidence_id=candidate.evidence_id,
                via=candidate.via,
                rule_ids=candidate.rule_ids,
                raw_bm25=candidate.bm25_raw,
            )
            for candidate in result.candidates
        ),
    )


def _warnings(
    evidence: tuple[EvidenceItem, ...],
    store: Store,
    document_id: str,
    relaxed_notes: list[str],
) -> tuple[str, ...]:
    messages: list[str] = []
    checked: set[int] = set()
    for item in evidence:
        if item.quality_status == QualityStatus.VERIFIED or item.pdf_page in checked:
            continue
        checked.add(item.pdf_page)
        codes = store.page_warning_codes(document_id, item.pdf_page)
        detail = f"its stored issues are {', '.join(codes)}" if codes else "no issue is stored for it"
        messages.append(f"page {item.pdf_page} is {item.quality_status.value}; {detail}")
    messages.extend(relaxed_notes)
    return tuple(dict.fromkeys(messages))


def _respond(
    analysis: QuestionAnalysis,
    decided: list[_Decided],
    retrieved: dict[str, RetrievalResult],
    units: dict[str, EvidenceUnit],
    store: Store,
    document_id: str,
    policy: AcceptancePolicy,
) -> QAResponse:
    """Assemble and validate the response. The status is the aggregate of the component statuses (ARCHITECTURE §16.5)."""
    table = _EvidenceTable(store, document_id)
    components: list[ComponentOutcome] = []
    spans: list[AnswerSpan] = []
    verification: list[CandidateVerification] = []
    conflicts: list[ConflictFinding] = []
    screening: list[ScreenSummary] = []
    retrieval: list[RetrievalSummary] = []
    relaxed_notes: list[str] = []

    for item in decided:
        component_id = item.component.component_id
        answered_component = item.status == DecisionStatus.ANSWERED
        evidence_ids: list[str] = []
        for judgement in item.judgements:
            candidate = judgement.candidate
            unit = units[candidate.evidence_id]
            answered = answered_component and judgement.accepted
            table.add(
                evidence_id=candidate.evidence_id,
                pdf_page=candidate.pdf_page,
                ordinal=unit.ordinal,
                printed_page=unit.printed_page,
                heading=unit.heading_text,
                quality=unit.extraction_quality.value,
                quote=candidate.quote,
                start=candidate.page_start,
                end=candidate.page_end,
                role=ItemRole.ANSWER if answered else ItemRole.PASSAGE,
                component_id=component_id,
            )
            evidence_ids.append(candidate.evidence_id)
            verification.append(_verification_entry(judgement, component_id))
            if answered:
                spans.append(_answer_span(candidate, component_id))
            if judgement.accepted and judgement.relaxed:
                names = ", ".join(GATE_OF_CHECK[name] for name in judgement.relaxed)
                relaxed_notes.append(
                    f"{candidate.evidence_id} is accepted with an open check relaxed by the policy ({names})"
                )
        for relation in item.screen.relations:
            conflicts.append(_conflict_entry(relation, item.screen, component_id))
            for index in (relation.first, relation.second):
                piece = item.screen.pieces[index]
                table.add(
                    evidence_id=piece.evidence_id,
                    pdf_page=piece.pdf_page,
                    ordinal=piece.ordinal,
                    printed_page=piece.printed_page,
                    heading=piece.heading_text,
                    quality=piece.extraction_quality,
                    quote=piece.text if piece.quotable else None,
                    start=piece.page_start,
                    end=piece.page_end,
                    role=ItemRole.CONFLICTING,
                    component_id=component_id,
                )
                evidence_ids.append(piece.evidence_id)
        components.append(
            ComponentOutcome(
                component_id=component_id,
                text=item.component.text,
                question_type=item.component.question_type.value,
                status=item.status,
                reason_codes=item.reason_codes,
                reasons=item.reasons,
                evidence_ids=tuple(dict.fromkeys(evidence_ids)),
            )
        )
        screening.append(_screen_entry(item.screen))
        if component_id in retrieved:
            retrieval.append(_retrieval_summary(component_id, retrieved[component_id]))

    evidence = table.items()
    return QAResponse(
        status=aggregate_status([item.status for item in decided]),
        question=analysis.question,
        answer_spans=tuple(dict.fromkeys(spans)),
        evidence=evidence,
        warnings=_warnings(evidence, store, document_id, relaxed_notes),
        reason_codes=_overall_codes(decided),
        components=tuple(components),
        retrieval=tuple(retrieval),
        verification=tuple(verification),
        conflicts=tuple(conflicts),
        screening=tuple(screening),
        policy=PolicySummary(
            version=policy.version,
            calibrated=policy.calibrated,
            sha256=policy.sha256,
            gates=dict(policy.gates),
        ),
        engine_version=ENGINE_VERSION,
    )

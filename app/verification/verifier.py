"""The verifier: runs the checks and gives one verdict per candidate (ARCHITECTURE §15, D61).

``verify(candidate, analysis, store, document_id)`` is the entry point. Verdict rule: FAIL when any required check
fails; PASS when every required check passes (NOT_APPLICABLE is allowed only for the attribute and value checks);
UNRESOLVED otherwise. Conflict screening is pending in the decision step (D66). It is listed in the report and is not
part of the verdict, so a PASS here is a candidate-level result, not a final answer.
"""

from __future__ import annotations

from app.common.errors import StorageError
from app.evidence.selection import AnswerCandidate
from app.question_processing.analysis import QuestionAnalysis, QuestionComponent, QuestionType
from app.retrieval.terms import extract_terms
from app.storage import Store
from app.verification.checks import CHECKS, Claim
from app.verification.errors import VerificationError
from app.verification.report import CheckName, CheckResult, CheckStatus, Verdict, VerificationReport
from app.verification.vocabulary import EXPECTED_RULE_IDS, VERIFIER_VERSION

# The order of the report. Conflict screening is listed here and is pending (D66).
ORDER: tuple[CheckName, ...] = (
    CheckName.QUOTATION,
    CheckName.LOCATION,
    CheckName.ANSWER_SPAN,
    CheckName.ENTITY,
    CheckName.ATTRIBUTE,
    CheckName.VALUE,
    CheckName.CONTEXT,
    CheckName.NEGATION,
    CheckName.CONDITION,
    CheckName.CONFLICT,
    CheckName.SOURCE_QUALITY,
    CheckName.CANDIDATE_FLAGS,
)
PENDING: tuple[CheckName, ...] = (CheckName.CONFLICT,)

# Every question type requires the same checks (D65). The types differ only in the answer-span rule, which is applied
# inside the answer-span check, so a passage-only type can never pass.
REQUIRED: tuple[CheckName, ...] = tuple(name for name in ORDER if name not in PENDING)
REQUIRED_BY_TYPE: dict[QuestionType, tuple[CheckName, ...]] = {
    question_type: REQUIRED for question_type in EXPECTED_RULE_IDS
}

# A check may be NOT_APPLICABLE only where the question has no property word or no value (ARCHITECTURE §15).
NOT_APPLICABLE_ALLOWED = frozenset({CheckName.ATTRIBUTE, CheckName.VALUE})

_CONFLICT_REASON = (
    "conflict screening compares passages across the whole document, so it runs in the decision step (D66)"
)


def _component_of(analysis: QuestionAnalysis, candidate: AnswerCandidate) -> QuestionComponent:
    matches = [component for component in analysis.components if component.component_id == candidate.component_id]
    if len(matches) != 1:
        raise VerificationError(f"the analysis has no single component {candidate.component_id}")
    component = matches[0]
    if component.question_type != candidate.question_type:
        raise VerificationError(
            f"component {component.component_id} is {component.question_type.value}, "
            f"but the candidate is {candidate.question_type.value}"
        )
    if not component.searchable:
        raise VerificationError(f"component {component.component_id} is not searchable, so it has no candidates")
    if candidate.question_type not in REQUIRED_BY_TYPE:
        raise VerificationError(f"no verification rules exist for {candidate.question_type.value}")
    return component


def _page_text(store: Store, document_id: str, pdf_page: int) -> str | None:
    try:
        return store.page_texts(document_id, [pdf_page]).get(pdf_page)
    except StorageError:
        return None


def _verdict(results: dict[CheckName, CheckResult]) -> Verdict:
    required = [results[name] for name in REQUIRED]
    if any(result.status == CheckStatus.FAIL for result in required):
        return Verdict.FAIL
    for result in required:
        if result.status == CheckStatus.PASS:
            continue
        if result.status == CheckStatus.NOT_APPLICABLE and result.name in NOT_APPLICABLE_ALLOWED:
            continue
        return Verdict.UNRESOLVED
    return Verdict.PASS


def verify(
    candidate: AnswerCandidate,
    analysis: QuestionAnalysis,
    store: Store,
    document_id: str,
) -> VerificationReport:
    """Verify one P5 candidate against the stored text of ``document_id``. Read only; the store is not changed."""
    component = _component_of(analysis, candidate)
    claim = Claim(
        candidate=candidate,
        component=component,
        store=store,
        document_id=document_id,
        page_text=_page_text(store, document_id, candidate.pdf_page),
        unit=store.load_unit(document_id, candidate.evidence_id),
        question_terms=extract_terms(component.text),
    )
    results: dict[CheckName, CheckResult] = {}
    for name in ORDER:
        if name in PENDING:
            results[name] = CheckResult(
                name=name,
                rule_id=f"verify.{name.value}.v1",
                status=CheckStatus.PENDING,
                reason=_CONFLICT_REASON,
            )
        else:
            results[name] = CHECKS[name](claim)
    checks = tuple(results[name] for name in ORDER)
    reasons = tuple(
        f"{result.name.value}: {result.reason}"
        for result in checks
        if result.status in (CheckStatus.FAIL, CheckStatus.UNRESOLVED)
    )
    return VerificationReport(
        verifier_version=VERIFIER_VERSION,
        document_id=document_id,
        evidence_id=candidate.evidence_id,
        component_id=candidate.component_id,
        question_type=candidate.question_type,
        verdict=_verdict(results),
        checks=checks,
        pending=PENDING,
        reasons=reasons,
    )

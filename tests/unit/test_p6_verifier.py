"""The verdict rule, the required checks per type, the input errors and the pending conflict check (ARCHITECTURE §15).

The verdict rule is tested on the verifier's own function and on whole reports. Each report comes from the real P4
and P5 steps on a labelled synthetic document.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.question_processing.analysis import QuestionType, analyze
from app.verification import REQUIRED_BY_TYPE, VerificationError, verify
from app.verification.report import CheckName, CheckResult, CheckStatus, Verdict
from app.verification.verifier import NOT_APPLICABLE_ALLOWED, ORDER, PENDING, REQUIRED, _verdict
from app.verification.vocabulary import EXPECTED_RULE_IDS
from tests.fixtures.verification_docs import candidate_quoting, main_items, selection_for, stored_document

DOC = "doc-" + "9" * 16
LIMIT_Q = "How many days is the limit for loans?"
LIMIT_FRAGMENT = "The limit for loans is 30 days after approval."


@pytest.fixture(scope="module")
def main():
    store = stored_document(DOC, main_items())
    yield store
    store.close()


def _all_passing() -> dict[CheckName, CheckResult]:
    return {
        name: CheckResult(name=name, rule_id=f"verify.{name.value}.v1", status=CheckStatus.PASS, reason="ok")
        for name in REQUIRED
    }


def _with(results: dict[CheckName, CheckResult], name: CheckName, status: CheckStatus) -> dict[CheckName, CheckResult]:
    changed = dict(results)
    changed[name] = replace(results[name], status=status)
    return changed


def test_every_question_type_with_a_rule_requires_the_same_checks():
    assert set(REQUIRED_BY_TYPE) == set(EXPECTED_RULE_IDS)
    assert all(required == REQUIRED for required in REQUIRED_BY_TYPE.values())
    assert len(REQUIRED) == 11
    assert CheckName.CANDIDATE_FLAGS in REQUIRED
    assert PENDING == (CheckName.CONFLICT,)
    assert CheckName.CONFLICT not in REQUIRED


def test_the_report_order_is_the_spec_order_with_the_flag_check_last():
    assert [name.value for name in ORDER] == [
        "quotation",
        "location",
        "answer_span",
        "entity",
        "attribute",
        "value",
        "context",
        "negation",
        "condition",
        "conflict",
        "source_quality",
        "candidate_flags",
    ]


def test_not_applicable_is_allowed_only_for_the_attribute_and_value_checks():
    assert NOT_APPLICABLE_ALLOWED == {CheckName.ATTRIBUTE, CheckName.VALUE}


def test_all_passing_with_attribute_and_value_not_applicable_is_a_pass():
    results = _all_passing()
    results = _with(results, CheckName.ATTRIBUTE, CheckStatus.NOT_APPLICABLE)
    results = _with(results, CheckName.VALUE, CheckStatus.NOT_APPLICABLE)
    assert _verdict(results) == Verdict.PASS


@pytest.mark.parametrize("name", [CheckName.ENTITY, CheckName.LOCATION, CheckName.ANSWER_SPAN, CheckName.CONTEXT])
def test_not_applicable_on_any_other_required_check_is_unresolved(name):
    assert _verdict(_with(_all_passing(), name, CheckStatus.NOT_APPLICABLE)) == Verdict.UNRESOLVED


def test_any_fail_gives_fail_even_beside_an_unresolved_check():
    results = _with(_all_passing(), CheckName.CONTEXT, CheckStatus.UNRESOLVED)
    results = _with(results, CheckName.VALUE, CheckStatus.FAIL)
    assert _verdict(results) == Verdict.FAIL


def test_anything_else_that_is_not_a_pass_gives_unresolved():
    assert _verdict(_with(_all_passing(), CheckName.SOURCE_QUALITY, CheckStatus.UNRESOLVED)) == Verdict.UNRESOLVED


def test_a_pending_conflict_check_is_not_part_of_the_verdict():
    results = _all_passing()
    results[CheckName.CONFLICT] = CheckResult(
        name=CheckName.CONFLICT,
        rule_id="verify.conflict.v1",
        status=CheckStatus.PENDING,
        reason="pending",
    )
    assert _verdict(results) == Verdict.PASS


def test_a_clean_candidate_passes_and_lists_conflict_as_pending(main):
    analysis, selection = selection_for(main, DOC, LIMIT_Q)
    candidate = candidate_quoting(selection, LIMIT_FRAGMENT)
    report = verify(candidate, analysis, main, DOC)
    assert report.verdict == Verdict.PASS
    assert report.reasons == ()
    assert report.pending == (CheckName.CONFLICT,)
    assert report.check(CheckName.CONFLICT).status == CheckStatus.PENDING
    assert [check.name for check in report.checks] == list(ORDER)
    assert all(check.rule_id == f"verify.{check.name.value}.v1" for check in report.checks)


def test_a_failing_candidate_gives_fail_even_when_a_flag_leaves_it_unresolved(main):
    analysis, selection = selection_for(main, DOC, LIMIT_Q)
    cell = candidate_quoting(selection, "Loans limit: 30 days")
    expanded = replace(cell, retrieval=replace(cell.retrieval, via="expansion"))
    report = verify(expanded, analysis, main, DOC)
    assert report.check(CheckName.CANDIDATE_FLAGS).status == CheckStatus.UNRESOLVED
    assert report.verdict == Verdict.FAIL
    assert report.reasons, "every failing or unresolved check must give a reason"


@pytest.mark.parametrize(
    "question",
    ["What is the limit for loans?", "Who approves the loan?", "Where is the loan limit applied?"],
)
def test_a_passage_only_type_never_passes(main, question):
    analysis, selection = selection_for(main, DOC, question)
    candidates = [candidate for component in selection.components for candidate in component.candidates]
    assert candidates, "the question must reach at least one passage for this test to mean anything"
    for candidate in candidates:
        report = verify(candidate, analysis, main, DOC)
        assert report.verdict != Verdict.PASS, candidate.quote
        assert report.check(CheckName.ANSWER_SPAN).status == CheckStatus.UNRESOLVED


def test_a_candidate_from_a_different_type_is_a_verification_error(main):
    _, selection = selection_for(main, DOC, LIMIT_Q)
    candidate = candidate_quoting(selection, LIMIT_FRAGMENT)
    other = analyze("What is the limit for loans?")
    with pytest.raises(VerificationError, match="but the candidate is"):
        verify(candidate, other, main, DOC)


def test_a_candidate_whose_component_is_not_in_the_analysis_is_a_verification_error(main):
    analysis, selection = selection_for(main, DOC, LIMIT_Q)
    candidate = replace(candidate_quoting(selection, LIMIT_FRAGMENT), component_id="c9")
    with pytest.raises(VerificationError, match="no single component c9"):
        verify(candidate, analysis, main, DOC)


def test_a_candidate_for_an_unsearchable_component_is_a_verification_error(main):
    analysis = analyze("Why is the limit 30 days?")
    component = analysis.components[0]
    assert not component.searchable
    _, selection = selection_for(main, DOC, LIMIT_Q)
    candidate = replace(
        candidate_quoting(selection, LIMIT_FRAGMENT),
        question_type=QuestionType.UNSUPPORTED,
    )
    with pytest.raises(VerificationError, match="not searchable"):
        verify(candidate, analysis, main, DOC)


def test_the_same_inputs_give_the_same_report(main):
    analysis, selection = selection_for(main, DOC, LIMIT_Q)
    candidate = candidate_quoting(selection, LIMIT_FRAGMENT)
    assert verify(candidate, analysis, main, DOC) == verify(candidate, analysis, main, DOC)

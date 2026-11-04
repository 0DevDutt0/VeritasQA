"""P6 end to end on labelled synthetic stored documents (ARCHITECTURE §15).

The documents are hand-built, so each expected quote and offset is known. The key case is the same sentence on a
verified page and on a flagged page: it passes only on the verified page (SPEC §7, D62).
"""

from __future__ import annotations

import pytest

from app.common.errors import StorageIntegrityError
from app.verification import CheckName, CheckStatus, Verdict, verify
from app.verification.vocabulary import ANSWER_TYPES
from tests.fixtures.retrieval_docs import Item
from tests.fixtures.verification_docs import (
    ISSUE_CODE,
    candidate_quoting,
    clean_items,
    main_items,
    selection_for,
    stored_document,
)

DOC = "doc-" + "a" * 16
LIMIT_Q = "How many days is the limit for loans?"
LIMIT_FRAGMENT = "The limit for loans is 30 days after approval."


@pytest.fixture(scope="module")
def verified_store():
    store = stored_document(DOC, main_items())
    yield store
    store.close()


@pytest.fixture(scope="module")
def flagged_store():
    store = stored_document(DOC, main_items(), flagged_pages=(1,))
    yield store
    store.close()


def _report(store, question: str, fragment: str):
    analysis, selection = selection_for(store, DOC, question)
    candidate = candidate_quoting(selection, fragment)
    return candidate, verify(candidate, analysis, store, DOC)


def test_the_same_sentence_passes_on_a_verified_page_and_is_unresolved_on_a_flagged_one(verified_store, flagged_store):
    candidate, clean = _report(verified_store, LIMIT_Q, LIMIT_FRAGMENT)
    flagged_candidate, flagged = _report(flagged_store, LIMIT_Q, LIMIT_FRAGMENT)
    assert candidate.quote == flagged_candidate.quote
    assert clean.verdict == Verdict.PASS
    assert clean.reasons == ()
    assert flagged.verdict == Verdict.UNRESOLVED
    assert flagged.check(CheckName.SOURCE_QUALITY).status == CheckStatus.UNRESOLVED
    assert ISSUE_CODE in flagged.check(CheckName.SOURCE_QUALITY).reason
    assert flagged.check(CheckName.CONTEXT).status == CheckStatus.UNRESOLVED


def test_the_store_reports_the_issue_codes_of_each_page(verified_store, flagged_store):
    assert verified_store.page_warning_codes(DOC, 1) == ()
    assert flagged_store.page_warning_codes(DOC, 1) == (ISSUE_CODE,)
    with pytest.raises(StorageIntegrityError):
        flagged_store.page_warning_codes(DOC, 99)


def test_a_permission_and_a_prohibition_pass_with_their_own_polarity():
    # The question's property word ("permitted") must be in the passage: a passage that says only "may" is UNRESOLVED,
    # because synonyms are not used (D58). That is why these sentences use "permitted".
    items = [
        Item(page=1, text="The board approves the loan for small businesses."),
        Item(page=1, text="Staff are permitted to share the guide with visitors."),
        Item(page=1, text="Staff must not share passwords with visitors."),
        Item(page=1, text="Each loan request is reviewed by the credit office."),
    ]
    store = stored_document(DOC, items)
    try:
        candidate, permission = _report(store, "Is staff permitted to share the guide with visitors?", "Staff are permitted")
        assert permission.verdict == Verdict.PASS
        assert candidate.negated is False
        candidate, prohibition = _report(store, "Must staff share passwords with visitors?", "Staff must not share")
        assert prohibition.verdict == Verdict.PASS
        assert candidate.negated is True
        assert prohibition.check(CheckName.NEGATION).status == CheckStatus.PASS
    finally:
        store.close()


def test_a_question_without_a_number_leaves_the_value_check_not_applicable(verified_store):
    _candidate, report = _report(verified_store, LIMIT_Q, LIMIT_FRAGMENT)
    assert report.check(CheckName.ANSWER_SPAN).status == CheckStatus.PASS
    assert report.check(CheckName.VALUE).status == CheckStatus.NOT_APPLICABLE
    assert report.check(CheckName.ATTRIBUTE).status == CheckStatus.PASS


def test_every_candidate_gets_a_complete_report_and_quotation_and_location_always_pass(verified_store):
    questions = [
        LIMIT_Q,
        "What is the limit for loans?",
        "Is staff permitted to share passwords with visitors?",
        "Is staff permitted to share the guide with visitors?",
        "What is the fee for loans?",
    ]
    seen = 0
    for question in questions:
        analysis, selection = selection_for(verified_store, DOC, question)
        for component in selection.components:
            for candidate in component.candidates:
                report = verify(candidate, analysis, verified_store, DOC)
                seen += 1
                assert len(report.checks) == 12
                assert report.check(CheckName.QUOTATION).status == CheckStatus.PASS
                assert report.check(CheckName.LOCATION).status == CheckStatus.PASS
                if component.question_type not in ANSWER_TYPES:
                    assert report.verdict != Verdict.PASS, question
    assert seen >= 8, "the questions must reach several candidates for this test to mean anything"

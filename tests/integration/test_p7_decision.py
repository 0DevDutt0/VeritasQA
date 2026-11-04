"""P7 end to end on labelled synthetic documents (SPEC §8-§10; ARCHITECTURE §16).

Each document is hand-built, so every expected status, quote and reason is known in advance. The cases cover every
SPEC §9 status, the compound rule (PARTIAL), the screen over the whole document, the policy switches, determinism, and
the isolation of two documents in one store.
"""

from __future__ import annotations

import pytest

from app.common.errors import StorageError
from app.decision import DecisionStatus, QAResponse, answer, load_policy
from app.decision.policy import AcceptancePolicy
from app.document_structure.models import ContentType
from app.question_processing.errors import QuestionError
from app.storage import Store
from tests.fixtures.retrieval_docs import Item, build, filler
from tests.fixtures.verification_docs import CREATED, ISSUE_CODE, clean_items, main_items, stored_document

DOC = "doc-" + "a" * 16
OTHER = "doc-" + "b" * 16
LIMIT = "How many days is the limit for loans?"
SENTENCE_30 = "The limit for loans is 30 days after approval."
SENTENCE_45 = "The limit for loans is 45 days after approval."


def _store(items: list[Item], *, flagged_pages: tuple[int, ...] = ()) -> Store:
    return stored_document(DOC, items, flagged_pages=flagged_pages)


def _run(store: Store, question: str, policy: AcceptancePolicy | None = None, document: str = DOC) -> QAResponse:
    return answer(store, document, question, policy if policy is not None else load_policy())


def _relaxed(**gates: bool) -> AcceptancePolicy:
    base = load_policy()
    return base.model_copy(update={"gates": dict(base.gates) | gates})


def _kinds(response: QAResponse) -> set[str]:
    return {finding.relation.value for finding in response.conflicts}


def test_a_supported_question_is_answered_with_its_verbatim_passage_and_span():
    store = _store(main_items())
    response = _run(store, LIMIT)
    assert response.status == DecisionStatus.ANSWERED
    assert [span.text for span in response.answer_spans] == ["30 days"]
    span = response.answer_spans[0]
    assert any(item.quote == SENTENCE_30 and "answer" in item.roles for item in response.evidence)
    assert span.evidence_id in {item.evidence_id for item in response.evidence}
    assert response.conflicts == (), "the 5 USD sentence is a different measure, so it is not compared"
    assert response.warnings == ()
    assert response.screening[0].screened is True
    assert response.screening[0].pieces_with_claims >= 2
    assert all(verdict.accepted for verdict in response.verification if verdict.verdict == "PASS")
    store.close()


def test_the_same_answer_comes_back_from_two_independent_runs_and_two_stores():
    first_store = _store(main_items())
    first = _run(first_store, LIMIT).model_dump(mode="json")
    again = _run(first_store, LIMIT).model_dump(mode="json")
    second_store = _store(main_items())
    second = _run(second_store, LIMIT).model_dump(mode="json")
    assert first == again == second
    first_store.close()
    second_store.close()


def test_a_response_survives_a_round_trip_through_its_own_model():
    store = _store(main_items())
    response = _run(store, LIMIT)
    assert QAResponse.model_validate(response.model_dump(mode="json")) == response
    store.close()


def test_the_same_sentence_on_a_flagged_page_is_source_unverified_and_gives_no_span():
    store = _store(main_items(), flagged_pages=(1,))
    response = _run(store, LIMIT)
    assert response.status == DecisionStatus.SOURCE_UNVERIFIED
    assert response.answer_spans == ()
    assert any("page 1 is warning" in warning and ISSUE_CODE in warning for warning in response.warnings)
    assert any(code.value == "source_quality" for code in response.reason_codes)
    assert any(item.quality_status.value == "warning" for item in response.evidence)
    store.close()


def test_two_different_values_for_the_same_subject_and_scope_are_a_confirmed_conflict():
    store = _store([Item(page=1, text=SENTENCE_30), Item(page=1, text=SENTENCE_45)])
    response = _run(store, LIMIT)
    assert response.status == DecisionStatus.CONFLICT
    assert response.answer_spans == ()
    assert "confirmed_incompatible" in _kinds(response)
    finding = next(item for item in response.conflicts if item.relation.value == "confirmed_incompatible")
    assert finding.impact.value == "conflict"
    assert {finding.first_claim, finding.second_claim} == {"30 days", "45 days"}
    assert finding.first_quote and finding.second_quote
    store.close()


def test_a_conflict_on_a_page_far_from_the_question_is_still_found():
    items = [Item(page=1, text=SENTENCE_30), *filler(12, page=2), Item(page=3, text=SENTENCE_45)]
    store = _store(items)
    response = _run(store, LIMIT)
    assert response.status == DecisionStatus.CONFLICT
    assert {finding.first_claim for finding in response.conflicts} | {finding.second_claim for finding in response.conflicts} >= {"30 days", "45 days"}
    store.close()


def test_numbers_for_different_scopes_are_not_called_a_conflict_but_still_do_not_answer():
    store = _store([Item(page=1, text="The limit for loans for staff is 45 days."), Item(page=1, text=SENTENCE_30)])
    response = _run(store, LIMIT)
    assert response.status == DecisionStatus.AMBIGUOUS_QUERY
    assert "different_scope" in _kinds(response)
    assert all(finding.impact.value != "conflict" for finding in response.conflicts)
    assert response.answer_spans == ()
    store.close()


def test_dated_values_that_differ_are_a_dated_change_and_the_answer_depends_on_the_date():
    store = _store(
        [
            Item(page=1, text="From 1 January 2026 the limit for loans is 45 days."),
            Item(page=1, text="From 1 January 2025 the limit for loans is 30 days."),
        ]
    )
    response = _run(store, LIMIT)
    assert response.status == DecisionStatus.AMBIGUOUS_QUERY
    assert "dated_change" in _kinds(response)
    assert "date_differs" in {code.value for code in response.reason_codes}
    store.close()


def test_a_stated_supersession_with_a_different_value_is_shown_as_a_conflict_and_is_not_applied():
    store = _store(
        [
            Item(page=1, text=SENTENCE_30),
            Item(page=1, text="The limit for loans is replaced by 45 days after approval."),
        ]
    )
    response = _run(store, LIMIT)
    assert response.status == DecisionStatus.CONFLICT
    assert "explicit_supersession" in _kinds(response)
    assert response.answer_spans == ()
    store.close()


def test_a_permission_and_a_prohibition_for_the_same_subject_are_a_conflict():
    store = _store(
        [
            Item(page=1, text="Staff are permitted to share the guide with visitors."),
            Item(page=1, text="Staff must not share the guide with visitors."),
        ]
    )
    response = _run(store, "Is staff permitted to share the guide with visitors?")
    assert response.status == DecisionStatus.CONFLICT
    assert "confirmed_incompatible" in _kinds(response)
    assert response.answer_spans == ()
    store.close()


def test_a_generated_table_row_that_disagrees_blocks_the_answer_but_cannot_be_called_a_confirmed_conflict():
    items = [
        Item(page=1, text=SENTENCE_30),
        Item(
            page=1,
            text="Loans limit | 45 days | after approval",
            content_type=ContentType.TABLE_ROW,
            derived=True,
            index="Table 1 | Loans limit | 45 days | after approval",
        ),
    ]
    store = _store(items)
    response = _run(store, LIMIT)
    assert response.status == DecisionStatus.AMBIGUOUS_QUERY
    assert "potential_discrepancy" in _kinds(response)
    assert "confirmed_incompatible" not in _kinds(response)
    assert response.answer_spans == ()
    store.close()


def test_a_passage_only_question_returns_its_passages_for_inspection_without_an_answer():
    store = _store(main_items())
    response = _run(store, "What is the fee for loans?")
    assert response.status == DecisionStatus.INSUFFICIENT_EVIDENCE
    assert response.answer_spans == ()
    assert "no_verified_answer" in {code.value for code in response.reason_codes}
    assert any(item.quote and "The fee for loans is 5 USD" in item.quote for item in response.evidence)
    assert all("passage" in item.roles or "conflicting" in item.roles for item in response.evidence)
    store.close()


def test_an_unsupported_question_is_ambiguous_with_its_reason():
    store = _store(main_items())
    response = _run(store, "Why is the limit for loans 30 days?")
    assert response.status == DecisionStatus.AMBIGUOUS_QUERY
    assert "unsupported_question" in {code.value for code in response.reason_codes}
    assert response.answer_spans == ()
    store.close()


def test_a_question_about_a_missing_subject_is_insufficient_with_no_candidates():
    store = _store(main_items())
    response = _run(store, "How many days is the limit for cars?")
    assert response.status == DecisionStatus.INSUFFICIENT_EVIDENCE
    assert "no_candidates" in {code.value for code in response.reason_codes}
    assert response.evidence == ()
    store.close()


def test_a_compound_question_reports_each_component_and_is_partial():
    store = _store(main_items())
    response = _run(store, "How many days is the limit for loans, and who approves loans?")
    assert response.status == DecisionStatus.PARTIAL
    assert [component.status for component in response.components] == [
        DecisionStatus.ANSWERED,
        DecisionStatus.INSUFFICIENT_EVIDENCE,
    ]
    assert [span.text for span in response.answer_spans] == ["30 days"]
    store.close()


def test_an_empty_question_is_an_error_and_an_unknown_document_is_an_error():
    store = _store(clean_items())
    with pytest.raises(QuestionError):
        _run(store, "   ")
    with pytest.raises(StorageError):
        _run(store, LIMIT, document="doc-" + "c" * 16)
    store.close()


def test_the_policy_switch_for_context_lets_only_the_context_outcome_through_on_a_verified_page():
    items = [Item(page=1, text=SENTENCE_30), Item(page=1, text="Exceptions apply unless the loan is renewed.")]
    store = _store(items)
    default = _run(store, LIMIT)
    assert default.status == DecisionStatus.INSUFFICIENT_EVIDENCE
    assert "verification_unresolved" in {code.value for code in default.reason_codes}
    relaxed = _run(store, LIMIT, _relaxed(require_context_validation=False))
    assert relaxed.status == DecisionStatus.ANSWERED
    assert "relaxed_gate_used" in {code.value for code in relaxed.reason_codes}
    assert any("require_context_validation" in warning for warning in relaxed.warnings)
    assert relaxed.policy.gates["require_context_validation"] is False
    store.close()


def test_relaxing_the_context_switch_does_not_let_a_flagged_page_through():
    items = [Item(page=1, text=SENTENCE_30), Item(page=1, text="Exceptions apply unless the loan is renewed.")]
    store = _store(items, flagged_pages=(1,))
    response = _run(store, LIMIT, _relaxed(require_context_validation=False))
    assert response.status == DecisionStatus.SOURCE_UNVERIFIED
    assert response.answer_spans == ()
    store.close()


def test_two_documents_in_one_store_do_not_see_each_other():
    store = Store.open(":memory:")
    for document_id, items in ((DOC, [Item(page=1, text=SENTENCE_30)]), (OTHER, [Item(page=1, text=SENTENCE_45)])):
        extracted, structure = build(document_id, items)
        store.write_document(extracted, structure, created_at=CREATED)
    first = _run(store, LIMIT, document=DOC)
    second = _run(store, LIMIT, document=OTHER)
    assert first.status == DecisionStatus.ANSWERED and first.conflicts == ()
    assert second.status == DecisionStatus.ANSWERED and second.conflicts == ()
    assert [span.text for span in first.answer_spans] == ["30 days"]
    assert [span.text for span in second.answer_spans] == ["45 days"]
    store.close()

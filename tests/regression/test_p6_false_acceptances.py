"""One case per false acceptance that verification must never make (ARCHITECTURE §15, SPEC §7 and §9).

Each case builds a tiny labelled synthetic document, so the false acceptance is isolated. Each case also has a
precondition: the same document with the defect removed must pass. Without that, a FAIL or UNRESOLVED result could
come from a broken setup rather than from the defect itself. Where it matters, the case also names the check that
must be the one to fail, so that a result cannot pass for the wrong reason.
"""

from __future__ import annotations

from dataclasses import replace

from app.document_structure.models import ContentType
from app.verification import CheckName, CheckStatus, Verdict, verify
from app.question_processing.analysis import analyze
from tests.fixtures.retrieval_docs import Item, filler
from tests.fixtures.verification_docs import candidate_quoting, main_items, selection_for, stored_document

DOC = "doc-" + "b" * 16


def _verdict(items, question: str, fragment: str, *, verify_question=None, flagged=(), forge=None):
    """Select with ``question`` and verify the candidate. ``verify_question`` checks it against another question."""
    store = stored_document(DOC, items, flagged_pages=flagged)
    try:
        analysis, selection = selection_for(store, DOC, question)
        candidate = candidate_quoting(selection, fragment)
        if forge is not None:
            candidate = forge(candidate)
        if verify_question is not None:
            analysis = analyze(verify_question)
        return verify(candidate, analysis, store, DOC)
    finally:
        store.close()


def _sentence(text: str, *, count: int = 3):
    return [Item(page=1, text=text), *filler(count, page=1)]


def test_a_prohibition_whose_not_is_dropped_from_its_stored_polarity_is_not_accepted():
    items = _sentence("Staff must not share passwords with visitors.")
    question = "Must staff share passwords with visitors?"
    assert _verdict(items, question, "Staff must not").verdict == Verdict.PASS
    report = _verdict(items, question, "Staff must not", forge=lambda c: replace(c, negated=False))
    assert report.verdict == Verdict.FAIL
    assert report.check(CheckName.NEGATION).status == CheckStatus.FAIL


def test_a_minus_sign_is_not_read_as_a_positive_value():
    question = "How many days is the limit of 3.5 for loans?"
    positive = _sentence("The limit of 3.5 for loans is 30 days after approval.")
    assert _verdict(positive, question, "The limit of 3.5").verdict == Verdict.PASS
    negative = _sentence("The limit of -3.5 for loans is 30 days after approval.")
    report = _verdict(negative, question, "The limit of")
    assert report.verdict == Verdict.FAIL
    assert report.check(CheckName.VALUE).status == CheckStatus.FAIL


def test_a_number_inside_a_longer_identifier_is_not_the_question_value():
    selected_by = "How many days is the limit for loans?"
    verified_against = "How many days is the limit of 3.5 for loans?"
    clean = _sentence("The limit of 3.5 for loans is 30 days.")
    assert _verdict(clean, selected_by, "The limit of 3.5", verify_question=verified_against).verdict == Verdict.PASS
    longer = _sentence("The code 3.5.2 sets the limit for loans to 30 days.")
    report = _verdict(longer, selected_by, "The code 3.5.2", verify_question=verified_against)
    assert report.verdict != Verdict.PASS
    assert report.check(CheckName.VALUE).status == CheckStatus.UNRESOLVED or (
        report.check(CheckName.ENTITY).status == CheckStatus.FAIL
    )


def test_a_number_inside_a_longer_number_is_not_the_question_value():
    selected_by = "How many days is the limit for loans?"
    verified_against = "How many days is the limit of 5 for loans?"
    clean = _sentence("The limit of 5 for loans is 30 days.")
    assert _verdict(clean, selected_by, "The limit of 5", verify_question=verified_against).verdict == Verdict.PASS
    longer = _sentence("The limit of 15 for loans is 30 days.")
    report = _verdict(longer, selected_by, "The limit of 15", verify_question=verified_against)
    assert report.verdict != Verdict.PASS
    assert report.check(CheckName.VALUE).status == CheckStatus.UNRESOLVED or (
        report.check(CheckName.ENTITY).status == CheckStatus.FAIL
    )


def test_a_candidate_reached_only_by_a_reviewed_rule_is_never_support():
    items = _sentence("The limit for loans is 30 days after approval.")
    question = "How many days is the limit for loans?"
    assert _verdict(items, question, "The limit for loans").verdict == Verdict.PASS
    expanded = _verdict(
        items,
        question,
        "The limit for loans",
        forge=lambda c: replace(c, retrieval=replace(c.retrieval, via="expansion")),
    )
    assert expanded.verdict == Verdict.FAIL
    assert expanded.check(CheckName.ENTITY).status == CheckStatus.FAIL


def test_a_neighbour_that_qualifies_the_passage_blocks_it():
    question = "Is staff permitted to share the guide with visitors?"
    clean = _sentence("Staff are permitted to share the guide with visitors.")
    assert _verdict(clean, question, "Staff are permitted").verdict == Verdict.PASS
    qualified = [
        Item(page=1, text="Staff are permitted to share the guide with visitors."),
        Item(page=1, text="The guide is restricted. It applies unless the staff member is suspended."),
        *filler(2, page=1),
    ]
    report = _verdict(qualified, question, "Staff are permitted")
    assert report.verdict != Verdict.PASS
    assert report.check(CheckName.CONTEXT).status == CheckStatus.UNRESOLVED
    assert "unless" in report.check(CheckName.CONTEXT).reason


def test_a_table_cell_is_never_accepted_as_an_answer():
    items = [Item(page=1, text="Loans limit: 30 days", content_type=ContentType.TABLE_CELL), *filler(2, page=1)]
    report = _verdict(items, "How many days is the limit for loans?", "Loans limit")
    assert report.verdict == Verdict.UNRESOLVED
    assert report.check(CheckName.CANDIDATE_FLAGS).status == CheckStatus.UNRESOLVED
    assert report.check(CheckName.ANSWER_SPAN).status == CheckStatus.UNRESOLVED


def test_a_derived_table_row_is_never_quoted():
    items = [
        Item(page=1, text="The limit for loans is 30 days after approval."),
        Item(
            page=1,
            text="Low | 1 | Rare",
            content_type=ContentType.TABLE_ROW,
            derived=True,
            index="Table 1 | Low | Rating = 1 ; Meaning = Rare",
        ),
    ]
    store = stored_document(DOC, items)
    try:
        analysis, selection = selection_for(store, DOC, "How many days is the limit for loans?")
        candidate = candidate_quoting(selection, "The limit for loans")
        row = next(unit for unit in store.load_structure(DOC).units if unit.derived)
        text = store.page_texts(DOC, [row.pdf_page])[row.pdf_page]
        start, end = row.source_spans[0]
        as_row = replace(
            candidate,
            retrieval=replace(
                candidate.retrieval,
                evidence_id=row.evidence_id,
                ordinal=row.ordinal,
                derived=True,
                extraction_quality=row.extraction_quality.value,
            ),
            section_id=row.section_id,
            quote=text[start:end],
            page_start=start,
            page_end=end,
            answer_span=None,
            answer_page_start=None,
            answer_page_end=None,
            answer_kind=None,
        )
        report = verify(as_row, analysis, store, DOC)
        assert report.verdict == Verdict.FAIL
        assert report.check(CheckName.LOCATION).status == CheckStatus.FAIL
    finally:
        store.close()


def test_a_replacement_character_in_the_passage_is_never_accepted():
    question = "How many days is the limit for loans?"
    clean = _sentence("The limit for loans is 30 days after approval.")
    assert _verdict(clean, question, "The limit for loans").verdict == Verdict.PASS
    damaged = _sentence("The limit for loans is 30 days after approval�.")
    report = _verdict(damaged, question, "The limit for loans")
    assert report.verdict == Verdict.UNRESOLVED
    assert "replacement character" in report.check(CheckName.CANDIDATE_FLAGS).reason


def test_two_values_in_one_passage_never_give_a_single_answer():
    items = _sentence("The fee for loans is 5 USD and the limit is 30 days.")
    report = _verdict(items, "How many days is the limit for loans?", "The fee for loans is 5 USD")
    assert report.verdict == Verdict.UNRESOLVED
    assert report.check(CheckName.ANSWER_SPAN).status == CheckStatus.UNRESOLVED


def test_a_passage_only_type_never_passes_even_with_a_span_added():
    items = _sentence("The limit for loans is 30 days after approval.")
    question = "What is the limit for loans?"
    assert _verdict(items, question, "The limit for loans").verdict == Verdict.UNRESOLVED
    forged = _verdict(
        items,
        question,
        "The limit for loans",
        forge=lambda c: replace(c, answer_span="30 days", answer_page_start=c.page_start, answer_page_end=c.page_start + 2),
    )
    assert forged.verdict == Verdict.FAIL
    assert forged.check(CheckName.ANSWER_SPAN).status == CheckStatus.FAIL


def test_a_quote_that_no_longer_matches_the_stored_page_fails():
    items = _sentence("The limit for loans is 30 days after approval.")
    report = _verdict(
        items,
        "How many days is the limit for loans?",
        "The limit for loans",
        forge=lambda c: replace(c, quote=c.quote.replace("30", "60")),
    )
    assert report.verdict == Verdict.FAIL
    assert report.check(CheckName.QUOTATION).status == CheckStatus.FAIL


def test_a_flagged_page_never_passes():
    items = _sentence("The limit for loans is 30 days after approval.")
    question = "How many days is the limit for loans?"
    assert _verdict(items, question, "The limit for loans").verdict == Verdict.PASS
    report = _verdict(items, question, "The limit for loans", flagged=(1,))
    assert report.verdict == Verdict.UNRESOLVED
    assert report.check(CheckName.SOURCE_QUALITY).status == CheckStatus.UNRESOLVED


def test_a_hedged_permission_is_not_accepted():
    question = "Is staff permitted to share the guide with visitors?"
    assert _verdict(_sentence("Staff are permitted to share the guide with visitors."), question, "Staff are permitted").verdict == Verdict.PASS
    hedged = _sentence("Staff are permitted to share the guide with visitors, but it possibly applies.")
    report = _verdict(hedged, question, "Staff are permitted")
    assert report.verdict != Verdict.PASS
    assert report.check(CheckName.NEGATION).status == CheckStatus.UNRESOLVED
    assert "possibly" in report.check(CheckName.NEGATION).reason


def test_a_conditional_permission_is_not_accepted():
    question = "Is staff permitted to share the guide with visitors?"
    assert _verdict(_sentence("Staff are permitted to share the guide with visitors."), question, "Staff are permitted").verdict == Verdict.PASS
    conditional = _sentence("Staff are permitted to share the guide with visitors if they are trained.")
    report = _verdict(conditional, question, "Staff are permitted")
    assert report.verdict == Verdict.UNRESOLVED
    assert report.check(CheckName.CONDITION).status == CheckStatus.UNRESOLVED
    assert "if" in report.check(CheckName.CONDITION).reason


def test_a_negated_question_is_not_matched_to_a_passage_polarity():
    items = _sentence("Staff must not share passwords with visitors.")
    assert _verdict(items, "Must staff share passwords with visitors?", "Staff must not").verdict == Verdict.PASS
    report = _verdict(items, "Must staff not share passwords with visitors?", "Staff must not")
    assert report.verdict != Verdict.PASS
    assert report.check(CheckName.NEGATION).status == CheckStatus.UNRESOLVED
    assert "negated" in report.check(CheckName.NEGATION).reason

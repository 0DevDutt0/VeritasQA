"""P13 word forms of a question word (ARCHITECTURE §14, D131; the owner's option 3 of D129).

A target word also matches its inflected forms in the original retrieval match, in the sentence check of the selection,
in the entity check and in the conflict screen. The rule is a fixed suffix rule (``app/retrieval/forms.py``), not a
stemmer. These tests pin the generated forms, the collisions that are excluded, the boundary rule of the exact check,
and the rule that a quotation is still compared verbatim.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.conflict.detector import scope_words
from app.retrieval import all_forms, find_word, search, span_matches_word, word_forms
from app.storage import Store
from app.verification import CheckName, CheckStatus, verify
from tests.fixtures.retrieval_docs import Item, build, filler
from tests.fixtures.verification_docs import candidate_quoting, selection_for, stored_document

DOC = "doc-" + "d" * 16
DOC_VERIFY = "doc-" + "f" * 16
CREATED = "2026-01-01T00:00:00Z"


@pytest.fixture(scope="module")
def store_and_structure():
    items = filler(20, page=1)
    items += [
        Item(page=1, text="Fees are received within 5 days."),
        Item(page=1, text="The unreceived fees are listed for the public."),
        Item(page=1, text="The receiver is named in the notice."),
    ]
    items += filler(20, page=1)
    extracted, structure = build(DOC, items)
    store = Store.open(":memory:")
    store.write_document(extracted, structure, created_at=CREATED)
    yield store, structure
    store.close()


def _found(store, result) -> dict:
    """The candidates of a search, keyed by the raw text of their unit."""
    ids = [candidate.evidence_id for candidate in result.candidates]
    summaries = store.unit_summaries(DOC, ids)
    return {summaries[candidate.evidence_id].raw_text: candidate for candidate in result.candidates}


# A. The forms that the suffix rule generates.


@pytest.mark.parametrize(
    "word, expected",
    [
        ("receive", {"received", "receives", "receiving"}),
        ("apply", {"applied", "applies", "applying"}),
        ("stop", {"stopped", "stopping", "stops"}),
        ("access", {"accessed", "accesses", "accessing"}),
        ("carry", {"carried", "carries", "carrying"}),
        ("play", {"played", "plays", "playing"}),
        ("die", {"died", "dies", "dying"}),
        ("agree", {"agreed", "agrees", "agreeing"}),
        ("box", {"boxed", "boxes", "boxing"}),
        ("watch", {"watched", "watches", "watching"}),
    ],
)
def test_a_word_has_its_plural_past_and_ing_forms(word, expected):
    forms = word_forms(word)
    assert forms[0] == word, "the word itself comes first"
    assert expected <= set(forms)


@pytest.mark.parametrize(
    "inflected, base",
    [("received", "receive"), ("applies", "apply"), ("stopping", "stop"), ("carried", "carry"), ("fees", "fee")],
)
def test_an_inflected_question_word_also_has_its_base_form_and_back(inflected, base):
    assert base in word_forms(inflected)
    assert inflected in word_forms(base)


@pytest.mark.parametrize("word", ["3.5", "ABC-123", "2024", "us", "go", "café"])
def test_numbers_identifiers_short_words_and_non_ascii_words_have_no_forms(word):
    assert word_forms(word) == (word,)


def test_all_forms_has_no_repeats_and_keeps_the_order_of_the_words():
    forms = all_forms(("fee", "fees"))
    assert len(forms) == len(set(forms))
    assert forms[0] == "fee"
    assert "fees" in forms


# B. Collisions that the rule must not create.


def test_use_does_not_produce_us():
    assert "us" not in word_forms("use")
    assert {"used", "uses", "using"} <= set(word_forms("use"))


def test_new_and_news_are_not_forms_of_each_other():
    assert "news" not in word_forms("new")
    assert "new" not in word_forms("news")


def test_fee_and_feed_are_not_forms_of_each_other_but_their_plurals_are():
    assert "feed" not in word_forms("fee")
    assert "fee" not in word_forms("feed")
    assert "fees" in word_forms("fee")
    assert "feeds" in word_forms("feed")
    assert "feed" in word_forms("feeds"), "the plural of feed still reaches feed"


@pytest.mark.parametrize("word, stem", [("class", "clas"), ("access", "acces"), ("pass", "pas")])
def test_a_word_ending_in_ss_takes_no_stem(word, stem):
    assert stem not in word_forms(word)


# C. The exact check applies to each form (token boundaries are inherited, D33).


@pytest.mark.parametrize(
    "span, word, expected",
    [
        ("Fees are received within 5 days.", "receive", True),
        ("Each request receives a reply.", "receive", True),
        ("Requests are receiving support.", "receive", True),
        ("The request was not received.", "receive", True),
        ("The unreceived fees are listed.", "receive", False),
        ("The receiver is named.", "receive", False),
        ("The news is out.", "new", False),
        ("We give us the form.", "use", False),
        ("The feed is due.", "fee", False),
        ("The fees are due.", "fee", True),
        ("Each class meets.", "class", True),
        ("The clas word.", "class", False),
        ("Access is granted.", "access", True),
    ],
)
def test_the_exact_check_applies_to_each_form(span, word, expected):
    assert span_matches_word(span, word) is expected


# D. Retrieval: a form is an original hit, never an expansion (D38).


def test_retrieval_reaches_a_form_as_an_original_hit(store_and_structure):
    store, _ = store_and_structure
    found = _found(store, search(store, DOC, "receive", context_window=0))
    assert found["Fees are received within 5 days."].via == "original"
    assert not found["Fees are received within 5 days."].expansion_only
    assert found["Fees are received within 5 days."].rule_ids == ()
    assert "The receiver is named in the notice." not in found
    assert "The unreceived fees are listed for the public." not in found


def test_find_word_returns_the_units_with_a_form(store_and_structure):
    store, _ = store_and_structure
    texts = [unit.raw_text for unit in find_word(store, DOC, "receive")]
    assert "Fees are received within 5 days." in texts
    assert "The receiver is named in the notice." not in texts


# E. Selection and the entity check accept a form of a target word; the quotation stays verbatim.


def test_the_selection_and_the_entity_check_accept_a_form_of_a_target_word():
    items = [Item(page=1, text="The agency is paid when payment is received by 4 March 2024.")] + filler(3, page=1)
    store = stored_document(DOC_VERIFY, items)
    try:
        analysis, selection = selection_for(store, DOC_VERIFY, "When must the agency receive payment?")
        candidate = candidate_quoting(selection, "payment is received")
        report = verify(candidate, analysis, store, DOC_VERIFY)
        assert report.check(CheckName.ENTITY).status == CheckStatus.PASS
    finally:
        store.close()


def test_the_entity_check_still_fails_when_no_form_of_a_target_word_is_in_the_quote():
    items = [Item(page=1, text="The agency is paid when payment is received by 4 March 2024.")] + filler(3, page=1)
    store = stored_document(DOC_VERIFY, items)
    try:
        analysis, selection = selection_for(store, DOC_VERIFY, "When must the agency receive payment?")
        candidate = candidate_quoting(selection, "payment is received")
        forged = replace(candidate, quote="The agency is paid when payment is reviewed by 4 March 2024.")
        report = verify(forged, analysis, store, DOC_VERIFY)
        assert report.check(CheckName.ENTITY).status == CheckStatus.FAIL
    finally:
        store.close()


def test_the_quotation_check_still_compares_the_verbatim_text():
    items = [Item(page=1, text="The agency is paid when payment is received by 4 March 2024.")] + filler(3, page=1)
    store = stored_document(DOC_VERIFY, items)
    try:
        analysis, selection = selection_for(store, DOC_VERIFY, "When must the agency receive payment?")
        candidate = candidate_quoting(selection, "payment is received")
        assert verify(candidate, analysis, store, DOC_VERIFY).check(CheckName.QUOTATION).status == CheckStatus.PASS
        # A form that is not on the page is still a changed quotation.
        forged = replace(candidate, quote=candidate.quote.replace("received", "receives"))
        report = verify(forged, analysis, store, DOC_VERIFY)
        assert report.check(CheckName.QUOTATION).status == CheckStatus.FAIL
    finally:
        store.close()


# F. The conflict screen treats a form of a target word as part of the subject, not as a qualifier (D70).


def test_a_form_of_a_target_word_is_not_a_qualifying_word_in_the_conflict_scope():
    words = scope_words("Payment is received by 4 March 2024.", ("payment", "receive"), (), ())
    assert "received" not in words

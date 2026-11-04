"""P4 regression set for synonym and stemming rules: known ways a rule could add a false candidate.

A rule adds candidates only, and no check may accept an expansion-only candidate as support (D38). These cases
guard the recall path: a rule must not reach a word that merely contains a listed word, or a word whose form is
not listed. The rules are the synthetic fixture ``tests/fixtures/retrieval_rules_test.toml``. Each case has a
name, so that a future false match can be added beside it (SPEC §12).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.retrieval import search
from app.retrieval.rules import load_rules
from app.storage import Store
from tests.fixtures.retrieval_docs import Item, build, filler

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "retrieval_rules_test.toml"
DOC = "doc-" + "9" * 16
CREATED = "2026-01-01T00:00:00Z"

DISCHARGE = "The discharge applies to each visit."  # contains "charge", as the end of a longer word
FEES = "The fees are listed for the public."  # a plural that the rule does not list
REREAD = "The rerun is scheduled for the day."  # contains "run" as the end of a longer word
SURCHARGE = "A surcharge is never listed as an alternative."
CONFUSABLES = frozenset({DISCHARGE, FEES, REREAD, SURCHARGE})


@pytest.fixture(scope="module")
def store():
    items = filler(20, page=1)
    items += [Item(page=1, text=text) for text in (DISCHARGE, FEES, REREAD, SURCHARGE)]
    items += [Item(page=1, text="The fee is due at the visit."), Item(page=1, text="The team is running the test.")]
    items += filler(20, page=1)
    extracted, structure = build(DOC, items)
    handle = Store.open(":memory:")
    handle.write_document(extracted, structure, created_at=CREATED)
    yield handle
    handle.close()


@pytest.fixture(scope="module")
def rules():
    return load_rules(FIXTURE)


def _reached_texts(store, result) -> set[str]:
    ids = [candidate.evidence_id for candidate in result.candidates]
    summaries = store.unit_summaries(DOC, ids)
    return {summaries[evidence_id].raw_text for evidence_id in ids}


@pytest.mark.parametrize("query", ["fee", "run", "charge", "risk assessment"])
def test_no_confusable_text_is_reached_for_a_rule_query(store, rules, query):
    result = search(store, DOC, query, rules=rules, context_window=0)
    assert _reached_texts(store, result) & CONFUSABLES == set(), query


def test_a_word_that_ends_in_a_listed_alternative_is_not_reached(store, rules):
    result = search(store, DOC, "fee", rules=rules, context_window=0)
    assert DISCHARGE not in _reached_texts(store, result)


def test_an_unlisted_plural_is_not_reached(store, rules):
    result = search(store, DOC, "fee", rules=rules, context_window=0)
    assert FEES not in _reached_texts(store, result)


def test_a_listed_stemming_form_is_reached_and_its_longer_neighbour_is_not(store, rules):
    result = search(store, DOC, "run", rules=rules, context_window=0)
    reached = _reached_texts(store, result)
    assert "The team is running the test." in reached, "the listed form itself is reached"
    assert REREAD not in reached


def test_a_compound_is_not_reached_through_its_part(store, rules):
    result = search(store, DOC, "charge", rules=rules, context_window=0)
    assert result.trace.applied_rules == (), "one-way: an alternative never adds the query term"
    assert SURCHARGE not in _reached_texts(store, result)

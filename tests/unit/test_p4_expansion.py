"""P4 expansion: reviewed rules add candidates only, are logged with their IDs and never take an original slot (D38, D41).

The rules are the synthetic fixture ``tests/fixtures/retrieval_rules_test.toml``. The shipped file has no rule (D43).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.retrieval import search
from app.retrieval.rules import AppliedRule, RuleSet, load_rules
from app.storage import Store
from tests.fixtures.retrieval_docs import Item, build, filler

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "retrieval_rules_test.toml"
DOC = "doc-" + "e" * 16
CREATED = "2026-01-01T00:00:00Z"


@pytest.fixture(scope="module")
def rules():
    return load_rules(FIXTURE)


@pytest.fixture(scope="module")
def store_and_structure():
    items = filler(20, page=1)
    items += [
        Item(page=1, text="The fee is due at the visit."),
        Item(page=1, text="The charge applies to each visit."),
        Item(page=1, text="The fees are listed for the public."),
        Item(page=1, text="The discharge applies to each visit."),
        Item(page=1, text="The team is running the test."),
        Item(page=1, text="The rerun is scheduled for the day."),
        Item(page=1, text="The hazard review is complete."),
        Item(page=1, text="The risk assessment is attached."),
    ]
    items += filler(20, page=1)
    extracted, structure = build(DOC, items)
    store = Store.open(":memory:")
    store.write_document(extracted, structure, created_at=CREATED)
    yield store, structure
    store.close()


def _id(structure, fragment: str) -> str:
    matches = [unit.evidence_id for unit in structure.units if fragment in unit.raw_text]
    assert len(matches) == 1, fragment
    return matches[0]


def test_an_alternative_hit_is_an_expansion_only_candidate_with_its_rule_id(store_and_structure, rules):
    store, structure = store_and_structure
    result = search(store, DOC, "fee", rules=rules, context_window=0)
    original = _id(structure, "The fee is due")
    expansion = _id(structure, "The charge applies")
    by_id = {candidate.evidence_id: candidate for candidate in result.candidates}
    assert by_id[original].via == "original" and not by_id[original].expansion_only
    assert by_id[original].rule_ids == ()
    assert by_id[expansion].via == "expansion" and by_id[expansion].expansion_only
    assert by_id[expansion].rule_ids == ("test-fee-charge",)
    assert by_id[original].rank < by_id[expansion].rank, "original hits come before expansion-only hits"
    fees = _id(structure, "The fees are listed")
    discharge = _id(structure, "The discharge applies")
    assert by_id[fees].via == "original" and not by_id[fees].expansion_only, "a plural is an original hit (P13)"
    assert discharge not in by_id


def test_each_applied_alternative_is_logged_with_its_rule_and_version(store_and_structure, rules):
    store, _ = store_and_structure
    result = search(store, DOC, "fee", rules=rules, context_window=0)
    assert result.trace.applied_rules == (
        AppliedRule(query_term="fee", rule_id="test-fee-charge", rule_version=1, alternative="charge"),
        AppliedRule(query_term="fee", rule_id="test-fee-charge", rule_version=1, alternative="charges"),
    )
    assert result.trace.rules_fingerprint == rules.fingerprint


def test_an_expansion_never_takes_an_original_slot(store_and_structure, rules):
    store, structure = store_and_structure
    original = _id(structure, "The fee is due")
    expansion = _id(structure, "The charge applies")
    with_room = search(store, DOC, "fee", k=1, expansion_k=10, rules=rules, context_window=0)
    assert [candidate.evidence_id for candidate in with_room.candidates] == [original, expansion]
    without_room = search(store, DOC, "fee", k=1, expansion_k=0, rules=rules, context_window=0)
    assert [candidate.evidence_id for candidate in without_room.candidates] == [original]
    assert without_room.trace.expansion_hits == 1
    assert without_room.trace.truncated_expansion == 1


def test_an_expansion_limit_of_zero_returns_no_expansion_but_still_logs_the_rule(store_and_structure, rules):
    store, _ = store_and_structure
    result = search(store, DOC, "fee", expansion_k=0, rules=rules, context_window=0)
    assert all(not candidate.expansion_only for candidate in result.candidates)
    assert len(result.trace.applied_rules) == 2


def test_a_unit_that_an_original_word_reaches_is_never_expansion_only(store_and_structure, rules):
    store, structure = store_and_structure
    charge = _id(structure, "The charge applies")
    result = search(store, DOC, "fee charge", rules=rules, context_window=0)
    by_id = {candidate.evidence_id: candidate for candidate in result.candidates}
    assert by_id[charge].via == "original"
    assert result.trace.expansion_hits == 0, "the alternative 'charge' is already a query word, so it adds nothing"


def test_the_rule_is_one_way(store_and_structure, rules):
    store, structure = store_and_structure
    result = search(store, DOC, "charge", rules=rules, context_window=0)
    assert result.trace.applied_rules == ()
    assert _id(structure, "The fee is due") not in {candidate.evidence_id for candidate in result.candidates}


def test_a_multi_word_term_needs_its_words_to_be_adjacent(store_and_structure, rules):
    store, structure = store_and_structure
    hazard = _id(structure, "The hazard review")
    adjacent = search(store, DOC, "risk assessment", rules=rules, context_window=0)
    found = {candidate.evidence_id: candidate for candidate in adjacent.candidates}
    assert found[hazard].expansion_only and found[hazard].rule_ids == ("test-risk-review",)
    apart = search(store, DOC, "risk alone assessment", rules=rules, context_window=0)
    assert apart.trace.applied_rules == ()
    assert hazard not in {candidate.evidence_id for candidate in apart.candidates}


def test_a_word_form_is_an_original_hit_and_a_similar_word_is_not(store_and_structure, rules):
    # P13 (D131): "running" is a form of "run", so it is an original hit and the listed stemming rule adds nothing for
    # it. The expansion-only path is tested above with "fee" and "charge", which no word form produces.
    store, structure = store_and_structure
    result = search(store, DOC, "run", rules=rules, context_window=0)
    running = _id(structure, "The team is running")
    found = {candidate.evidence_id: candidate for candidate in result.candidates}
    assert found[running].via == "original" and not found[running].expansion_only
    assert _id(structure, "The rerun is scheduled") not in found


def test_without_rules_nothing_is_expanded(store_and_structure):
    store, structure = store_and_structure
    result = search(store, DOC, "fee", rules=RuleSet(), context_window=0)
    assert result.trace.applied_rules == ()
    assert all(not candidate.expansion_only for candidate in result.candidates)


def test_the_shipped_rules_add_nothing_to_a_query(store_and_structure):
    store, _ = store_and_structure
    result = search(store, DOC, "fee", context_window=0)
    assert result.trace.applied_rules == ()
    assert all(not candidate.expansion_only for candidate in result.candidates)

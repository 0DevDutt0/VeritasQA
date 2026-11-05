"""P9a baselines: the RRF and duplicate rules are exact, the BM25 arm is the engine's order, and scikit-learn is needed
only by the TF-IDF arm (ARCHITECTURE §18.5, §18.6, D94 to D96). Tests that need scikit-learn skip when it is missing."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.benchmark import BASELINE_DEPTH, RRF_CONSTANT, BenchmarkError
from app.benchmark.baselines import (
    ComponentQuery,
    bm25_ranking,
    body_units,
    component_queries,
    dedupe,
    measure_baselines,
    rrf_ranking,
    text_key,
    tfidf_model,
    tfidf_ranking,
)
from app.evaluation import load_gold, select_split
from app.retrieval.config import load_retrieval_config
from tests.fixtures.p9_sweep_docs import DOC, GOLD_QUOTE, HEADING_UNIT_TEXT, sweep_items
from tests.fixtures.verification_docs import stored_document

GOLD = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "p9_synthetic_gold.jsonl"


@pytest.fixture
def store():
    stored = stored_document(DOC, sweep_items())
    yield stored
    stored.close()


def _unit_id(store, raw_text: str) -> str:
    matches = [unit.evidence_id for unit in body_units(store, DOC) if unit.raw_text == raw_text]
    assert len(matches) == 1
    return matches[0]


def test_rrf_uses_the_fixed_constant_of_the_original_method():
    assert RRF_CONSTANT == 60
    assert BASELINE_DEPTH == 50


def test_rrf_scores_are_the_sum_of_reciprocal_ranks():
    # "b" is second in the first list and first in the second: 1/62 + 1/61. "a" is first in one list only: 1/61.
    assert rrf_ranking(["a", "b"], ["b"]) == ["b", "a"]


def test_rrf_breaks_a_tie_by_evidence_id():
    assert rrf_ranking(["a"], ["b"]) == ["a", "b"]


def test_rrf_of_one_list_keeps_its_order():
    assert rrf_ranking(["c", "a", "b"]) == ["c", "a", "b"]


def test_dedupe_keeps_the_first_of_each_duplicate_group_and_stops_at_the_depth():
    raw = {"x": "Same  text.", "y": "Same text.", "z": "Other text."}
    assert dedupe(["x", "y", "z"], raw, depth=10) == ["x", "z"]
    assert dedupe(["x", "y", "z"], raw, depth=1) == ["x"]


def test_the_duplicate_key_ignores_whitespace_but_keeps_case():
    assert text_key("A  b") == text_key("A b")
    assert text_key("A b") != text_key("a b")


def test_the_bm25_arm_is_the_engine_order_for_the_query(store):
    # The configured heading weight is 2.0, so the heading unit ranks first (D97).
    assert bm25_ranking(store, DOC, "quarterly", load_retrieval_config()) == [
        _unit_id(store, HEADING_UNIT_TEXT),
        _unit_id(store, GOLD_QUOTE),
    ]


def test_the_component_queries_are_the_searchable_components_with_gold(store):
    dev = select_split(load_gold(GOLD), "dev", final_run=False)
    assert component_queries(dev) == (
        ComponentQuery(index=1, query="quarterly", gold_quotes=(GOLD_QUOTE,), gold_pages=(1,)),
    )


def test_tfidf_ranks_only_the_gold_passage_for_quarterly(store):
    pytest.importorskip("sklearn")
    model = tfidf_model(body_units(store, DOC))
    assert tfidf_ranking(model, "quarterly") == [_unit_id(store, GOLD_QUOTE)]


def test_tfidf_ignores_case_and_returns_nothing_without_a_matching_word(store):
    pytest.importorskip("sklearn")
    model = tfidf_model(body_units(store, DOC))
    assert tfidf_ranking(model, "QUARTERLY") == tfidf_ranking(model, "quarterly")
    assert tfidf_ranking(model, "interest rate mortgages") == []


def test_tfidf_is_deterministic_and_fits_only_body_units(store):
    pytest.importorskip("sklearn")
    units = body_units(store, DOC)
    first = tfidf_model(units)
    second = tfidf_model(units)
    assert tfidf_ranking(first, "quarterly") == tfidf_ranking(second, "quarterly")
    running_header = [unit.evidence_id for unit in store.load_structure(DOC).units if not unit.body_retrieval]
    assert running_header and not set(running_header) & set(first.evidence_ids)


def test_the_tfidf_arm_refuses_to_run_without_scikit_learn(store, monkeypatch):
    monkeypatch.setitem(sys.modules, "sklearn", None)
    monkeypatch.setitem(sys.modules, "sklearn.feature_extraction", None)
    monkeypatch.setitem(sys.modules, "sklearn.feature_extraction.text", None)
    with pytest.raises(BenchmarkError, match="scikit-learn"):
        tfidf_model(body_units(store, DOC))
    dev = select_split(load_gold(GOLD), "dev", final_run=False)
    with pytest.raises(BenchmarkError, match="scikit-learn"):
        measure_baselines(store, DOC, dev, base=load_retrieval_config())


def test_the_baseline_arms_match_the_hand_computed_values(store):
    pytest.importorskip("sklearn")
    dev = select_split(load_gold(GOLD), "dev", final_run=False)
    result = measure_baselines(store, DOC, dev, base=load_retrieval_config())
    arms = result["arms"]
    assert result["components"] == 1
    # BM25 puts the heading unit first, so the gold passage is second.
    assert arms["bm25"]["recall_at_1"] == {"n": 1, "value": 0.0}
    assert arms["bm25"]["mrr"] == {"n": 1, "value": 0.5}
    # TF-IDF sees only the index text, where only the gold passage contains the word.
    assert arms["tfidf"]["recall_at_1"] == {"n": 1, "value": 1.0}
    assert arms["tfidf"]["mrr"] == {"n": 1, "value": 1.0}
    # Fusion puts the gold passage first: 1/61 + 1/62 beats the heading unit's 1/61.
    assert arms["rrf"]["recall_at_1"] == {"n": 1, "value": 1.0}
    assert arms["rrf"]["mrr"] == {"n": 1, "value": 1.0}
    # Every arm is measured to depth 50, so every depth is defined.
    assert arms["rrf"]["recall_at_50"] == {"n": 1, "value": 1.0}

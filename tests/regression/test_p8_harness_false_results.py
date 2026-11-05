"""Regression cases for false results the harness could have produced (SPEC §12; ARCHITECTURE §17).

Each case names a mistake that a review found in the harness design, and asserts the behaviour the contract requires.
A future false result gets its own case here.
"""

import json

import pytest

from app.evaluation import EvaluationError, GoldError, load_gold, run_evaluation
from app.evaluation import runner as runner_module
from app.evaluation.gold import GoldRecord
from app.evaluation.metrics import rate
from app.evaluation.scoring import (
    ObservedComponent,
    ObservedEvidence,
    ObservedResponse,
    ObservedRetrieval,
    build_metrics,
    score_record,
)
from app.evaluation.gold import check_against_store
from pathlib import Path
from tests.fixtures.verification_docs import main_items, stored_document

GOLD = Path(__file__).resolve().parents[1] / "fixtures" / "p8_synthetic_gold.jsonl"
DOC = "doc-" + "8" * 16
B = "The limit for loans is 30 days after approval."
S = "Staff may share the guide with visitors."
PAGE = f"{B} {S}"


def gold(status, evidence, answers=()):
    return GoldRecord.model_validate(
        {
            "record_id": "r1",
            "question": "How many days is the limit for loans?",
            "category": "direct_fact",
            "source": "synthetic",
            "split": "dev",
            "annotator": "test",
            "expected_status": status,
            "evidence": list(evidence),
            "answers": list(answers),
        }
    )


def test_an_empty_denominator_is_none_and_never_a_zero_rate():
    # Only answerable records were run, so there is no unanswerable record. A zero would read as a 0% false
    # acceptance rate, which is a claim the run never measured.
    answerable = gold("ANSWERED", [{"component": 1, "pdf_page": 1, "quote": B}])
    observed = ObservedResponse(
        status="ANSWERED",
        question_type="how_many",
        components=(ObservedComponent(1, True, ("e1",), frozenset({"e1"})),),
        spans=(),
        evidence=(ObservedEvidence("e1", 1, B, 0, len(B), frozenset({1})),),
        retrieval=(ObservedRetrieval(1, 50, ((1, "e1"),)),),
    )
    score = score_record(answerable, observed, {"e1": (1, B)}, {1: PAGE})
    rates = build_metrics([score])["outcomes"]["rates"]
    assert rates["false_acceptance_rate"] == rate(0, 0).as_dict()
    assert rates["false_acceptance_rate"]["value"] is None


def test_a_wrong_component_in_a_partial_response_is_not_hidden_by_a_correct_one():
    record = gold("PARTIAL", [{"component": 1, "pdf_page": 1, "quote": B}], [{"component": 1, "text": "30 days"}])
    observed = ObservedResponse(
        status="PARTIAL",
        question_type="compound",
        components=(
            ObservedComponent(1, True, ("e1",), frozenset({"e1"})),
            ObservedComponent(2, True, ("e2",), frozenset({"e2"})),
        ),
        spans=(),
        evidence=(
            ObservedEvidence("e1", 1, B, 0, len(B), frozenset({1})),
            ObservedEvidence("e2", 1, S, len(B) + 1, len(B) + 1 + len(S), frozenset({2})),
        ),
        retrieval=(ObservedRetrieval(1, 50, ((1, "e1"),)), ObservedRetrieval(2, 50, ((1, "e2"),))),
    )
    score = score_record(record, observed, {"e1": (1, B), "e2": (1, S)}, {1: PAGE})
    assert score.outcome == "incorrect_answer"


def test_a_quote_with_one_changed_character_is_refused_by_the_store(tmp_path):
    rows = GOLD.read_text(encoding="utf-8").splitlines()
    record = json.loads(rows[0])
    record["evidence"][0]["quote"] = "The limit for loans is 31 days after approval."
    record["answers"] = []
    path = tmp_path / "gold.jsonl"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    store = stored_document(DOC, main_items())
    try:
        with pytest.raises(GoldError, match="not verbatim"):
            check_against_store(load_gold(path).records[0], store, DOC)
    finally:
        store.close()


def test_a_held_out_run_without_the_final_flag_never_reaches_the_engine(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("the engine must not be called for held-out records without final_run=True")

    monkeypatch.setattr(runner_module, "answer", forbidden)
    store = stored_document(DOC, main_items())
    try:
        with pytest.raises(EvaluationError, match="final_run=True"):
            run_evaluation(store, DOC, load_gold(GOLD), "heldout", output_dir=tmp_path)
    finally:
        store.close()
    assert list(tmp_path.iterdir()) == []


def test_a_development_run_with_the_final_flag_is_refused(tmp_path):
    store = stored_document(DOC, main_items())
    try:
        with pytest.raises(EvaluationError, match="applies only to held-out"):
            run_evaluation(store, DOC, load_gold(GOLD), "dev", final_run=True, output_dir=tmp_path)
    finally:
        store.close()


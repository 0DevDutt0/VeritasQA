"""P8a end to end on labelled synthetic documents (ARCHITECTURE §17; SPEC §11, §12).

The gold file is hand-written from the fixture text (tests/fixtures/p8_synthetic_gold.jsonl). Each expected status
comes from the document, not from the engine. Two expected outcomes are known design costs, and each is named below.
"""

import json
from pathlib import Path

import pytest

from app.decision import load_policy
from app.evaluation import EvaluationError, GoldError, load_gold, run_evaluation
from app.evaluation import runner as runner_module
from tests.fixtures.verification_docs import main_items, stored_document

GOLD = Path(__file__).resolve().parents[1] / "fixtures" / "p8_synthetic_gold.jsonl"
DOC = "doc-" + "9" * 16
HELDOUT_QUESTION = "Does the board approve the loan for small businesses?"

EXPECTED_DEV_OUTCOMES = {
    "s-limit-days-direct": "correct_answer",
    # D67: "permitted" is not in the passage "may share", so the verifier cannot confirm the property word.
    "s-staff-permitted-share": "incorrect_abstention",
    "s-mortgage-rate-unanswerable": "correct_abstention",
    "s-limit-and-mortgage-partial": "correct_answer",
    # D65: a who-question is passage-only and is never answered, although the document does answer it.
    "s-who-approves-board": "incorrect_abstention",
    "s-fee-visitors-unanswerable": "correct_abstention",
}


@pytest.fixture
def store():
    stored = stored_document(DOC, main_items())
    yield stored
    stored.close()


def forbid_engine(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("the engine must not be called on this path")

    monkeypatch.setattr(runner_module, "answer", forbidden)


def test_each_dev_record_gets_its_expected_outcome(store, tmp_path):
    run = run_evaluation(
        store, DOC, load_gold(GOLD), "dev", output_dir=tmp_path, run_id="run-dev-1", created_at="2026-01-01T00:00:00Z"
    )
    assert {row["record_id"]: row["outcome"] for row in run.records} == EXPECTED_DEV_OUTCOMES


def test_the_aggregate_counts_and_rates_follow_from_the_outcomes(store, tmp_path):
    run = run_evaluation(store, DOC, load_gold(GOLD), "dev", output_dir=tmp_path, run_id="run-dev-agg")
    outcomes = run.metrics["outcomes"]
    assert outcomes["total"] == 6
    assert outcomes["answerable"] == 4
    assert outcomes["unanswerable"] == 2
    assert outcomes["accepted"] == 2
    assert outcomes["counts"]["correct_answer"] == 2
    assert outcomes["counts"]["incorrect_abstention"] == 2
    assert outcomes["counts"]["correct_abstention"] == 2
    assert outcomes["counts"]["false_acceptance"] == 0
    rates = outcomes["rates"]
    assert rates["false_acceptance_rate"]["n"] == 2
    assert rates["false_acceptance_rate"]["value"] == 0.0
    assert rates["false_acceptance_rate"]["high"] == pytest.approx(0.65770, abs=1e-4)
    assert rates["incorrect_abstention_rate"]["value"] == 0.5
    assert rates["coverage"]["value"] == pytest.approx(2 / 6)
    assert rates["selective_risk"]["value"] == 0.0


def test_the_breakdowns_show_where_the_misses_sit(store, tmp_path):
    run = run_evaluation(store, DOC, load_gold(GOLD), "dev", output_dir=tmp_path, run_id="run-dev-break")
    by_type = run.metrics["breakdown"]["question_type"]
    assert by_type["who"]["counts"]["incorrect_abstention"] == 1
    assert by_type["whether"]["counts"]["incorrect_abstention"] == 1
    assert by_type["compound"]["counts"]["correct_answer"] == 1
    by_category = run.metrics["breakdown"]["category"]
    assert set(by_category) == {"compound", "direct_fact", "numeric_date", "paraphrase", "unanswerable"}


def test_the_answer_and_status_measures_are_computed_from_the_gold(store, tmp_path):
    run = run_evaluation(store, DOC, load_gold(GOLD), "dev", output_dir=tmp_path, run_id="run-dev-answers")
    answers = run.metrics["answers"]
    assert answers["exact_match"]["n"] == 2
    assert answers["exact_match"]["value"] == 1.0
    assert answers["status_accuracy"]["n"] == 6
    assert answers["status_accuracy"]["value"] == pytest.approx(4 / 6)


def test_the_run_record_names_the_policy_the_dataset_and_the_synthetic_label(store, tmp_path):
    dataset = load_gold(GOLD)
    run = run_evaluation(store, DOC, dataset, "dev", output_dir=tmp_path, run_id="run-dev-label")
    payload = json.loads(run.output_path.read_text(encoding="utf-8"))
    assert payload["synthetic"] is True
    assert payload["banner"].startswith("Synthetic test set")
    assert payload["config"]["policy_sha256"] == load_policy().sha256
    assert payload["config"]["dataset_sha256"] == dataset.sha256
    assert payload["dataset"]["record_count"] == 6
    row = store.read_evaluation("run-dev-label")
    assert row["split"] == "dev"
    assert row["dataset_sha256"] == dataset.sha256


def test_the_store_row_holds_the_same_metrics_as_the_run_file(store, tmp_path):
    run = run_evaluation(store, DOC, load_gold(GOLD), "dev", output_dir=tmp_path, run_id="run-dev-row")
    row = store.read_evaluation("run-dev-row")
    assert json.loads(row["metrics_json"]) == json.loads(json.dumps(run.metrics, sort_keys=True))


def test_two_runs_with_different_ids_and_times_give_identical_metrics(store, tmp_path):
    dataset = load_gold(GOLD)
    first = run_evaluation(store, DOC, dataset, "dev", output_dir=tmp_path, run_id="run-a", created_at="t1")
    second = run_evaluation(store, DOC, dataset, "dev", output_dir=tmp_path, run_id="run-b", created_at="t2")
    assert first.metrics == second.metrics
    assert store.read_evaluation("run-a")["metrics_json"] == store.read_evaluation("run-b")["metrics_json"]


def test_a_development_run_never_asks_the_engine_about_a_held_out_record(store, tmp_path, monkeypatch):
    asked = []
    original = runner_module.answer

    def recording(store_, document_id, question, *args, **kwargs):
        asked.append(question)
        return original(store_, document_id, question, *args, **kwargs)

    monkeypatch.setattr(runner_module, "answer", recording)
    run_evaluation(store, DOC, load_gold(GOLD), "dev", output_dir=tmp_path, run_id="run-dev-guard")
    assert HELDOUT_QUESTION not in asked
    assert len(asked) == 6


def test_a_held_out_run_without_the_final_flag_is_refused_before_any_answer(store, tmp_path, monkeypatch):
    forbid_engine(monkeypatch)
    with pytest.raises(EvaluationError, match="final_run=True"):
        run_evaluation(store, DOC, load_gold(GOLD), "heldout", output_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_the_final_held_out_run_is_allowed_with_the_flag(store, tmp_path):
    run = run_evaluation(
        store, DOC, load_gold(GOLD), "heldout", final_run=True, output_dir=tmp_path, run_id="run-final-1"
    )
    assert run.split == "heldout"
    assert run.final_run is True
    assert run.record_count == 1
    assert run.records[0]["record_id"] == "s-heldout-board-approves"


def test_an_inexact_quotation_stops_the_run_before_any_answer(store, tmp_path, monkeypatch):
    record = json.loads(GOLD.read_text(encoding="utf-8").splitlines()[0])
    record["evidence"][0]["quote"] = "The limit for loans is 31 days after approval."
    record["answers"] = []
    path = tmp_path / "inexact.jsonl"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    forbid_engine(monkeypatch)
    with pytest.raises(GoldError, match="not verbatim"):
        run_evaluation(store, DOC, load_gold(path), "dev", output_dir=tmp_path)


def test_a_repeated_run_id_is_refused_and_the_first_file_is_kept(store, tmp_path):
    dataset = load_gold(GOLD)
    run_evaluation(store, DOC, dataset, "dev", output_dir=tmp_path, run_id="run-same")
    before = (tmp_path / "run-same.json").read_text(encoding="utf-8")
    with pytest.raises(EvaluationError, match="already recorded"):
        run_evaluation(store, DOC, dataset, "dev", output_dir=tmp_path, run_id="run-same")
    assert (tmp_path / "run-same.json").read_text(encoding="utf-8") == before


@pytest.mark.parametrize("bad_run_id", ["../escape", "a/b", "", ".hidden", "x" * 81, "run one"])
def test_a_run_id_that_is_not_a_plain_file_name_is_refused_before_any_write(store, tmp_path, bad_run_id):
    with pytest.raises(EvaluationError, match="run id"):
        run_evaluation(store, DOC, load_gold(GOLD), "dev", output_dir=tmp_path, run_id=bad_run_id)
    assert list(tmp_path.iterdir()) == []


def test_a_document_that_is_not_stored_is_refused(store, tmp_path):
    with pytest.raises(EvaluationError, match="not in the store"):
        run_evaluation(store, "doc-" + "0" * 16, load_gold(GOLD), "dev", output_dir=tmp_path)

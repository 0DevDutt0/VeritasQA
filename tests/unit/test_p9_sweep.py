"""P9a sweep, end to end on the labelled synthetic document (ARCHITECTURE §18; D90 to D94, D97).

The expected retrieval values are worked out by hand from the document in tests/fixtures/p9_sweep_docs.py (see that
module's docstring), not read back from the engine.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.benchmark import BenchmarkError, run_sweep
from app.benchmark import sweep as sweep_module
from app.decision import load_policy
from app.evaluation import load_gold
from app.evaluation import runner as runner_module
from app.retrieval.config import RetrievalConfig
from tests.fixtures.p9_sweep_docs import DOC, sweep_items
from tests.fixtures.verification_docs import stored_document

# Every full sweep runs the TF-IDF and RRF baselines, which need scikit-learn (requirements-experimental.txt). A
# baseline-only environment reports this module as skipped (ARCHITECTURE §18.6).
pytest.importorskip("sklearn", reason="the sweep runs the TF-IDF and RRF baselines, which need scikit-learn")

REPO = Path(__file__).resolve().parents[2]
GOLD = REPO / "tests" / "fixtures" / "p9_synthetic_gold.jsonl"
CONFIG_DIR = REPO / "config"
CREATED = "2026-01-01T00:00:00Z"
DEV_QUESTIONS = {"What is quarterly?", "What is the interest rate for mortgages?"}
HELDOUT_QUESTION = "Does quarterly mean once every three months?"

ONE = {"n": 1, "value": 1.0}
ZERO = {"n": 1, "value": 0.0}
HALF = {"n": 1, "value": 0.5}
NOT_SEARCHED = {"n": 0, "value": None}


@pytest.fixture
def store():
    stored = stored_document(DOC, sweep_items())
    yield stored
    stored.close()


@pytest.fixture
def dataset():
    return load_gold(GOLD)


def _sweep(store, dataset, output_dir, sweep_id="p9-test-a", **kwargs):
    return run_sweep(store, DOC, dataset, output_dir=output_dir, sweep_id=sweep_id, created_at=CREATED, **kwargs)


def _point(summary, k, window, heading):
    matches = [
        point
        for point in summary["points"]
        if (point["k"], point["context_window"], point["heading_weight"]) == (k, window, heading)
    ]
    assert len(matches) == 1
    return matches[0]


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_each_point_is_one_evaluation_on_the_dev_split(store, dataset, tmp_path):
    result = _sweep(store, dataset, tmp_path)
    assert [run.run_id for run in result.runs] == [f"p9-test-a-{index:02d}" for index in range(1, 37)]
    assert all(run.split == "dev" and run.final_run is False for run in result.runs)
    assert all((tmp_path / f"{run.run_id}.json").is_file() for run in result.runs)
    assert all(store.read_evaluation(run.run_id)["split"] == "dev" for run in result.runs)
    assert result.summary_path == tmp_path / "p9-test-a-summary.json"
    assert json.loads(result.summary_path.read_text(encoding="utf-8")) == result.summary


def test_the_run_calls_never_ask_for_the_held_out_split(store, dataset, tmp_path, monkeypatch):
    calls = []
    original = sweep_module.run_evaluation

    def spy(*args, **kwargs):
        calls.append((args[3], kwargs["final_run"]))
        return original(*args, **kwargs)

    monkeypatch.setattr(sweep_module, "run_evaluation", spy)
    _sweep(store, dataset, tmp_path)
    assert calls == [("dev", False)] * 36


def test_a_held_out_question_never_reaches_the_engine(store, dataset, tmp_path, monkeypatch):
    seen: list[str] = []
    original = runner_module.answer

    def recording(store_, document_id, question, *args, **kwargs):
        seen.append(question)
        return original(store_, document_id, question, *args, **kwargs)

    monkeypatch.setattr(runner_module, "answer", recording)
    _sweep(store, dataset, tmp_path)
    assert HELDOUT_QUESTION not in seen
    assert set(seen) == DEV_QUESTIONS


@pytest.mark.parametrize(
    ("k", "window", "heading", "expected"),
    [
        # Heading weight 1.0: the gold passage is first. K = 1 keeps it.
        (1, 0, 1.0, {"recall_at_1": ONE, "recall_at_5": NOT_SEARCHED, "mrr": ONE}),
        # Heading weight 2.0 or 4.0: the heading unit is first, so K = 1 leaves the gold passage out.
        (1, 0, 2.0, {"recall_at_1": ZERO, "recall_at_5": NOT_SEARCHED, "mrr": ZERO}),
        (1, 2, 4.0, {"recall_at_1": ZERO, "recall_at_5": NOT_SEARCHED, "mrr": ZERO}),
        (5, 1, 1.0, {"recall_at_1": ONE, "recall_at_5": ONE, "mrr": ONE}),
        (5, 1, 2.0, {"recall_at_1": ZERO, "recall_at_5": ONE, "mrr": HALF}),
        (10, 2, 4.0, {"recall_at_1": ZERO, "recall_at_5": ONE, "recall_at_10": ONE, "mrr": HALF}),
        (50, 1, 2.0, {"recall_at_1": ZERO, "recall_at_5": ONE, "recall_at_10": ONE, "recall_at_50": ONE, "mrr": HALF}),
    ],
)
def test_the_retrieval_values_of_a_point_match_the_hand_computed_values(
    store, dataset, tmp_path, k, window, heading, expected
):
    point = _point(_sweep(store, dataset, tmp_path).summary, k, window, heading)
    for key, value in expected.items():
        assert point["retrieval"][key] == value, key
    if "recall_at_50" not in expected:
        assert point["retrieval"]["recall_at_50"] == NOT_SEARCHED


def test_the_context_window_changes_no_retrieval_value(store, dataset, tmp_path):
    summary = _sweep(store, dataset, tmp_path).summary
    for k in (1, 5, 10, 50):
        for heading in (1.0, 2.0, 4.0):
            values = [_point(summary, k, window, heading)["retrieval"] for window in (0, 1, 2)]
            assert values[0] == values[1] == values[2], (k, heading)


def test_the_tie_groups_are_the_hand_computed_groups(store, dataset, tmp_path):
    summary = _sweep(store, dataset, tmp_path).summary
    assert summary["distinct_results"] == 8
    assert summary["tie_groups"] == [
        [1, 4, 7],
        [2, 3, 5, 6, 8, 9],
        [10, 13, 16],
        [11, 12, 14, 15, 17, 18],
        [19, 22, 25],
        [20, 21, 23, 24, 26, 27],
        [28, 31, 34],
        [29, 30, 32, 33, 35, 36],
    ]


def test_the_outcome_counts_do_not_separate_the_points_on_this_set(store, dataset, tmp_path):
    points = _sweep(store, dataset, tmp_path).summary["points"]
    counts = {json.dumps(point["counts"], sort_keys=True) for point in points}
    assert len(counts) == 1


def test_the_summary_is_marked_synthetic_and_names_no_best_point(store, dataset, tmp_path):
    summary = _sweep(store, dataset, tmp_path).summary
    assert summary["synthetic"] is True
    assert summary["banner"].startswith("Synthetic test set")
    assert summary["split"] == "dev"
    assert summary["dataset"]["dev_records"] == 2
    assert summary["dataset"]["total_records"] == 3
    text = json.dumps(summary).lower()
    assert "best" not in text
    assert "recommend" not in text


def test_two_sweeps_with_different_ids_and_times_give_the_same_metrics_text(store, dataset, tmp_path):
    _sweep(store, dataset, tmp_path, sweep_id="p9-test-d")
    run_sweep(
        store,
        DOC,
        dataset,
        output_dir=tmp_path,
        sweep_id="p9-test-e",
        created_at="2026-02-02T00:00:00Z",
    )
    for index in range(1, 37):
        first = store.read_evaluation(f"p9-test-d-{index:02d}")
        second = store.read_evaluation(f"p9-test-e-{index:02d}")
        assert first["metrics_json"] == second["metrics_json"], index
        assert first["config_json"] == second["config_json"], index


def test_no_configuration_file_is_written_and_the_policy_stays_uncalibrated(store, dataset, tmp_path):
    before = {path.name: _hash(path) for path in sorted(CONFIG_DIR.glob("*.toml"))}
    _sweep(store, dataset, tmp_path)
    after = {path.name: _hash(path) for path in sorted(CONFIG_DIR.glob("*.toml"))}
    assert before == after
    assert load_policy().calibrated is False


@pytest.mark.parametrize("sweep_id", ["", "../escape", "a/b", "has space", ".hidden", "x" * 61])
def test_a_sweep_id_that_is_not_a_plain_name_is_refused_before_any_write(store, dataset, tmp_path, sweep_id):
    with pytest.raises(BenchmarkError):
        _sweep(store, dataset, tmp_path, sweep_id=sweep_id)
    assert list(tmp_path.iterdir()) == []


def test_an_existing_point_file_refuses_the_whole_sweep_before_any_write(store, dataset, tmp_path):
    (tmp_path / "p9-test-b-05.json").write_text("{}", encoding="utf-8")
    with pytest.raises(BenchmarkError, match="already exists"):
        _sweep(store, dataset, tmp_path, sweep_id="p9-test-b")
    assert {path.name for path in tmp_path.iterdir()} == {"p9-test-b-05.json"}
    assert store.read_evaluation("p9-test-b-01") is None


def test_an_existing_summary_refuses_the_sweep(store, dataset, tmp_path):
    (tmp_path / "p9-test-f-summary.json").write_text("{}", encoding="utf-8")
    with pytest.raises(BenchmarkError, match="summary"):
        _sweep(store, dataset, tmp_path, sweep_id="p9-test-f")
    assert {path.name for path in tmp_path.iterdir()} == {"p9-test-f-summary.json"}


def test_a_run_id_already_in_the_store_refuses_the_sweep(store, dataset, tmp_path):
    store.record_evaluation(
        run_id="p9-test-c-17",
        created_at=CREATED,
        split="dev",
        config_json="{}",
        metrics_json="{}",
        dataset_sha256="0" * 64,
    )
    with pytest.raises(BenchmarkError, match="already recorded"):
        _sweep(store, dataset, tmp_path, sweep_id="p9-test-c")
    assert list(tmp_path.iterdir()) == []


def test_a_document_that_is_not_in_the_store_is_refused(store, dataset, tmp_path):
    with pytest.raises(BenchmarkError, match="not in the store"):
        run_sweep(store, "doc-missing", dataset, output_dir=tmp_path, sweep_id="p9-test-g")
    assert list(tmp_path.iterdir()) == []


def test_a_point_that_fails_leaves_the_finished_points_and_no_summary(store, dataset, tmp_path, monkeypatch):
    original = sweep_module.run_evaluation
    calls = {"count": 0}

    def failing_on_fifth(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 5:
            raise RuntimeError("simulated failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(sweep_module, "run_evaluation", failing_on_fifth)
    with pytest.raises(RuntimeError, match="simulated failure"):
        _sweep(store, dataset, tmp_path, sweep_id="p9-test-h")
    names = {path.name for path in tmp_path.iterdir()}
    assert names == {f"p9-test-h-{index:02d}.json" for index in range(1, 5)}
    assert store.read_evaluation("p9-test-h-05") is None


def test_the_fixture_is_sensitive_to_the_heading_weight(store, dataset, tmp_path, monkeypatch):
    """A sweep that ignored the heading weight would give other values here (D97). This guards the fixture itself."""

    def ignore_heading_weight(self, base):
        return RetrievalConfig(
            k=self.k,
            expansion_k=base.expansion_k,
            weight_index=base.weight_index,
            weight_heading=base.weight_heading,
            context_window=self.context_window,
        )

    summary = _sweep(store, dataset, tmp_path, sweep_id="p9-test-i").summary
    assert _point(summary, 5, 1, 1.0)["retrieval"]["recall_at_1"] == ONE
    monkeypatch.setattr(sweep_module.SweepPoint, "config", ignore_heading_weight)
    broken = _sweep(store, dataset, tmp_path / "broken", sweep_id="p9-test-j").summary
    assert _point(broken, 5, 1, 1.0)["retrieval"]["recall_at_1"] == ZERO

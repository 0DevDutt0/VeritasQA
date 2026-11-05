"""P10: the owner-document banner and the annotators field of a run record (ARCHITECTURE §19.6; D115).

The tests use the synthetic store of the P8 harness. Its gold file is relabelled as owner-document records inside
``tmp_path``, so no owner data is read and no result about the owner's document is produced.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.evaluation import load_gold, run_evaluation
from app.evaluation.gold import Source, select_split
from app.evaluation.runner import OWNER_DOCUMENT_BANNER, STAND_IN_BANNER, SYNTHETIC_BANNER, banner_for
from tests.fixtures.verification_docs import main_items, stored_document

GOLD = Path(__file__).resolve().parents[1] / "fixtures" / "p8_synthetic_gold.jsonl"
DOC = "doc-" + "9" * 16


@pytest.fixture
def store():
    stored = stored_document(DOC, main_items())
    yield stored
    stored.close()


def _owner_labelled_gold(tmp_path: Path) -> Path:
    """The P8 gold file with every record relabelled as owner_document. Annotators alternate between two names."""
    lines = []
    for index, line in enumerate(GOLD.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        record = json.loads(line)
        record["source"] = "owner_document"
        record["annotator"] = "annotator-A" if index % 2 == 0 else "annotator-B"
        lines.append(json.dumps(record, ensure_ascii=False))
    path = tmp_path / "owner-labelled.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_the_owner_document_has_its_own_banner_and_it_points_to_the_annotators() -> None:
    assert banner_for(Source.OWNER_DOCUMENT) == OWNER_DOCUMENT_BANNER
    assert "owner's document" in OWNER_DOCUMENT_BANNER
    assert "annotators" in OWNER_DOCUMENT_BANNER
    assert "not been checked by the owner" in OWNER_DOCUMENT_BANNER
    assert OWNER_DOCUMENT_BANNER not in {SYNTHETIC_BANNER, STAND_IN_BANNER}


def test_the_owner_banner_does_not_name_an_annotator() -> None:
    # The banner is keyed to the source only. Who annotated a record is in the annotators field.
    assert "assistant-drafted" not in OWNER_DOCUMENT_BANNER
    assert "Claude" not in OWNER_DOCUMENT_BANNER


def test_a_run_on_owner_labelled_records_carries_the_owner_banner_and_the_annotators_of_its_split(store, tmp_path):
    dataset = load_gold(_owner_labelled_gold(tmp_path))
    run = run_evaluation(store, DOC, dataset, "dev", output_dir=tmp_path, run_id="run-owner-banner")
    payload = json.loads(run.output_path.read_text(encoding="utf-8"))
    assert payload["source"] == "owner_document"
    assert payload["banner"] == OWNER_DOCUMENT_BANNER
    assert payload["synthetic"] is False
    assert payload["public_document"] is False
    expected = sorted({record.annotator for record in select_split(dataset, "dev", final_run=False)})
    assert payload["annotators"] == expected
    assert expected == ["annotator-A", "annotator-B"]


def test_a_synthetic_run_lists_its_annotators_and_keeps_its_banner(store, tmp_path):
    dataset = load_gold(GOLD)
    run = run_evaluation(store, DOC, dataset, "dev", output_dir=tmp_path, run_id="run-synthetic-annotators")
    payload = json.loads(run.output_path.read_text(encoding="utf-8"))
    expected = sorted({record.annotator for record in select_split(dataset, "dev", final_run=False)})
    assert payload["annotators"] == expected
    assert payload["banner"] == SYNTHETIC_BANNER


def test_annotators_stay_out_of_the_config_and_the_metrics(store, tmp_path):
    dataset = load_gold(_owner_labelled_gold(tmp_path))
    run = run_evaluation(store, DOC, dataset, "dev", output_dir=tmp_path, run_id="run-owner-hash")
    payload = json.loads(run.output_path.read_text(encoding="utf-8"))
    assert "annotators" not in payload["config"]
    assert "annotators" not in payload["metrics"]
    row = store.read_evaluation("run-owner-hash")
    assert row is not None
    assert "annotator" not in row["config_json"]
    assert "annotator" not in row["metrics_json"]

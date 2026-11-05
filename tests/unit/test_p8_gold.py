"""Gold records: layer 1 (shape and consistency) and the split and source guard (ARCHITECTURE §17.2, §17.3, §17.5)."""

import hashlib
import json

import pytest
from pydantic import ValidationError

from app.evaluation.errors import EvaluationError, GoldError
from app.evaluation.gold import GoldRecord, load_gold, select_split

QUOTE = "The limit for loans is 30 days after approval."


def record(**overrides) -> dict:
    base = {
        "record_id": "limit-days",
        "question": "How many days is the limit for loans?",
        "category": "numeric_date",
        "source": "synthetic",
        "split": "dev",
        "annotator": "test",
        "expected_status": "ANSWERED",
        "evidence": [{"component": 1, "pdf_page": 1, "quote": QUOTE}],
        "answers": [{"component": 1, "text": "30 days"}],
    }
    base.update(overrides)
    return base


def test_a_well_formed_record_is_accepted():
    parsed = GoldRecord.model_validate(record())
    assert parsed.answerable


def test_an_extra_field_is_refused():
    with pytest.raises(ValidationError):
        GoldRecord.model_validate(record(notes="not in the schema"))


def test_an_uppercase_record_id_is_refused():
    with pytest.raises(ValidationError):
        GoldRecord.model_validate(record(record_id="Limit-Days"))


def test_a_blank_question_is_refused():
    with pytest.raises(ValidationError):
        GoldRecord.model_validate(record(question="   "))


def test_an_unknown_category_is_refused():
    with pytest.raises(ValidationError):
        GoldRecord.model_validate(record(category="trivia"))


def test_an_unknown_split_such_as_all_is_refused():
    with pytest.raises(ValidationError):
        GoldRecord.model_validate(record(split="all"))


def test_a_blank_annotator_is_refused():
    with pytest.raises(ValidationError):
        GoldRecord.model_validate(record(annotator=""))


def test_an_answerable_record_needs_gold_evidence():
    with pytest.raises(ValidationError):
        GoldRecord.model_validate(record(evidence=[], answers=[]))


def test_an_unanswerable_record_may_not_give_answer_spans():
    with pytest.raises(ValidationError):
        GoldRecord.model_validate(record(expected_status="INSUFFICIENT_EVIDENCE"))


def test_an_answer_must_be_inside_the_evidence_of_its_component():
    with pytest.raises(ValidationError):
        GoldRecord.model_validate(record(answers=[{"component": 1, "text": "45 days"}]))


def test_an_answer_must_be_inside_evidence_of_the_same_component():
    with pytest.raises(ValidationError):
        GoldRecord.model_validate(
            record(
                evidence=[{"component": 1, "pdf_page": 1, "quote": QUOTE}],
                answers=[{"component": 2, "text": "30 days"}],
            )
        )


def test_a_page_below_one_is_refused():
    with pytest.raises(ValidationError):
        GoldRecord.model_validate(record(evidence=[{"component": 1, "pdf_page": 0, "quote": QUOTE}]))


def test_a_component_below_one_is_refused():
    with pytest.raises(ValidationError):
        GoldRecord.model_validate(record(evidence=[{"component": 0, "pdf_page": 1, "quote": QUOTE}]))


def test_a_blank_quote_is_refused():
    with pytest.raises(ValidationError):
        GoldRecord.model_validate(record(evidence=[{"component": 1, "pdf_page": 1, "quote": " \n "}]))


def write_lines(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_load_gold_records_the_sha256_of_the_file_bytes(tmp_path):
    path = write_lines(tmp_path / "gold.jsonl", [json.dumps(record(), ensure_ascii=False)])
    dataset = load_gold(path)
    assert dataset.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert dataset.file_name == "gold.jsonl"
    assert len(dataset.records) == 1


def test_load_gold_reads_utf8_text(tmp_path):
    path = write_lines(
        tmp_path / "gold.jsonl",
        [json.dumps(record(question="Wie lange ist das Café-Limit?", evidence=[{"component": 1, "pdf_page": 1, "quote": QUOTE}], answers=[]), ensure_ascii=False)],
    )
    assert load_gold(path).records[0].question.endswith("Café-Limit?")


def test_a_blank_line_is_refused_with_its_number(tmp_path):
    path = write_lines(tmp_path / "gold.jsonl", [json.dumps(record()), "", json.dumps(record(record_id="other"))])
    with pytest.raises(GoldError, match="line 2 is blank"):
        load_gold(path)


def test_invalid_json_is_refused_with_its_line_number(tmp_path):
    path = write_lines(tmp_path / "gold.jsonl", [json.dumps(record()), "{not json"])
    with pytest.raises(GoldError, match="line 2 is not valid JSON"):
        load_gold(path)


def test_a_schema_error_names_its_line(tmp_path):
    path = write_lines(tmp_path / "gold.jsonl", [json.dumps(record(category="trivia"))])
    with pytest.raises(GoldError, match="line 1"):
        load_gold(path)


def test_a_repeated_record_id_is_refused(tmp_path):
    path = write_lines(tmp_path / "gold.jsonl", [json.dumps(record()), json.dumps(record())])
    with pytest.raises(GoldError, match="repeats the record id"):
        load_gold(path)


def test_an_empty_file_is_refused(tmp_path):
    path = write_lines(tmp_path / "gold.jsonl", [])
    with pytest.raises(GoldError, match="holds no records"):
        load_gold(path)


def dataset_with(tmp_path, *records):
    path = write_lines(tmp_path / "gold.jsonl", [json.dumps(item) for item in records])
    return load_gold(path)


def test_a_development_run_selects_only_development_records(tmp_path):
    dataset = dataset_with(
        tmp_path,
        record(record_id="a", split="dev"),
        record(record_id="b", split="heldout"),
    )
    chosen = select_split(dataset, "dev", final_run=False)
    assert [item.record_id for item in chosen] == ["a"]


def test_a_held_out_run_without_the_final_flag_is_refused(tmp_path):
    dataset = dataset_with(tmp_path, record(record_id="b", split="heldout"))
    with pytest.raises(EvaluationError, match="final_run=True"):
        select_split(dataset, "heldout", final_run=False)


def test_a_held_out_run_with_the_final_flag_selects_held_out_records(tmp_path):
    dataset = dataset_with(tmp_path, record(record_id="b", split="heldout"), record(record_id="a", split="dev"))
    chosen = select_split(dataset, "heldout", final_run=True)
    assert [item.record_id for item in chosen] == ["b"]


def test_the_final_flag_is_refused_for_development_records(tmp_path):
    dataset = dataset_with(tmp_path, record(record_id="a", split="dev"))
    with pytest.raises(EvaluationError, match="applies only to held-out"):
        select_split(dataset, "dev", final_run=True)


def test_all_is_not_a_split(tmp_path):
    dataset = dataset_with(tmp_path, record(record_id="a", split="dev"))
    with pytest.raises(EvaluationError, match="unknown split"):
        select_split(dataset, "all", final_run=False)


def test_a_run_may_not_mix_synthetic_and_owner_records(tmp_path):
    dataset = dataset_with(
        tmp_path,
        record(record_id="a", split="dev", source="synthetic"),
        record(record_id="b", split="dev", source="owner_document"),
    )
    with pytest.raises(EvaluationError, match="may not mix"):
        select_split(dataset, "dev", final_run=False)


def test_a_split_with_no_records_is_refused(tmp_path):
    dataset = dataset_with(tmp_path, record(record_id="a", split="dev"))
    with pytest.raises(EvaluationError, match="no heldout records"):
        select_split(dataset, "heldout", final_run=True)

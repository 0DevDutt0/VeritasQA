"""Source labels and banners of the public stand-in gold set (ARCHITECTURE §17.15; D101).

These tests use no document and no owner data. They check the label rules and the banner text only.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.evaluation.errors import EvaluationError
from app.evaluation.gold import GoldDataset, GoldRecord, Source, select_split
from app.evaluation.runner import OWNER_DOCUMENT_BANNER, STAND_IN_BANNER, SYNTHETIC_BANNER, banner_for


def _record(record_id: str, source: str, split: str = "dev") -> GoldRecord:
    return GoldRecord.model_validate(
        {
            "record_id": record_id,
            "question": "What is the limit for loans?",
            "category": "direct_fact",
            "source": source,
            "split": split,
            "annotator": "unit-test",
            "expected_status": "INSUFFICIENT_EVIDENCE",
            "evidence": [],
            "answers": [],
        }
    )


def test_public_document_is_its_own_source_value_and_owner_document_is_unchanged() -> None:
    assert Source("public_document") is Source.PUBLIC_DOCUMENT
    assert Source("owner_document") is Source.OWNER_DOCUMENT
    assert Source("synthetic") is Source.SYNTHETIC


def test_a_record_with_the_public_source_is_accepted() -> None:
    assert _record("pub-one", "public_document").source is Source.PUBLIC_DOCUMENT


def test_a_short_or_unknown_source_name_is_refused() -> None:
    with pytest.raises(ValidationError):
        _record("pub-two", "public")


def test_a_run_refuses_to_mix_public_and_synthetic_records() -> None:
    dataset = GoldDataset(
        file_name="mixed.jsonl",
        sha256="0" * 64,
        records=(_record("mix-synthetic", "synthetic"), _record("mix-public", "public_document")),
    )
    with pytest.raises(EvaluationError, match="may not mix"):
        select_split(dataset, "dev", final_run=False)


def test_each_source_gets_its_own_banner() -> None:
    assert banner_for(Source.SYNTHETIC) == SYNTHETIC_BANNER
    assert banner_for(Source.PUBLIC_DOCUMENT) == STAND_IN_BANNER
    # P10 (D115): an owner-document run now carries its own banner, which names the annotators field.
    assert banner_for(Source.OWNER_DOCUMENT) == OWNER_DOCUMENT_BANNER


def test_the_stand_in_banner_says_who_wrote_it_and_what_it_is_not() -> None:
    assert "written by the assistant" in STAND_IN_BANNER
    assert "not a measurement of the owner's document" in STAND_IN_BANNER

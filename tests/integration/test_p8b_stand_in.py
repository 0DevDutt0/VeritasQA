"""The local public stand-in gold file (ARCHITECTURE §17.15; D100 to D105).

The gold file and its store are git-ignored and are not part of the repository, so this module skips when either is
absent and a clean checkout still passes. The checks cover the labels, the split rule and the quotations. Failure
messages name record ids only, because a quotation in a message would print question text into a log.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.evaluation.errors import GoldError
from app.evaluation.gold import Source, check_against_store, load_gold
from app.storage import Store

ROOT = Path(__file__).resolve().parents[2]
GOLD_FILE = ROOT / "data" / "evaluations" / "gold" / "standin-nist-sp800-171r3.jsonl"
STORE_FILE = ROOT / "data" / "indexes" / "standin.sqlite"


@pytest.fixture(scope="module")
def stand_in():
    if not GOLD_FILE.is_file() or not STORE_FILE.is_file():
        pytest.skip("the local stand-in gold file or its store is absent (both are git-ignored)")
    dataset = load_gold(GOLD_FILE)
    store = Store.open(STORE_FILE)
    document_id = store.document_ids()[0]
    yield dataset, store, document_id
    store.close()


def _split_by_rule(record_id: str) -> str:
    """ARCHITECTURE §17.15 (D102): held out when the first eight hex digits of SHA-256 of the id are divisible by 3."""
    digest = hashlib.sha256(record_id.encode("utf-8")).hexdigest()
    return "heldout" if int(digest[:8], 16) % 3 == 0 else "dev"


def test_every_record_is_labelled_as_a_public_stand_in(stand_in) -> None:
    dataset, _, _ = stand_in
    wrong = [record.record_id for record in dataset.records if record.source is not Source.PUBLIC_DOCUMENT]
    assert not wrong, f"records with another source label: {wrong}"


def test_every_split_follows_the_fixed_rule(stand_in) -> None:
    dataset, _, _ = stand_in
    wrong = [r.record_id for r in dataset.records if r.split.value != _split_by_rule(r.record_id)]
    assert not wrong, f"records whose split does not follow the rule: {wrong}"


def test_every_quotation_is_verbatim_on_its_stored_page(stand_in) -> None:
    dataset, store, document_id = stand_in
    failing = []
    for record in dataset.records:
        try:
            check_against_store(record, store, document_id)
        except GoldError:
            failing.append(record.record_id)
    assert not failing, f"records that fail the stored-document check: {failing}"


def test_the_record_ids_are_unique_and_the_file_is_not_empty(stand_in) -> None:
    dataset, _, _ = stand_in
    ids = [record.record_id for record in dataset.records]
    assert ids, "the stand-in gold file holds no records"
    assert len(ids) == len(set(ids))

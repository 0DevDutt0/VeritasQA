"""The known-failure list (ARCHITECTURE §17.13; D86).

An open entry must still fail. An entry that the engine now answers as expected must leave the list and join a regression
module. The file starts empty, so the framework is tested here on temporary files as well.
"""

import json
from pathlib import Path

import pytest

from app.decision import DecisionStatus
from tests.fixtures.regression_cases import (
    KnownFailure,
    fixed_entries,
    load_known_failures,
    observed_status,
)

KNOWN_FAILURES = Path(__file__).with_name("known_failures.jsonl")
LOANS = [{"page": 1, "text": "The limit for loans is 30 days after approval."}]


def probe(identifier: str, expected: str, *, items=LOANS, question="How many days is the limit for loans?") -> KnownFailure:
    return KnownFailure.model_validate(
        {
            "id": identifier,
            "phase": "P8a",
            "summary": "framework probe",
            "question": question,
            "expected_status": expected,
            "document": {"items": items},
            "reason": "framework probe, not a real failure",
        }
    )


def test_the_known_failure_file_is_readable_and_its_ids_are_unique():
    cases = load_known_failures(KNOWN_FAILURES)
    assert len({case.id for case in cases}) == len(cases)


def test_every_open_known_failure_still_fails():
    assert fixed_entries(load_known_failures(KNOWN_FAILURES)) == []


def test_an_entry_that_the_engine_now_answers_as_expected_is_reported():
    passing_now = observed_status(probe("probe-passing", "ANSWERED"))
    assert fixed_entries([probe("probe-passing", passing_now)]) == ["probe-passing"]


def test_an_entry_that_still_fails_is_not_reported():
    current = observed_status(probe("probe-open", "ANSWERED"))
    other = next(status for status in DecisionStatus if status.value != current)
    assert fixed_entries([probe("probe-open", other.value)]) == []


def test_a_file_with_an_entry_that_now_passes_is_reported(tmp_path):
    passing_now = observed_status(probe("probe-file", "ANSWERED"))
    path = tmp_path / "known_failures.jsonl"
    line = {
        "id": "probe-file",
        "phase": "P8a",
        "summary": "framework probe",
        "question": "How many days is the limit for loans?",
        "expected_status": passing_now,
        "document": {"items": LOANS},
        "reason": "framework probe, not a real failure",
    }
    path.write_text(json.dumps(line) + "\n", encoding="utf-8")
    assert fixed_entries(load_known_failures(path)) == ["probe-file"]


def test_an_entry_may_name_a_registered_fixture_instead_of_inline_items(tmp_path):
    path = tmp_path / "known_failures.jsonl"
    line = {
        "id": "probe-fixture",
        "phase": "P8a",
        "summary": "framework probe",
        "question": "How many days is the limit for loans?",
        "expected_status": "ANSWERED",
        "document": {"fixture": "loans-main"},
        "reason": "framework probe",
    }
    path.write_text(json.dumps(line) + "\n", encoding="utf-8")
    assert load_known_failures(path)[0].document == {"fixture": "loans-main"}


@pytest.mark.parametrize(
    "document",
    [
        {"fixture": "no-such-fixture"},
        {"items": []},
        {"items": [{"page": 0, "text": "a"}]},
        {"items": [{"page": 1, "text": "   "}]},
        {"items": [{"page": 1, "text": "a", "content_type": "not-a-type"}]},
        {"items": [{"page": 1, "text": "a"}], "fixture": "loans-main"},
        {"file": "x.pdf"},
    ],
)
def test_a_malformed_document_is_refused(document):
    with pytest.raises(ValueError):
        KnownFailure.model_validate(
            {
                "id": "probe-bad",
                "phase": "P8a",
                "summary": "framework probe",
                "question": "How many days is the limit for loans?",
                "expected_status": "ANSWERED",
                "document": document,
                "reason": "framework probe",
            }
        )


def test_a_repeated_id_in_the_file_is_refused(tmp_path):
    path = tmp_path / "known_failures.jsonl"
    entry = {
        "id": "probe-twice",
        "phase": "P8a",
        "summary": "framework probe",
        "question": "How many days is the limit for loans?",
        "expected_status": "ANSWERED",
        "document": {"fixture": "loans-main"},
        "reason": "framework probe",
    }
    path.write_text(json.dumps(entry) + "\n" + json.dumps(entry) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="repeats the id"):
        load_known_failures(path)

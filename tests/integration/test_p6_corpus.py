"""P6 on the public QA corpus (data/corpus/public): verification of every candidate that P5 selects (SPEC §7).

The questions are the ones the P5 corpus test generates. They are imported, so the two phases test the same questions.
No expected answer is written here. The gated checks run on every candidate: every report lists every check in order;
quotation and location pass (P5 builds verbatim quotes from stored units); no passage-only question type passes; the
answer-span check never fails on a candidate that P5 built; and a second run gives the same reports. The verdict
counts are reported with ``-s``. They are property counts on real text, not a measurement on the owner's document
(B1, B3).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from app.document_structure import build_structure
from app.ingestion.extract import extract_document
from app.question_processing.analysis import QuestionType
from app.storage import Store
from app.verification import ORDER, CheckName, CheckStatus, Verdict, verify
from app.verification.vocabulary import ANSWER_TYPES
from tests.fixtures.verification_docs import selection_for
from tests.integration.test_p5_corpus import CREATED, DOCUMENTS, _generate, _present

REPO_ROOT = Path(__file__).resolve().parents[2]
PASSAGE_ONLY = frozenset(set(QuestionType) - set(ANSWER_TYPES) - {QuestionType.UNSUPPORTED})
DETERMINISM_SAMPLE = 60

pytestmark = pytest.mark.public_corpus


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    workdir = tmp_path_factory.mktemp("p6-corpus")
    store = Store.open(workdir / "combined.sqlite")
    structures = {}
    for entry in DOCUMENTS:
        path = _present(entry)
        extracted = extract_document(path, out_root=workdir / "p1")
        structure = build_structure(extracted, path)
        store.write_document(extracted, structure, created_at=CREATED)
        structures[entry["file"]] = (extracted.document_id, structure)

    questions = []
    for entry in DOCUMENTS:
        document_id, structure = structures[entry["file"]]
        for kind, question, _sentence, _unit in _generate(structure):
            questions.append((document_id, kind, question))

    inputs = []
    reports = []
    verdicts: Counter = Counter()
    checks: Counter = Counter()
    page_quality: Counter = Counter()
    blocked_by_flag_only = 0
    for document_id, _kind, question in questions:
        analysis, selection = selection_for(store, document_id, question)
        for component in selection.components:
            for candidate in component.candidates:
                report = verify(candidate, analysis, store, document_id)
                inputs.append((analysis, candidate, document_id))
                reports.append((question, report))
                verdicts[(component.question_type.value, report.verdict.value)] += 1
                for check in report.checks:
                    checks[(check.name.value, check.status.value)] += 1
                unit = store.load_unit(document_id, candidate.evidence_id)
                page_quality[unit.extraction_quality.value] += 1
                if _blocked_only_by_the_page_flag(report, component.question_type, unit.extraction_quality.value):
                    blocked_by_flag_only += 1

    yield {
        "store": store,
        "questions": len(questions),
        "inputs": inputs,
        "reports": reports,
        "verdicts": verdicts,
        "checks": checks,
        "page_quality": page_quality,
        "blocked_by_flag_only": blocked_by_flag_only,
    }
    store.close()


def _blocked_only_by_the_page_flag(report, question_type, page_quality: str) -> bool:
    """True when an answer type is not PASS only because its page is flagged. Such a candidate could pass after a
    repair of the reading order (Q11). This is an upper bound: the context check still has to pass on that page."""
    if report.verdict == Verdict.PASS or question_type not in ANSWER_TYPES or page_quality != "warning":
        return False
    for check in report.checks:
        if check.status not in (CheckStatus.FAIL, CheckStatus.UNRESOLVED):
            continue
        if check.name in (CheckName.SOURCE_QUALITY, CheckName.CONTEXT):
            continue
        return False
    return True


def test_every_report_lists_every_check_in_order(run):
    assert run["reports"], "the public corpus must yield candidates for this test to mean anything"
    for _question, report in run["reports"]:
        assert [check.name for check in report.checks] == list(ORDER)


def test_quotation_and_location_pass_for_every_candidate(run):
    for question, report in run["reports"]:
        assert report.check(CheckName.QUOTATION).status == CheckStatus.PASS, question
        assert report.check(CheckName.LOCATION).status == CheckStatus.PASS, question


def test_no_passage_only_question_type_passes(run):
    for question, report in run["reports"]:
        if report.question_type in PASSAGE_ONLY:
            assert report.verdict != Verdict.PASS, question


def test_the_answer_span_check_never_fails_on_a_candidate_that_p5_built(run):
    for question, report in run["reports"]:
        assert report.check(CheckName.ANSWER_SPAN).status != CheckStatus.FAIL, question


def test_verification_on_the_public_corpus_is_deterministic(run):
    store = run["store"]
    sample = list(zip(run["inputs"][:DETERMINISM_SAMPLE], run["reports"][:DETERMINISM_SAMPLE]))
    assert sample
    for (analysis, candidate, document_id), (question, first) in sample:
        assert verify(candidate, analysis, store, document_id) == first, question


def test_the_verdict_counts_are_reported(run):
    verdicts = run["verdicts"]
    summary = {
        "questions": run["questions"],
        "candidates": sum(verdicts.values()),
        "pass": sum(count for key, count in verdicts.items() if key[1] == "PASS"),
        "fail": sum(count for key, count in verdicts.items() if key[1] == "FAIL"),
        "unresolved": sum(count for key, count in verdicts.items() if key[1] == "UNRESOLVED"),
        "blocked_only_by_page_flag": run["blocked_by_flag_only"],
    }
    print("\nP6 public corpus (property counts, not a measurement on the owner's document):")
    print("  verdict by question type:")
    for key in sorted(verdicts):
        print(f"    {key[0]} -> {key[1]}: {verdicts[key]}")
    print("  page quality of the candidates' units: " + json.dumps(dict(sorted(run["page_quality"].items()))))
    print("  check results (name, status): count")
    for key in sorted(run["checks"]):
        print(f"    {key[0]} {key[1]}: {run['checks'][key]}")
    print("  summary: " + json.dumps(summary, sort_keys=True))
    assert summary["candidates"] == summary["pass"] + summary["fail"] + summary["unresolved"]

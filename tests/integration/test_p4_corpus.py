"""P4 on the public QA corpus (data/corpus/public): BM25 candidates on real text (ARCHITECTURE §13).

These are property checks, not gold results. No expected answer is written here. The PDFs are git-ignored,
so a fresh clone skips these tests and says why. Recall is measured as follows: for a sampled unit, does a
six-word window of that unit's own index text bring the unit back among the first K candidates, either as a
candidate or as a recorded duplicate? The numbers are reported. They are not used to tune any threshold, and
they are not a measurement on the owner's document (B1, B3).

Run: pytest tests/integration/test_p4_corpus.py -q -s
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.document_structure import build_structure
from app.ingestion.extract import extract_document
from app.retrieval import search
from app.storage import Store

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = REPO_ROOT / "data" / "corpus" / "public"
DOCUMENTS = json.loads((CORPUS_DIR / "manifest.json").read_text(encoding="utf-8"))["documents"]
CREATED = "2026-01-01T00:00:00Z"
WINDOW_WORDS = 6
SAMPLE_PER_DOCUMENT = 60
ISOLATION_QUERIES = 12

pytestmark = pytest.mark.public_corpus


def _present(entry: dict) -> Path:
    path = CORPUS_DIR / entry["file"]
    if not path.is_file():
        pytest.skip(f"{entry['file']} is not in data/corpus/public (git-ignored); re-fetch it from {entry['source_url']}")
    return path


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    workdir = tmp_path_factory.mktemp("p4-corpus")
    combined = Store.open(workdir / "combined.sqlite")
    documents = {}
    for entry in DOCUMENTS:
        path = _present(entry)
        extracted = extract_document(path, out_root=workdir / "p1")
        structure = build_structure(extracted, path)
        combined.write_document(extracted, structure, created_at=CREATED)
        documents[entry["file"]] = (extracted, structure)
    yield combined, documents
    combined.close()


def _sample(structure) -> list[tuple[str, str]]:
    """Evenly spaced body units (not derived rows, whose index text is generated), each with a six-word window."""
    eligible = sorted(
        (
            unit
            for unit in structure.units
            if unit.body_retrieval and not unit.derived and len(unit.index_text.split()) >= WINDOW_WORDS + 2
        ),
        key=lambda unit: unit.evidence_id,
    )
    step = max(1, len(eligible) // SAMPLE_PER_DOCUMENT)
    windows = []
    for unit in eligible[::step][:SAMPLE_PER_DOCUMENT]:
        words = unit.index_text.split()
        start = (len(words) - WINDOW_WORDS) // 2
        windows.append((unit.evidence_id, " ".join(words[start : start + WINDOW_WORDS])))
    return windows


def _reached(result) -> set[str]:
    """Candidates and the copies recorded under them, so that a removed duplicate still counts as found."""
    reached: set[str] = set()
    for candidate in result.candidates:
        reached.add(candidate.evidence_id)
        reached.update(candidate.duplicate_evidence_ids)
    return reached


def test_each_public_document_is_searched_only_within_itself(corpus):
    combined, documents = corpus
    for name, (extracted, structure) in documents.items():
        for _, query in _sample(structure)[:ISOLATION_QUERIES]:
            for candidate in search(combined, extracted.document_id, query).candidates:
                assert candidate.evidence_id.startswith(extracted.document_id + ":"), (name, query)


def test_a_document_scores_the_same_alone_and_next_to_the_others(corpus):
    combined, documents = corpus
    for name, (extracted, structure) in documents.items():
        alone = Store.open(":memory:")
        try:
            alone.write_document(extracted, structure, created_at=CREATED)
            for _, query in _sample(structure)[:ISOLATION_QUERIES]:
                assert search(alone, extracted.document_id, query) == search(
                    combined, extracted.document_id, query
                ), (name, query)
        finally:
            alone.close()


def test_the_same_question_gives_the_same_result_on_the_corpus(corpus):
    combined, documents = corpus
    for _, (extracted, structure) in documents.items():
        for _, query in _sample(structure)[:ISOLATION_QUERIES]:
            assert search(combined, extracted.document_id, query) == search(combined, extracted.document_id, query)


def test_a_window_of_a_unit_is_measured_against_its_unit_within_k(corpus, capsys):
    """Recall is measured and reported. It is not gated: a miss is a result to record, and P9a sets K.

    The candidate list for K = 10 is the first ten entries of the list for K = 50, because the ranking
    does not depend on K. So one search per window gives both figures.
    """
    combined, documents = corpus
    report = {}
    for name, (extracted, structure) in documents.items():
        windows = _sample(structure)
        found_at_50 = found_at_10 = 0
        misses: list[str] = []
        for evidence_id, query in windows:
            result = search(combined, extracted.document_id, query, k=50, context_window=0)
            if evidence_id in _reached(result):
                found_at_50 += 1
            else:
                misses.append(evidence_id)
            top_ten = replace(result, candidates=result.candidates[:10])
            if evidence_id in _reached(top_ten):
                found_at_10 += 1
        report[name] = {
            "windows": len(windows),
            "found_within_10": found_at_10,
            "found_within_50": found_at_50,
            "misses_within_50": misses,
        }
    with capsys.disabled():
        print("\nP4 corpus recall (property check, no gold answers, not gated):")
        for name, figures in report.items():
            print(
                f"  {name}: {figures['found_within_50']} of {figures['windows']} within K=50, "
                f"{figures['found_within_10']} within K=10; misses within K=50: {figures['misses_within_50']}"
            )
    for name, figures in report.items():
        assert figures["windows"] > 0, name
        assert figures["found_within_50"] + len(figures["misses_within_50"]) == figures["windows"], name
        assert figures["found_within_10"] <= figures["found_within_50"], name

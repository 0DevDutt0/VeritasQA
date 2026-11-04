"""P3 on the public QA corpus (data/corpus/public): round trip, FTS coverage and search on real documents.

These are property checks. No expected answer is written here, because no human has verified one. The
PDFs are git-ignored, so a fresh clone skips these tests and says why. All three documents go into one
store, so the isolation checks run on real text.

Run: pytest tests/integration/test_p3_corpus.py -q
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.document_structure import build_structure
from app.document_structure.models import ContentType
from app.ingestion.extract import extract_document
from app.retrieval import find_phrase
from app.storage import Store
from tests.fixtures.store_checks import brute_force_phrase, row_counts
from tests.fixtures.structure_checks import check_invariants

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = REPO_ROOT / "data" / "corpus" / "public"
DOCUMENTS = json.loads((CORPUS_DIR / "manifest.json").read_text(encoding="utf-8"))["documents"]
CREATED = "2026-01-01T00:00:00Z"

pytestmark = pytest.mark.public_corpus


def _present(entry: dict) -> Path:
    path = CORPUS_DIR / entry["file"]
    if not path.is_file():
        pytest.skip(f"{entry['file']} is not in data/corpus/public (git-ignored); re-fetch it from {entry['source_url']}")
    return path


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    workdir = tmp_path_factory.mktemp("p3-corpus")
    store = Store.open(workdir / "corpus.sqlite")
    documents = {}
    for entry in DOCUMENTS:
        path = _present(entry)
        extracted = extract_document(path, out_root=workdir / "p1")
        structure = build_structure(extracted, path)
        store.write_document(extracted, structure, created_at=CREATED)
        documents[entry["file"]] = (extracted, structure)
    yield store, documents
    store.close()


def test_every_corpus_document_reads_back_equal_and_passes_the_p2_invariants(corpus):
    store, documents = corpus
    for name, (extracted, structure) in documents.items():
        loaded = store.load_structure(extracted.document_id)
        assert loaded == structure, f"{name}: the structure changed on the way through the store"
        check_invariants(extracted, loaded)


def test_every_body_unit_is_indexed_exactly_once(corpus):
    store, documents = corpus
    for name, (extracted, structure) in documents.items():
        body = [unit for unit in structure.units if unit.body_retrieval]
        indexed = store._conn.execute(
            "SELECT COUNT(*) FROM evidence_fts WHERE document_id = ?", (extracted.document_id,)
        ).fetchone()[0]
        distinct = store._conn.execute(
            "SELECT COUNT(DISTINCT evidence_id) FROM evidence_fts WHERE document_id = ?", (extracted.document_id,)
        ).fetchone()[0]
        assert indexed == distinct == len(body), name


def _sampled_phrases(structure, count=10):
    paragraphs = [
        unit
        for unit in structure.units
        if unit.body_retrieval and unit.content_type == ContentType.PARAGRAPH and len(unit.raw_text.split()) >= 5
    ]
    if not paragraphs:
        return []
    step = max(1, len(paragraphs) // count)
    return [" ".join(unit.raw_text.split()[:5]) for unit in paragraphs[::step][:count]]


def test_the_candidate_step_agrees_with_brute_force_on_sampled_phrases(corpus):
    store, documents = corpus
    for name, (extracted, structure) in documents.items():
        phrases = _sampled_phrases(structure)
        assert phrases, f"{name}: no paragraphs to sample"
        for phrase in phrases:
            found = sorted(unit.evidence_id for unit in find_phrase(store, extracted.document_id, phrase))
            assert found == brute_force_phrase(store, extracted.document_id, phrase), (name, phrase)


def test_results_never_cross_documents(corpus):
    store, documents = corpus
    names = list(documents)
    source_doc, source_structure = documents[names[0]]
    other_doc, _ = documents[names[1]]
    for phrase in _sampled_phrases(source_structure, count=4):
        for unit in find_phrase(store, other_doc.document_id, phrase):
            assert unit.document_id == other_doc.document_id
        for unit in find_phrase(store, source_doc.document_id, phrase):
            assert unit.document_id == source_doc.document_id


def test_hostile_queries_leave_the_corpus_store_unchanged(corpus):
    store, documents = corpus
    before = row_counts(store)
    for phrase in ["risk AND assessment", "NEAR(a b)", "-risk", "risk*", "'); DROP TABLE evidence_units; --"]:
        for extracted, _ in documents.values():
            assert isinstance(find_phrase(store, extracted.document_id, phrase), list)
    assert row_counts(store) == before

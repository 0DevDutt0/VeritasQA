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

from app.common.text import normalize_text
from app.document_structure import build_structure
from app.document_structure.models import ContentType
from app.ingestion.extract import extract_document
from app.retrieval import find_phrase, span_matches
from app.retrieval.query import build_phrase_query
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


def _windows(normalized: str) -> list[str]:
    """Whitespace-delimited windows of one normalized span: its first two words, its last two, and a middle three."""
    words = normalized.split(" ")
    picks = {" ".join(words[:2]), " ".join(words[-2:])}
    if len(words) >= 5:
        middle = len(words) // 2
        picks.add(" ".join(words[middle - 1 : middle + 2]))
    return sorted(pick for pick in picks if any(character.isalnum() for character in pick))


def test_a_window_of_each_sampled_unit_finds_that_unit(corpus):
    """Recall on real text: a window cut from a unit's own normalized span must find that unit.

    The sample covers every body content type, and every span of table rows and cells, where the index text
    differs from the verbatim text. Windows are cut from the normalized span, so a line-end hyphen cannot
    make the test fail by itself. A derived row is checked only for the windows its generated index text
    states (the exact check on ``index_text``): P2 leaves some values and cell-crossing phrases out of that
    text, which is a documented limit (ARCHITECTURE §12, open question Q12), and the cell units still find
    those values.
    """
    store, documents = corpus
    checked: dict[str, int] = {}
    excluded: dict[str, int] = {}
    for name, (extracted, structure) in documents.items():
        texts = store.page_texts(extracted.document_id, {unit.pdf_page for unit in structure.units})
        by_type: dict[ContentType, list] = {}
        for unit in structure.units:
            if unit.body_retrieval:
                by_type.setdefault(unit.content_type, []).append(unit)
        for content_type, units in by_type.items():
            for unit in units[:: max(1, len(units) // 8)][:8]:
                page_text = texts[unit.pdf_page]
                for start, end in unit.source_spans:
                    for window in _windows(normalize_text(page_text[start:end])):
                        if unit.derived and not span_matches(unit.index_text, build_phrase_query(window)):
                            # A derived row is found only through the text its generated index states (ARCHITECTURE §12).
                            excluded[content_type.value] = excluded.get(content_type.value, 0) + 1
                            continue
                        hits = [hit.evidence_id for hit in find_phrase(store, extracted.document_id, window)]
                        assert unit.evidence_id in hits, (name, content_type.value, unit.evidence_id, window)
                        checked[content_type.value] = checked.get(content_type.value, 0) + 1
    for required in ("heading", "paragraph", "table_cell", "table_row"):
        assert checked.get(required, 0) > 0, f"the sample must include {required} units"
    assert set(excluded) <= {"table_row"}, "only derived rows may be excluded, and only for the documented P2 limit"


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

"""P3 exit criteria (storage and exact retrieval, end to end): synthetic PDFs through P1, P2 and the store.

Every PDF is generated at test time and labelled synthetic. The structure is checked with P2's property
checks after it has been read back from the store. Run:
pytest tests/integration/test_p3_retrieval.py -q
"""

from __future__ import annotations

import fitz
import pytest

from app.document_structure import build_structure
from app.document_structure.models import ContentType
from app.ingestion.extract import extract_document
from app.ingestion.models import QualityStatus
from app.retrieval import find_phrase
from app.storage import Store
from tests.fixtures import structure_pdfs as fixtures
from tests.fixtures import synthetic_pdfs as pdfs
from tests.fixtures.store_checks import brute_force_phrase, row_counts
from tests.fixtures.structure_checks import check_invariants

CREATED = "2026-01-01T00:00:00Z"
HOSTILE = [
    "risk AND assessment",
    "NEAR(a b)",
    "-risk",
    "risk*",
    "a:b",
    "^x",
    "(risk)",
    '"risk',
    "'); DROP TABLE evidence_units; --",
    "index_text : secret",
]


def _twin(source, target):
    """The same pages with different metadata: a different file hash, so a different document_id."""
    document = fitz.open(source)
    document.set_metadata({"title": "Synthetic twin of the structure fixture"})
    document.save(target)
    document.close()
    return target


@pytest.fixture(scope="module")
def stored(tmp_path_factory):
    workdir = tmp_path_factory.mktemp("p3-retrieval")
    structure_path = fixtures.structure_pdf(workdir / "structure.pdf")
    twin_path = _twin(structure_path, workdir / "twin.pdf")
    hidden_path = pdfs.hidden_only_pdf(workdir / "hidden.pdf")
    store = Store.open(workdir / "store.sqlite")
    documents = {}
    for name, path in (("structure", structure_path), ("twin", twin_path), ("hidden", hidden_path)):
        extracted = extract_document(path, out_root=workdir / "p1")
        structure = build_structure(extracted, path)
        store.write_document(extracted, structure, created_at=CREATED)
        documents[name] = (extracted, structure)
    yield store, documents
    store.close()


def _quote(store, document_id, unit):
    """The quotation of a single-span unit: a slice of the page's stored raw text."""
    (start, end), = unit.source_spans
    return store.page_texts(document_id, [unit.pdf_page])[unit.pdf_page][start:end]


def test_every_structure_reads_back_equal_and_passes_the_p2_invariants(stored):
    store, documents = stored
    for name, (extracted, structure) in documents.items():
        loaded = store.load_structure(extracted.document_id)
        assert loaded == structure, f"{name}: the structure changed on the way through the store"
        check_invariants(extracted, loaded)


def test_a_paragraph_is_found_by_its_opening_words_and_quoted_verbatim(stored):
    store, documents = stored
    extracted, structure = documents["structure"]
    paragraph = next(
        unit for unit in structure.units
        if unit.raw_text == "The purpose of the method is to find and rank risks before they cause harm."
    )
    hits = find_phrase(store, extracted.document_id, "The purpose of the method")
    assert paragraph.evidence_id in [unit.evidence_id for unit in hits]
    hit = next(unit for unit in hits if unit.evidence_id == paragraph.evidence_id)
    assert _quote(store, extracted.document_id, hit) == hit.raw_text == paragraph.raw_text


def test_a_heading_is_found_by_its_own_text(stored):
    store, documents = stored
    extracted, _ = documents["structure"]
    hits = find_phrase(store, extracted.document_id, "Risk Assessment Guide Overview")
    assert [unit.content_type for unit in hits] == [ContentType.HEADING]


def test_a_table_cell_and_its_row_are_found_with_their_source_text(stored):
    store, documents = stored
    extracted, _ = documents["structure"]
    hits = find_phrase(store, extracted.document_id, "Rare")
    cells = [unit for unit in hits if unit.content_type == ContentType.TABLE_CELL]
    rows = [unit for unit in hits if unit.content_type == ContentType.TABLE_ROW]
    assert [cell.raw_text for cell in cells] == ["Rare"]
    assert cells[0].col_header == "Meaning" and cells[0].row_header == "Low"
    assert len(rows) == 1 and rows[0].derived is True


def test_the_hidden_text_page_is_indexed_and_returned_as_unverified(stored):
    store, documents = stored
    extracted, _ = documents["hidden"]
    hits = find_phrase(store, extracted.document_id, "Invisible words only")
    assert hits, "the page's text is body text, so it must be a candidate"
    assert all(unit.extraction_quality is QualityStatus.UNVERIFIED for unit in hits)


def test_a_phrase_found_in_two_identical_documents_is_returned_for_each_separately(stored):
    store, documents = stored
    phrase = "purpose of the method"
    first, _ = documents["structure"]
    second, _ = documents["twin"]
    assert first.document_id != second.document_id
    a = find_phrase(store, first.document_id, phrase)
    b = find_phrase(store, second.document_id, phrase)
    assert a and b
    assert {unit.document_id for unit in a} == {first.document_id}
    assert {unit.document_id for unit in b} == {second.document_id}
    assert [(unit.pdf_page, unit.ordinal) for unit in a] == [(unit.pdf_page, unit.ordinal) for unit in b]


@pytest.mark.parametrize("phrase", HOSTILE)
def test_hostile_queries_leave_the_real_store_unchanged(stored, phrase):
    store, documents = stored
    before = row_counts(store)
    for extracted, _ in documents.values():
        assert isinstance(find_phrase(store, extracted.document_id, phrase), list)
    assert row_counts(store) == before


@pytest.mark.parametrize("name", ["structure", "twin"])
def test_the_candidate_step_agrees_with_brute_force_on_a_real_structure(stored, name):
    store, documents = stored
    extracted, structure = documents[name]
    words = []
    for unit in structure.units:
        if unit.body_retrieval and unit.content_type == ContentType.PARAGRAPH:
            tokens = unit.raw_text.split()
            if len(tokens) >= 3:
                words.append(" ".join(tokens[:3]))
    assert words, "the fixture must have paragraphs to sample"
    for phrase in words[:8] + ["risk", "Low", "1"]:
        assert sorted(unit.evidence_id for unit in find_phrase(store, extracted.document_id, phrase)) == (
            brute_force_phrase(store, extracted.document_id, phrase)
        ), phrase

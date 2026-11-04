"""P4 end to end on synthetic PDFs: PDF -> P1 -> P2 -> store -> BM25 candidates (ARCHITECTURE §13).

Every PDF is generated at test time and labelled synthetic. Nothing here is a result about the owner's document.
Run: pytest tests/integration/test_p4_retrieval.py -q
"""

from __future__ import annotations

import pytest

from app.document_structure import build_structure
from app.document_structure.models import ContentType
from app.ingestion.extract import extract_document
from app.retrieval import search
from app.storage import Store
from tests.fixtures import structure_pdfs as fixtures
from tests.fixtures import synthetic_pdfs as pdfs

CREATED = "2026-01-01T00:00:00Z"
PARAGRAPH_PHRASE = "structured method for assessing risk"


@pytest.fixture(scope="module")
def stored(tmp_path_factory):
    workdir = tmp_path_factory.mktemp("p4-retrieval")
    store = Store.open(workdir / "store.sqlite")
    documents = {}
    sources = (
        ("structure", fixtures.structure_pdf(workdir / "structure.pdf")),
        ("hidden", pdfs.hidden_only_pdf(workdir / "hidden.pdf")),
    )
    for name, path in sources:
        extracted = extract_document(path, out_root=workdir / "p1")
        structure = build_structure(extracted, path)
        store.write_document(extracted, structure, created_at=CREATED)
        documents[name] = (extracted, structure)
    yield store, documents
    store.close()


def _units(structure):
    return {unit.evidence_id: unit for unit in structure.units}


def test_a_phrase_from_a_paragraph_ranks_its_unit_first_and_its_copy_is_recorded(stored):
    store, documents = stored
    extracted, structure = documents["structure"]
    result = search(store, extracted.document_id, PARAGRAPH_PHRASE, context_window=0)
    top = result.candidates[0]
    unit = _units(structure)[top.evidence_id]
    assert PARAGRAPH_PHRASE in " ".join(unit.raw_text.split())
    assert unit.content_type == ContentType.PARAGRAPH
    # The same paragraph appears on page 2. The copy is recorded under the kept candidate, not dropped.
    copies = [
        other.evidence_id
        for other in structure.units
        if PARAGRAPH_PHRASE in " ".join(other.raw_text.split()) and other.evidence_id != top.evidence_id
    ]
    assert copies, "the synthetic PDF repeats the paragraph on page 2"
    assert set(copies) <= set(top.duplicate_evidence_ids)


def test_the_running_header_and_footers_are_never_candidates(stored):
    store, documents = stored
    extracted, structure = documents["structure"]
    by_id = _units(structure)
    for query in ("Risk Assessment Guide", "guide", "page"):
        for candidate in search(store, extracted.document_id, query, context_window=0).candidates:
            assert by_id[candidate.evidence_id].content_type not in (ContentType.HEADER, ContentType.FOOTER)


def test_table_rows_are_flagged_as_derived_and_cells_are_not(stored):
    store, documents = stored
    extracted, structure = documents["structure"]
    by_id = _units(structure)
    candidates = search(store, extracted.document_id, "Likely", context_window=0).candidates
    assert candidates, "the table holds the word Likely"
    for candidate in candidates:
        unit = by_id[candidate.evidence_id]
        assert candidate.derived == unit.derived
        if unit.content_type == ContentType.TABLE_ROW:
            assert candidate.derived, "a generated table row is flagged, so that it is never quoted"


def test_each_candidate_carries_the_quality_its_unit_was_stored_with(stored):
    store, documents = stored
    extracted, structure = documents["structure"]
    by_id = _units(structure)
    candidates = search(store, extracted.document_id, "scope purpose method", context_window=0).candidates
    assert candidates
    for candidate in candidates:
        assert candidate.extraction_quality == by_id[candidate.evidence_id].extraction_quality.value
    # The page with the ruled table is a WARNING page (D25), so its units are flagged warning, not verified.
    assert {candidate.extraction_quality for candidate in candidates} <= {"verified", "warning"}
    assert any(candidate.extraction_quality == "verified" for candidate in candidates)


def test_a_unit_from_an_unverified_page_is_returned_with_its_flag_not_filtered(stored):
    store, documents = stored
    extracted, structure = documents["hidden"]
    candidates = search(store, extracted.document_id, "invisible", context_window=0).candidates
    assert candidates, "abstention needs unverified text to be visible to the later checks"
    by_id = _units(structure)
    assert {candidate.extraction_quality for candidate in candidates} == {"unverified"}
    assert all(by_id[candidate.evidence_id].extraction_quality.value == "unverified" for candidate in candidates)


def test_each_document_is_searched_on_its_own(stored):
    store, documents = stored
    structure_id = documents["structure"][0].document_id
    hidden_id = documents["hidden"][0].document_id
    assert all(
        candidate.evidence_id.startswith(structure_id + ":")
        for candidate in search(store, structure_id, "guide").candidates
    )
    assert search(store, structure_id, "invisible").candidates == ()
    assert all(
        candidate.evidence_id.startswith(hidden_id + ":")
        for candidate in search(store, hidden_id, "invisible").candidates
    )


def test_the_same_pdf_in_a_new_store_gives_the_same_result(stored, tmp_path):
    store, documents = stored
    extracted, structure = documents["structure"]
    fresh = Store.open(tmp_path / "fresh.sqlite")
    try:
        fresh.write_document(extracted, structure, created_at=CREATED)
        for query in (PARAGRAPH_PHRASE, "Likely", "Risk Assessment Guide"):
            assert search(store, extracted.document_id, query) == search(fresh, extracted.document_id, query), query
    finally:
        fresh.close()

"""P4 context: the body units around a candidate and the headings of its sections (D42, ARCHITECTURE §13).

Context is never a candidate, never replaces one, and never includes header or footer units.
"""

from __future__ import annotations

import pytest

from app.document_structure.models import ContentType
from app.retrieval import search
from app.storage import Store
from tests.fixtures.retrieval_docs import Item, SectionSpec, build

DOC = "doc-" + "c" * 16
CREATED = "2026-01-01T00:00:00Z"


@pytest.fixture(scope="module")
def store_and_structure():
    items = [
        Item(page=1, text="Alpha paragraph before the target."),
        Item(page=1, text="Target threshold paragraph."),
        Item(page=1, text="Page furniture footer", content_type=ContentType.FOOTER, body=False),
        Item(page=1, text="Beta paragraph after the target."),
        Item(page=2, text="Gamma paragraph on page two.", section="s2"),
        Item(page=2, text="Delta paragraph on page two."),
    ]
    sections = [SectionSpec("s1", "Section One"), SectionSpec("s2", "Section Two", parent="s1")]
    extracted, structure = build(DOC, items, sections)
    store = Store.open(":memory:")
    store.write_document(extracted, structure, created_at=CREATED)
    yield store, structure
    store.close()


def _unit(structure, fragment: str):
    matches = [unit for unit in structure.units if fragment in unit.raw_text]
    assert len(matches) == 1
    return matches[0]


def _body_in_reading_order(structure):
    body = [unit for unit in structure.units if unit.body_retrieval]
    return sorted(body, key=lambda unit: (unit.pdf_page, unit.ordinal))


def test_neighbours_are_body_units_in_reading_order_and_furniture_is_skipped(store_and_structure):
    store, structure = store_and_structure
    target = _unit(structure, "Target threshold")
    result = search(store, DOC, "threshold", context_window=2)
    (candidate,) = result.candidates
    assert candidate.evidence_id == target.evidence_id
    body = _body_in_reading_order(structure)
    position = [unit.evidence_id for unit in body].index(target.evidence_id)
    assert candidate.context.before == tuple(unit.evidence_id for unit in body[max(0, position - 2) : position])
    assert candidate.context.after == tuple(unit.evidence_id for unit in body[position + 1 : position + 3])
    footer = _unit(structure, "Page furniture footer")
    assert footer.evidence_id not in candidate.context.before + candidate.context.after


def test_neighbours_cross_the_page_boundary(store_and_structure):
    store, structure = store_and_structure
    gamma = _unit(structure, "Gamma paragraph")
    beta = _unit(structure, "Beta paragraph")
    result = search(store, DOC, "gamma", context_window=3)
    (candidate,) = result.candidates
    assert candidate.evidence_id == gamma.evidence_id
    assert beta.evidence_id in candidate.context.before, "the unit before a page break is context too"
    assert candidate.context.before[-1] == beta.evidence_id


def test_the_section_and_parent_headings_are_attached(store_and_structure):
    store, structure = store_and_structure
    sections = {section.title: section for section in structure.sections}
    result = search(store, DOC, "gamma", context_window=0)
    (candidate,) = result.candidates
    assert candidate.context.section_heading_id == sections["Section Two"].heading_id
    assert candidate.context.parent_heading_id == sections["Section One"].heading_id


def test_a_heading_is_not_its_own_context(store_and_structure):
    store, structure = store_and_structure
    heading = next(section for section in structure.sections if section.title == "Section One").heading_id
    result = search(store, DOC, "section", context_window=0)
    found = next(candidate for candidate in result.candidates if candidate.evidence_id == heading)
    assert found.context.section_heading_id is None
    assert found.context.parent_heading_id is None


def test_context_is_never_a_candidate_and_never_replaces_one(store_and_structure):
    store, structure = store_and_structure
    target = _unit(structure, "Target threshold")
    result = search(store, DOC, "threshold", k=1, context_window=2)
    assert [candidate.evidence_id for candidate in result.candidates] == [target.evidence_id]
    assert result.candidates[0].context.before and result.candidates[0].context.after


def test_a_window_of_zero_gives_no_neighbours_but_keeps_the_headings(store_and_structure):
    store, structure = store_and_structure
    result = search(store, DOC, "gamma", context_window=0)
    (candidate,) = result.candidates
    assert candidate.context.before == () and candidate.context.after == ()
    assert candidate.context.section_heading_id is not None


def test_no_footer_appears_in_any_context(store_and_structure):
    store, structure = store_and_structure
    footer = _unit(structure, "Page furniture footer").evidence_id
    for candidate in search(store, DOC, "paragraph", context_window=3).candidates:
        assert footer not in candidate.context.before + candidate.context.after

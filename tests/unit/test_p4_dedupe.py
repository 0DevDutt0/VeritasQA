"""P4 duplicate removal: text with the same normalized form is kept once, and every removed copy is recorded.

A removed copy is never dropped silently. It is listed under the kept candidate, and it is counted in the trace
(ARCHITECTURE §13).
"""

from __future__ import annotations

from app.retrieval import search
from app.storage import Store
from tests.fixtures.retrieval_docs import Item, build, filler

DOC = "doc-" + "d" * 16
CREATED = "2026-01-01T00:00:00Z"


def _store() -> tuple[Store, object]:
    items = filler(20, page=1)
    items += [
        Item(page=1, text="Repeated clause about the threshold."),
        Item(page=2, text="Repeated clause about the threshold."),
        Item(page=2, text="Repeated  clause about the threshold."),  # two spaces: the same normalized text
        Item(page=2, text="Repeated clause about the threshold."),  # no-break space: the same normalized text
        Item(page=2, text="repeated clause about the threshold."),  # other case: a different text
    ]
    items += filler(20, page=2)
    extracted, structure = build(DOC, items)
    store = Store.open(":memory:")
    store.write_document(extracted, structure, created_at=CREATED)
    return store, structure


def _ids_with_text(structure, text: str) -> list[str]:
    return [unit.evidence_id for unit in structure.units if unit.raw_text == text]


def test_copies_with_the_same_normalized_text_are_kept_once_and_the_copies_are_recorded():
    store, structure = _store()
    try:
        result = search(store, DOC, "threshold", context_window=0)
        identical = _ids_with_text(structure, "Repeated clause about the threshold.")
        spaced = _ids_with_text(structure, "Repeated  clause about the threshold.")
        no_break = _ids_with_text(structure, "Repeated clause about the threshold.")
        group = sorted(identical + spaced + no_break)
        kept = [candidate for candidate in result.candidates if candidate.evidence_id in group]
        assert len(kept) == 1, "the normalized copies must collapse to one candidate"
        assert kept[0].evidence_id == group[0], "the first copy in rank order keeps its place"
        assert sorted(kept[0].duplicate_evidence_ids) == group[1:]
        # Four units share the normalized text (two identical copies, one double-space and one no-break-space copy).
        assert len(group) == 4
        assert result.trace.duplicates_removed == len(group) - 1
    finally:
        store.close()


def test_a_copy_that_differs_in_case_is_not_a_duplicate():
    store, structure = _store()
    try:
        result = search(store, DOC, "threshold", context_window=0)
        lowercase = _ids_with_text(structure, "repeated clause about the threshold.")
        assert [candidate.evidence_id for candidate in result.candidates if candidate.evidence_id in lowercase] == lowercase
        assert all(not candidate.duplicate_evidence_ids for candidate in result.candidates if candidate.evidence_id in lowercase)
    finally:
        store.close()


def test_every_matching_unit_is_either_a_candidate_or_recorded_as_a_duplicate():
    store, structure = _store()
    try:
        result = search(store, DOC, "threshold", context_window=0)
        reached = set()
        for candidate in result.candidates:
            reached.add(candidate.evidence_id)
            reached.update(candidate.duplicate_evidence_ids)
        expected = {unit.evidence_id for unit in structure.units if "threshold" in unit.index_text.lower()}
        assert reached == expected
    finally:
        store.close()


def test_a_copy_beyond_k_is_still_recorded_under_its_kept_unit():
    store, structure = _store()
    try:
        result = search(store, DOC, "threshold", k=1, context_window=0)
        assert len(result.candidates) == 1
        kept = result.candidates[0]
        group = sorted(
            _ids_with_text(structure, "Repeated clause about the threshold.")
            + _ids_with_text(structure, "Repeated  clause about the threshold.")
            + _ids_with_text(structure, "Repeated clause about the threshold.")
        )
        assert kept.evidence_id == group[0]
        assert sorted(kept.duplicate_evidence_ids) == group[1:]
        assert result.trace.duplicates_removed == len(group) - 1
        assert result.trace.truncated_original == 1, "the other-case copy is kept as a hit but cut by k"
    finally:
        store.close()

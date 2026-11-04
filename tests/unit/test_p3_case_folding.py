"""P3 case folding: the exact check folds a character only where the FTS5 index folds it (ARCHITECTURE §12).

The pairs cover Latin, Greek, Cyrillic, Armenian, Georgian (Mkhedruli and Mtavruli), Cherokee and Deseret (outside
the BMP). For each pair, a document holds one form and the query uses the other, in both directions. Two checks:

1. The candidate step returns whatever the exact check accepts, and agrees with the brute-force reference.
2. The exact check folds a pair exactly when the index does (``index_foldable_characters``). For the pairs this
   SQLite build does not fold (Georgian Mtavruli, Cherokee), the exact check rejects the cross-case match, so
   neither path returns it.
"""

from __future__ import annotations

import pytest

from app.common.text import normalize_text
from app.document_structure.models import ContentType, DocumentStructure
from app.retrieval import find_phrase, span_matches
from app.retrieval.phrase import index_foldable_characters
from app.retrieval.query import build_phrase_query
from app.storage import Store
from tests.fixtures.store_checks import brute_force_phrase
from tests.fixtures.store_records import make_extracted, make_page, make_unit

PAIRS = [
    ("é", "É", "Latin-1"),
    ("ÿ", "Ÿ", "Latin-1 and Extended-A"),
    ("ł", "Ł", "Latin Extended-A"),
    ("ß", "ẞ", "German sharp s, capital U+1E9E"),
    ("ḃ", "Ḃ", "Latin Extended Additional"),
    ("ǆ", "Ǆ", "digraph DŽ, capital U+01C4"),
    ("σ", "Σ", "Greek sigma"),
    ("θ", "ϴ", "Greek theta symbol, capital U+03F4"),
    ("ж", "Ж", "Cyrillic"),
    ("ա", "Ա", "Armenian"),
    ("ა", "Ა", "Georgian Mkhedruli, with the Mtavruli capital U+1C90"),
    ("ꭰ", "Ꭰ", "Cherokee"),
    ("𐐨", "𐐀", "Deseret, outside the BMP"),
    ("ς", "Σ", "negative control: the final sigma does not lower to ς"),
    ("i", "İ", "negative control: the capital I with a dot lowers to two characters"),
]


def _document_id(index: int, direction: int) -> str:
    return f"doc-{index * 2 + direction:016x}"


@pytest.fixture(scope="module")
def cased_store(tmp_path_factory):
    store = Store.open(tmp_path_factory.mktemp("p3-case") / "case.sqlite")
    for index, (lower, upper, _) in enumerate(PAIRS):
        for direction, letter in ((0, lower), (1, upper)):
            document_id = _document_id(index, direction)
            text = f"ab{letter}cd"
            extracted = make_extracted(document_id, [make_page(1, text)])
            unit = make_unit(document_id, 1, 1, ContentType.PARAGRAPH, text, [(0, len(text))])
            store.write_document(
                extracted,
                DocumentStructure(document_id=document_id, units=[unit]),
                created_at="2026-01-01T00:00:00Z",
            )
    yield store
    store.close()


PARAMS = [(index, direction) for index in range(len(PAIRS)) for direction in (0, 1)]
IDS = [f"pair{index:02d}-{'lower' if direction == 0 else 'upper'}-in-text" for index, direction in PARAMS]


@pytest.mark.parametrize(("index", "direction"), PARAMS, ids=IDS)
def test_the_candidate_step_agrees_with_the_exact_check_across_case(cased_store, index, direction):
    lower, upper, _ = PAIRS[index]
    own, queried = (lower, upper) if direction == 0 else (upper, lower)
    document_id = _document_id(index, direction)
    text = f"ab{own}cd"
    query = f"ab{queried}cd"
    found = sorted(hit.evidence_id for hit in find_phrase(cased_store, document_id, query))
    assert found == brute_force_phrase(cased_store, document_id, query)
    if span_matches(text, build_phrase_query(query)):
        assert f"{document_id}:p0001:u0001" in found, "the exact check accepts this case, so the search must return it"


@pytest.mark.parametrize("index", range(len(PAIRS)), ids=[f"pair{index:02d}" for index in range(len(PAIRS))])
def test_the_exact_check_folds_a_pair_exactly_where_the_index_does(index):
    lower, upper, _ = PAIRS[index]
    foldable = index_foldable_characters()
    # The exact check compares NFKC-normalized text, so the expectation is computed on the normalized forms.
    upper_normalized, lower_normalized = normalize_text(upper), normalize_text(lower)
    folds = upper_normalized.lower() == lower_normalized and all(
        character in foldable for character in upper_normalized if character.lower() != character
    )
    assert span_matches(f"ab{upper}cd", build_phrase_query(f"ab{lower}cd")) is folds
    assert span_matches(f"ab{lower}cd", build_phrase_query(f"ab{upper}cd")) is folds


def test_the_calibration_is_not_empty_and_covers_the_common_cases():
    foldable = index_foldable_characters()
    assert len(foldable) > 1000
    assert {"É", "Σ", "Ж", "ẞ"} <= foldable

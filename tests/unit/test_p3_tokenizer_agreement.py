"""P3 tokenizer agreement: the FTS5 candidate step must never miss a unit that the exact check accepts.

Each character of the panel sits between ``ab`` and ``cd`` in its own synthetic document, so the result of
every phrase is known. The panel covers the Unicode categories that matter to unicode61 (letters, numbers,
marks, private use, format characters, punctuation, symbols, separators). The reference is the brute-force
exact check, so this test measures the candidate step and nothing else.
"""

from __future__ import annotations

import pytest

from app.document_structure.models import ContentType, DocumentStructure
from app.retrieval import find_phrase
from app.storage import Store
from tests.fixtures.store_checks import brute_force_phrase
from tests.fixtures.store_records import make_extracted, make_page, make_unit

PANEL = [
    "́",  # Mn: combining acute, folded away by unicode61 (a token character for it)
    "̸",  # Mn: combining long solidus overlay, a separator for unicode61
    "̣",  # Mn: combining dot below, composes with the preceding letter under NFKC
    "ऀ",  # Mn: devanagari inverted candrabindu
    "ः",  # Mc: devanagari visarga
    "",  # Co: private use, a token character for unicode61
    "‍",  # Cf: zero width joiner
    "­",  # Cf: soft hyphen, removed by normalization
    "_",  # Pc: connector punctuation
    "-",  # Pd: dash
    "‑",  # Pd: non-breaking hyphen, translated to a plain hyphen
    ".",  # Po
    "’",  # Pf: right single quotation mark, translated to an apostrophe
    "(",  # Ps
    "$",  # Sc
    "+",  # Sm
    "©",  # So: copyright sign
    " ",  # Zs: no-break space, normalized to a space
    "٣",  # Nd: arabic-indic digit three
    "²",  # No: superscript two, normalized to a digit
    "Ⅻ",  # Nl: roman numeral twelve
    "é",  # Ll: precomposed letter
    "ﬁ",  # Ll: ligature fi, normalized to two letters
    "文",  # Lo: CJK ideograph
]


@pytest.fixture(scope="module")
def panel_store(tmp_path_factory):
    store = Store.open(tmp_path_factory.mktemp("p3-panel") / "panel.sqlite")
    for index, character in enumerate(PANEL):
        document_id = f"doc-{index:016x}"
        text = f"ab{character}cd"
        extracted = make_extracted(document_id, [make_page(1, text)])
        unit = make_unit(document_id, 1, 1, ContentType.PARAGRAPH, text, [(0, len(text))])
        structure = DocumentStructure(document_id=document_id, units=[unit])
        store.write_document(extracted, structure, created_at="2026-01-01T00:00:00Z")
    yield store
    store.close()


@pytest.mark.parametrize("index", range(len(PANEL)), ids=[f"U+{ord(c):04X}" for c in PANEL])
def test_the_candidate_step_agrees_with_the_exact_check(panel_store, index):
    character = PANEL[index]
    document_id = f"doc-{index:016x}"
    unit_id = f"{document_id}:p0001:u0001"
    assert unit_id in [unit.evidence_id for unit in find_phrase(panel_store, document_id, f"ab{character}cd")], (
        "a phrase copied from the unit must find the unit"
    )
    for phrase in ("ab", "cd", f"b{character}c"):
        found = sorted(unit.evidence_id for unit in find_phrase(panel_store, document_id, phrase))
        assert found == brute_force_phrase(panel_store, document_id, phrase), repr(phrase)

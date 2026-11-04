"""Exact phrase search: an FTS5 candidate step, then a deterministic check on verbatim text (ARCHITECTURE §12).

FTS5 ignores punctuation and spacing, so ``3.5`` also finds ``3 5`` and ``3 . 5``. The candidates are
therefore checked again against the source text of each span. That check decides whether a unit
matches. The rules are documented in ARCHITECTURE §12 and tested in ``tests/unit/test_p3_phrase_check.py``.
"""

from __future__ import annotations

import unicodedata

from app.common.errors import StorageError
from app.common.text import normalize_text
from app.document_structure.models import EvidenceUnit
from app.retrieval.query import PhraseQuery, build_phrase_query
from app.storage.store import Store


def fold_case(text: str) -> str:
    """Lower-case one character at a time. The length never changes, so positions stay comparable.

    A character whose lower case is more than one character (``'İ'``) is kept as it is.
    """
    folded: list[str] = []
    for character in text:
        lower = character.lower()
        folded.append(lower if len(lower) == 1 else character)
    return "".join(folded)


def _is_word(character: str) -> bool:
    """A character that may belong to a token. The set includes every character unicode61 keeps inside a
    token (letters, numbers, private use, and the marks it folds away), so an exact match never ends in
    the middle of an FTS5 token. Extra characters here only make the check stricter."""
    category = unicodedata.category(character)
    return character.isalnum() or character == "_" or category.startswith("M") or category == "Co"


def _boundary_before(text: str, start: int, first: str) -> bool:
    """The character before a match must not be a word character, whatever the phrase starts with.

    So ``-5`` does not match inside ``3-5``, and ``.5`` does not match inside ``3.5``.
    """
    if start == 0:
        return True
    previous = text[start - 1]
    if _is_word(previous):
        return False
    if first.isdigit() and previous in ".," and start >= 2 and text[start - 2].isdigit():
        return False
    return True


def _boundary_after(text: str, end: int, last: str) -> bool:
    """The character after a match must not be a word character, whatever the phrase ends with.

    So ``U.S.`` does not match inside ``U.S.A``. A numeric edge also rejects a following ``.`` or
    ``,`` that is followed by a digit, so ``3.5`` does not match ``3.5.2``.
    """
    if end >= len(text):
        return True
    following = text[end]
    if _is_word(following):
        return False
    if last.isdigit() and following in ".," and end + 1 < len(text) and text[end + 1].isdigit():
        return False
    return True


def span_matches(span_text: str, query: PhraseQuery) -> bool:
    """True when the normalized span text contains the phrase at token boundaries.

    The span is read as verbatim source text. It is normalized with the index rules, so whitespace,
    no-break spaces, quote and dash variants and case do not matter. Diacritics and punctuation do.
    """
    haystack = fold_case(normalize_text(span_text))
    needle = fold_case(query.normalized)
    position = haystack.find(needle)
    while position != -1:
        end = position + len(needle)
        if _boundary_before(haystack, position, needle[0]) and _boundary_after(haystack, end, needle[-1]):
            return True
        position = haystack.find(needle, position + 1)
    return False


def find_phrase(store: Store, document_id: str, phrase: str) -> list[EvidenceUnit]:
    """Units of one document whose source text contains ``phrase`` under the exact check.

    Results are ordered by ``(pdf_page, ordinal)``. Each unit is returned with its verbatim spans, so a
    caller quotes ``raw_text`` and never ``index_text``. A unit with ``derived = True`` is only a
    candidate: its ``index_text`` is generated and must not be quoted.

    Raises :class:`QueryError` for a phrase with no letter or digit, and :class:`StorageError` for a
    document that is not in the store.
    """
    query = build_phrase_query(phrase)
    if not store.has_document(document_id):
        raise StorageError(f"the store holds no document {document_id}")
    candidates = store.match_units(document_id, query.match)
    if not candidates:
        return []
    texts = store.page_texts(document_id, (unit.pdf_page for unit in candidates))
    hits: list[EvidenceUnit] = []
    for unit in candidates:
        page_text = texts[unit.pdf_page]
        if any(span_matches(page_text[start:end], query) for start, end in unit.source_spans):
            hits.append(unit)
    return hits

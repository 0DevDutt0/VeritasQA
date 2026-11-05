"""Word forms of a question word (ARCHITECTURE §14, P13, D131).

A target word also matches its inflected forms: ``receive`` matches ``received``, ``receives`` and ``receiving``,
and ``received`` matches ``receive``. This is a fixed suffix rule, not a stemmer, and no stemming library is used.
It runs at query time and never changes the index. Each form is checked with the exact check (§12), so token
boundaries apply: ``receives`` does not match inside ``unreceives``.

Numbers, identifiers and words with other characters have no forms. A word shorter than three letters has none.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.document_structure.models import EvidenceUnit
from app.retrieval.phrase import find_phrase, span_matches
from app.retrieval.query import build_phrase_query
from app.storage.store import Store

MIN_LENGTH = 3
VOWELS = frozenset("aeiou")
_ASCII_WORD = re.compile(r"[a-z]+")

# Words that end like an inflection but are not one. No stem is taken from them: "news" is not a plural of "new".
NOT_INFLECTED = frozenset({"feed", "news"})

# Forms that are other English words, so a stem must not produce them (fee -> feed, new -> news). Pinned by
# tests/unit/test_p13_word_forms.py. Other collisions may exist; the development gate measures them.
UNRELATED_FORMS: dict[str, frozenset[str]] = {"fee": frozenset({"feed"}), "new": frozenset({"news"})}


def _doubles_at_end(stem: str) -> bool:
    """True for a stem that ends in consonant, vowel, consonant, the last not w, x or y (stop, visit, open)."""
    return (
        len(stem) >= MIN_LENGTH
        and stem[-1] not in VOWELS
        and stem[-1] not in "wxy"
        and stem[-2] in VOWELS
        and stem[-3] not in VOWELS
    )


def _stems(word: str) -> set[str]:
    """The word itself, and the shorter words that its suffix can leave (received -> receive, applies -> apply)."""
    if word in NOT_INFLECTED:
        return {word}
    stems = {word}
    if word.endswith(("ies", "ied")):
        stems.add(word[:-3] + "y")
    if word.endswith("es"):
        stems.add(word[:-2])
    if word.endswith("s") and not word.endswith("ss"):
        stems.add(word[:-1])
    if word.endswith("ed"):
        stems.add(word[:-2])
        stems.add(word[:-1])
        if len(word) >= 5 and word[-3] == word[-4] and word[-3] not in VOWELS:
            stems.add(word[:-3])
    if word.endswith("ing"):
        stems.add(word[:-3])
        stems.add(word[:-3] + "e")
        if word.endswith("ying"):
            stems.add(word[:-4] + "y")
        if len(word) >= 6 and word[-4] == word[-5] and word[-4] not in VOWELS:
            stems.add(word[:-4])
    return {stem for stem in stems if len(stem) >= MIN_LENGTH}


def _inflections(stem: str) -> set[str]:
    """The plural, past and -ing forms of one stem, with e-drop, y to i, and the doubled consonant."""
    forms = {stem}
    if stem.endswith("y") and stem[-2] not in VOWELS:
        forms.update({stem[:-1] + "ies", stem[:-1] + "ied", stem + "ing"})
    else:
        forms.add(stem + ("es" if stem.endswith(("s", "x", "z", "ch", "sh")) else "s"))
        forms.add(stem + ("d" if stem.endswith("e") else "ed"))
        if stem.endswith("ie"):
            forms.add(stem[:-2] + "ying")
        elif stem.endswith("e") and not stem.endswith(("ee", "oe", "ye")):
            forms.add(stem[:-1] + "ing")
        else:
            forms.add(stem + "ing")
    if _doubles_at_end(stem):
        forms.update({stem + stem[-1] + "ed", stem + stem[-1] + "ing"})
    return forms - UNRELATED_FORMS.get(stem, frozenset())


def word_forms(word: str) -> tuple[str, ...]:
    """The word and its word forms. The word comes first, then the other forms in sorted order.

    A word that is not ASCII letters, or that is shorter than three letters, has no forms: it is returned alone.
    """
    lowered = word.lower()
    if len(word) < MIN_LENGTH or not _ASCII_WORD.fullmatch(lowered):
        return (word,)
    forms: set[str] = set()
    for stem in _stems(lowered):
        forms |= _inflections(stem)
    forms.discard(lowered)
    return (lowered, *sorted(forms))


def all_forms(words: Iterable[str]) -> tuple[str, ...]:
    """The forms of several words, without repeats, in the order of the words."""
    return tuple(dict.fromkeys(form for word in words for form in word_forms(word)))


def span_matches_word(span_text: str, word: str) -> bool:
    """True when the span contains the word or one of its forms, under the exact check (§12)."""
    return any(span_matches(span_text, build_phrase_query(form)) for form in word_forms(word))


def find_word(store: Store, document_id: str, word: str) -> list[EvidenceUnit]:
    """Units of one document that contain the word or one of its forms: the union of ``find_phrase`` per form,
    in ``(pdf_page, ordinal)`` order. Raises what ``find_phrase`` raises."""
    found: dict[str, EvidenceUnit] = {}
    for form in word_forms(word):
        for unit in find_phrase(store, document_id, form):
            found.setdefault(unit.evidence_id, unit)
    return sorted(found.values(), key=lambda unit: (unit.pdf_page, unit.ordinal))

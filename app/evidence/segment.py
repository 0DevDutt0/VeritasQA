"""Sentence boundaries inside one quotable text (D50, ARCHITECTURE §14).

The splitter is deliberately conservative. A full stop after an abbreviation or an initial does not end a
sentence, unless the next word opens a sentence. A line break is whitespace, so a PDF line wrap never ends a
sentence. A boundary needs a capital letter after it, so a lower-case continuation never splits.
"""

from __future__ import annotations

import re

# Abbreviations, lower case, without their full stop. A dotted abbreviation keeps its inner dots (u.s).
_ABBREVIATIONS = frozenset(
    """
    e.g i.e u.s u.k e.u vs etc al cf no nos fig figs eq eqs sec secs sect art arts ch chap p pp vol vols ed eds
    dr mr mrs ms prof st jr sr inc ltd co corp dept govt approx est incl excl ref refs app tab tbl cat misc max
    min avg jan feb mar apr jun jul aug sep sept oct nov dec
    """.split()
)

# Words that open a sentence. After an abbreviation, a full stop ends the sentence only before one of these.
_OPENERS = frozenset(
    """
    the this these those it its in for if when where a an each such all any however therefore thus they we our
    their there also some most both several many only here other once after before during while although because
    unless under upon given who which what note please
    """.split()
)

_PUNCTUATION = re.compile(r"[.?!]+[\"')\]”’]*")
_OPENING = "\"'([“‘"
_WORD_BEFORE = re.compile(r"[A-Za-z][A-Za-z.]*$")
_FIRST_WORD = re.compile(r"[A-Za-z]+")


def _is_one_of(character: str, choices: str) -> bool:
    return character != "" and character in choices


def _is_abbreviation(word: str) -> bool:
    if not word:
        return False
    if word.lower() in _ABBREVIATIONS:
        return True
    return len(word) == 1 and word.isalpha()


def sentence_spans(text: str) -> tuple[tuple[int, int], ...]:
    """Half-open (start, end) offsets of the sentences of ``text``, in order, with the surrounding whitespace
    removed. Empty sentences are never returned."""
    length = len(text)
    cuts: list[tuple[int, int]] = []
    for match in _PUNCTUATION.finditer(text):
        end = match.end()
        if end < length and not text[end].isspace():
            continue
        following = end
        while following < length and text[following].isspace():
            following += 1
        probe = following
        while probe < length and _is_one_of(text[probe], _OPENING):
            probe += 1
        if probe >= length or not text[probe].isupper():
            continue
        punctuation = match.group(0)
        if "." in punctuation:
            word_match = _WORD_BEFORE.search(text[max(0, match.start() - 40) : match.start()])
            word = word_match.group(0) if word_match else ""
            if _is_abbreviation(word):
                next_word = _FIRST_WORD.match(text, probe)
                if next_word is None or next_word.group(0).lower() not in _OPENERS:
                    continue
        cuts.append((end, following))

    spans: list[tuple[int, int]] = []
    start = 0
    for end, next_start in cuts:
        spans.append((start, end))
        start = next_start
    spans.append((start, length))

    trimmed: list[tuple[int, int]] = []
    for first, last in spans:
        while first < last and text[first].isspace():
            first += 1
        while last > first and text[last - 1].isspace():
            last -= 1
        if first < last:
            trimmed.append((first, last))
    return tuple(trimmed)

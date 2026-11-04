"""Reversible text normalization for index text (SPEC §3B, ARCHITECTURE §11).

Index text is a derivative used only for retrieval. ``normalize_with_map`` returns it together with
the raw range of every output character, so any index match resolves to exact raw offsets. Index
normalization can cause a miss, but it cannot create evidence, because verification reads raw text.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

# Quote and dash variants, unified to ASCII in index text only.
_TRANSLATE = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‚": "'",
        "‛": "'",
        "′": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "‟": '"',
        "″": '"',
        "‐": "-",
        "‑": "-",
        "‒": "-",
        "–": "-",
        "—": "-",
        "―": "-",
        "−": "-",
    }
)
# Invisible characters that carry no meaning in index text. The soft hyphen is handled separately,
# because at a line end it marks a hyphenated break.
_INVISIBLE = frozenset({"​", "‎", "‏", "﻿"})
_SOFT_HYPHEN = "­"
_HYPHEN_TAG_CHARS = frozenset({"-", "‐", "‑"})

_TEXT = "text"
_HYPHEN = "hyphen"
_SOFT = "soft"
_NEWLINE = "newline"
_SPACE = "space"


@dataclass(frozen=True)
class NormalizedText:
    """Index text and, for each of its characters, the half-open raw range it came from."""

    text: str
    spans: tuple[tuple[int, int], ...]

    def raw_range(self, start: int, end: int) -> tuple[int, int]:
        """Return the raw range that covers the index characters ``[start, end)``."""
        if not 0 <= start < end <= len(self.text):
            raise ValueError(f"index range [{start}, {end}) is outside the text of length {len(self.text)}")
        window = self.spans[start:end]
        return min(span[0] for span in window), max(span[1] for span in window)


def _clusters(raw: str) -> list[tuple[int, int]]:
    """Split raw text into a base character and the combining marks that follow it."""
    ranges: list[tuple[int, int]] = []
    index = 0
    while index < len(raw):
        end = index + 1
        while end < len(raw) and _is_combining(raw[end]):
            end += 1
        ranges.append((index, end))
        index = end
    return ranges


def _is_combining(char: str) -> bool:
    return unicodedata.combining(char) != 0 or unicodedata.category(char) in {"Mn", "Mc", "Me"}


def normalize_with_map(raw: str) -> NormalizedText:
    """Normalize ``raw`` for indexing and keep the raw range of every output character.

    Pass 1 turns each cluster into tagged characters. Pass 2 removes a line-end hyphen (or soft
    hyphen) that is followed by a newline and a lowercase letter. Pass 3 writes the output, turning
    newlines and other whitespace into single spaces and dropping the spaces at either end.
    """
    tagged: list[tuple[str, int, int, str]] = []
    for start, end in _clusters(raw):
        chunk = raw[start:end]
        if chunk == _SOFT_HYPHEN:
            tagged.append(("", start, end, _SOFT))
            continue
        if chunk in _INVISIBLE:
            continue
        translated = unicodedata.normalize("NFKC", chunk.translate(_TRANSLATE))
        for char in translated:
            if char == "\n":
                tag = _NEWLINE
            elif char.isspace():
                tag = _SPACE
            elif char == "-" and chunk in _HYPHEN_TAG_CHARS:
                tag = _HYPHEN
            else:
                tag = _TEXT
            tagged.append((char, start, end, tag))

    kept: list[tuple[str, int, int, str]] = []
    position = 0
    while position < len(tagged):
        char, start, end, tag = tagged[position]
        if tag in {_HYPHEN, _SOFT} and position + 2 < len(tagged):
            next_char, _, _, next_tag = tagged[position + 1]
            after_char, _, _, after_tag = tagged[position + 2]
            if next_tag == _NEWLINE and after_tag == _TEXT and after_char.islower():
                position += 2
                continue
        kept.append((char, start, end, tag))
        position += 1

    out_chars: list[str] = []
    out_spans: list[tuple[int, int]] = []
    previous_was_space = True
    for char, start, end, tag in kept:
        if tag == _SOFT:
            continue
        if tag in {_NEWLINE, _SPACE}:
            if previous_was_space:
                continue
            out_chars.append(" ")
            out_spans.append((start, end))
            previous_was_space = True
            continue
        out_chars.append(char)
        out_spans.append((start, end))
        previous_was_space = False
    if out_chars and out_chars[-1] == " ":
        out_chars.pop()
        out_spans.pop()
    return NormalizedText(text="".join(out_chars), spans=tuple(out_spans))


def normalize_text(raw: str) -> str:
    """Return only the index text for ``raw``."""
    return normalize_with_map(raw).text

"""The one text rule of the evaluation harness (ARCHITECTURE §17.1, D76).

A quotation, an answer text and a containment test all compare ``normalize(...)``. Any run of whitespace, including a
line break from a line join, becomes one space. Nothing else changes: case, punctuation and every other character are
compared exactly. There is no case folding, stemming or fuzzy matching.
"""

from __future__ import annotations

import re

_WORD = re.compile(r"\w+")


def normalize(text: str) -> str:
    """Collapse every run of whitespace to one space and trim the ends. Nothing else changes."""
    return " ".join(text.split())


def contains(haystack: str, needle: str) -> bool:
    """True when the normalized needle occurs in the normalized haystack. A blank needle never occurs."""
    needle_normalized = normalize(needle)
    return bool(needle_normalized) and needle_normalized in normalize(haystack)


def tokens(text: str) -> list[str]:
    """The word tokens (``\\w+``) of the normalized text, in order. Used by token F1 only."""
    return _WORD.findall(normalize(text))

"""Numeric, date and identifier terms in query text (ARCHITECTURE §13, D43).

The terms are extracted so that P6 can check them against raw text later. The extraction itself decides
nothing: it finds the spans, and each candidate records which of them occur exactly in its raw text.
Overlapping matches are resolved in favour of the earlier pattern: a date beats the numbers inside it,
and a percentage beats its number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class TermKind(StrEnum):
    DATE = "date"
    PERCENT = "percent"
    IDENTIFIER = "identifier"
    NUMBER = "number"


@dataclass(frozen=True)
class Term:
    """A term found in the text. ``start`` and ``end`` are half-open offsets into that text."""

    kind: TermKind
    text: str
    start: int
    end: int


_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"

# Patterns in priority order. Each one takes the spans that no earlier pattern has taken.
_PATTERNS: tuple[tuple[TermKind, re.Pattern[str]], ...] = (
    (TermKind.DATE, re.compile(r"(?<![\w.])\d{4}-\d{2}-\d{2}(?![\w.])")),
    (TermKind.DATE, re.compile(rf"(?<![\w.])\d{{1,2}}\s+(?:{_MONTHS})\s+\d{{4}}(?![\w.])", re.IGNORECASE)),
    (TermKind.DATE, re.compile(rf"(?<![\w.])(?:{_MONTHS})\s+\d{{1,2}},?\s+\d{{4}}(?![\w.])", re.IGNORECASE)),
    (TermKind.PERCENT, re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*\s?%")),
    (
        TermKind.IDENTIFIER,
        re.compile(
            r"(?<![\w-])(?=[A-Za-z0-9_-]*[A-Za-z])(?=[A-Za-z0-9_-]*\d)[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)+(?![\w-])"
        ),
    ),
    (TermKind.NUMBER, re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*(?!\w)")),
)


def extract_terms(text: str) -> tuple[Term, ...]:
    """The numeric, date and identifier terms of ``text``, in order of position."""
    accepted: list[Term] = []
    taken: list[tuple[int, int]] = []
    for kind, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span()
            if any(start < other_end and other_start < end for other_start, other_end in taken):
                continue
            taken.append((start, end))
            accepted.append(Term(kind=kind, text=text[start:end], start=start, end=end))
    return tuple(sorted(accepted, key=lambda term: (term.start, term.end)))

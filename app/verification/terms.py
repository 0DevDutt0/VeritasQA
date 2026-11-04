"""Value occurrence for the value check (ARCHITECTURE §15, D63).

A question value is looked for with the boundaries and the sign rule of D63. This is stricter than the phrase check of
P3, which does not read a minus sign and accepts a number inside a longer one. The text is normalized with the index
rules first, so only the offsets of the normalized text are used, and only as a yes or no answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.common.text import normalize_text

MINUS_SIGNS = frozenset("-−–")


@dataclass(frozen=True)
class Occurrence:
    """One place where a term occurs. ``negative`` is true when a minus sign is attached in front of it."""

    start: int
    end: int
    negative: bool


def _pattern(term: str) -> re.Pattern[str]:
    body = r"\s+".join(re.escape(part) for part in term.split())
    # Before the term: not a letter, digit, underscore or one of . , /. After it: not a letter, digit or underscore,
    # and not . , or / followed by a letter or digit. So 3.5 is not found in 3.5.2 or 13.5, and 2 is not found in 1,2,3.
    return re.compile(rf"(?<![0-9A-Za-z_./,]){body}(?![0-9A-Za-z_]|[./,][0-9A-Za-z])")


def find_occurrences(text: str, term: str) -> tuple[Occurrence, ...]:
    """Every occurrence of ``term`` in ``text`` under the D63 rule, in order.

    The minus sign counts only when it is attached to the term and is not itself after a letter, digit or closing
    bracket. So ``10-15`` has a positive 15, while ``-3.5`` and ``(-3.5)`` have a negative 3.5.
    """
    haystack = normalize_text(text)
    needle = normalize_text(term).strip()
    if not needle:
        return ()
    found: list[Occurrence] = []
    for match in _pattern(needle).finditer(haystack):
        start = match.start()
        negative = False
        if start >= 1 and haystack[start - 1] in MINUS_SIGNS:
            before = start - 2
            negative = before < 0 or not (haystack[before].isalnum() or haystack[before] == ")")
        found.append(Occurrence(start=start, end=match.end(), negative=negative))
    return tuple(found)

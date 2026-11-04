"""Permission, condition and list markers in a quotable text (ARCHITECTURE §14).

A marker is a word or phrase that a rule can see. It is never a decision: whether a permission marker answers
a whether-question is for verification (P6) and the decision (P7). Each family is a short, reviewed list. Longer
phrases are tried before their parts, and matches never overlap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_WORD_EDGE = r"(?<![A-Za-z])"
_WORD_END = r"(?![A-Za-z])"


def _phrases(phrases: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(_WORD_EDGE + r"(?i:" + phrase + r")" + _WORD_END) for phrase in phrases)


# Negative permission and prohibition phrases (polarity negative). They are tried first.
_PERMISSION_NEGATIVE = _phrases(
    (
        r"must\s+not",
        r"must\s+never",
        r"shall\s+not",
        r"shall\s+never",
        r"may\s+not",
        r"cannot",
        r"can\s+not",
        r"(?:is|are)\s+not\s+(?:permitted|allowed|authori[sz]ed|required|necessary|mandatory|possible)",
        r"not\s+(?:permitted|allowed|authori[sz]ed|required|necessary|mandatory)",
        r"no\s+longer\s+(?:permitted|allowed|required)",
        r"(?:is|are)\s+(?:prohibited|forbidden)",
        r"prohibited",
        r"forbidden",
        r"need\s+not",
    )
)

# Positive permission and obligation phrases.
_PERMISSION_POSITIVE = _phrases(
    (
        r"must",
        r"shall",
        r"may",
        r"(?:is|are)\s+(?:permitted|allowed|authori[sz]ed|required|mandatory|necessary|possible)",
        r"permitted\s+to",
        r"allowed\s+to",
    )
)

_CONDITION = _phrases(
    (
        r"only\s+if",
        r"provided\s+that",
        r"subject\s+to",
        r"except\s+(?:as|for|where|when|if)",
        r"except",
        r"unless",
        r"in\s+the\s+event\s+(?:that|of)",
        r"in\s+cases?\s+where",
        r"in\s+case",
        r"if",
        r"when",
        r"where",
        r"exceptions?",
        r"(?:does|do)\s+not\s+apply",
    )
)

_LIST = _phrases(
    (
        r"including",
        r"includes",
        r"include",
        r"such\s+as",
        r"for\s+example",
        r"for\s+instance",
        r"the\s+following",
        r"consists?\s+of",
        r"comprises?",
        r"namely",
    )
)


@dataclass(frozen=True)
class Marker:
    """A marker found in a text. ``start`` and ``end`` are half-open offsets into that text.

    ``negative`` is true for a negative permission or prohibition phrase. It is false for every other kind.
    """

    kind: str
    text: str
    start: int
    end: int
    negative: bool = False


def _scan(text: str, patterns: tuple[re.Pattern[str], ...], kind: str, negative: bool, taken: list[tuple[int, int]]) -> list[Marker]:
    found: list[Marker] = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            start, end = match.span()
            if any(start < other_end and other_start < end for other_start, other_end in taken):
                continue
            taken.append((start, end))
            found.append(Marker(kind=kind, text=match.group(0), start=start, end=end, negative=negative))
    return found


def find_markers(text: str, kind: str) -> tuple[Marker, ...]:
    """The markers of one family (``permission``, ``condition`` or ``list``) in ``text``, in order of position.

    Raises ``ValueError`` for an unknown family, so a typo cannot return an empty list silently.
    """
    taken: list[tuple[int, int]] = []
    if kind == "permission":
        found = _scan(text, _PERMISSION_NEGATIVE, kind, True, taken) + _scan(
            text, _PERMISSION_POSITIVE, kind, False, taken
        )
    elif kind == "condition":
        found = _scan(text, _CONDITION, kind, False, taken)
    elif kind == "list":
        found = _scan(text, _LIST, kind, False, taken)
    else:
        raise ValueError(f"unknown marker family {kind!r}; expected permission, condition or list")
    return tuple(sorted(found, key=lambda marker: (marker.start, marker.end)))

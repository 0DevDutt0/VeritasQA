"""Build the FTS5 MATCH expression for an exact phrase (ARCHITECTURE §12).

User text never reaches MATCH as syntax. The phrase is normalized with the same rules as the index,
its tokens are the matches of a fixed pattern, and the tokens are placed inside a single pair of
double quotes behind a column filter. FTS5 operators such as ``AND``, ``NEAR``, ``-``, ``*``, ``:``
and ``^`` therefore have no effect: they are ordinary words.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.common.errors import QueryError
from app.common.text import normalize_text

# Letters and digits only. The underscore and every punctuation mark separate tokens.
TOKEN_PATTERN = re.compile(r"[^\W_]+")

# The MATCH expression is restricted to the index text, so heading text adds no candidates.
MATCH_COLUMN = "index_text"


@dataclass(frozen=True)
class PhraseQuery:
    """A phrase as the caller wrote it, its index-form normalization, its tokens and the MATCH expression."""

    phrase: str
    normalized: str
    tokens: tuple[str, ...]
    match: str


def build_phrase_query(phrase: str) -> PhraseQuery:
    """Return the query for ``phrase``. Raise :class:`QueryError` when it has no letter or digit."""
    if not isinstance(phrase, str):
        raise QueryError(f"a phrase must be text, not {type(phrase).__name__}")
    normalized = normalize_text(phrase)
    tokens = tuple(TOKEN_PATTERN.findall(normalized))
    if not tokens:
        raise QueryError(f"the phrase {phrase!r} has no letter or digit to search for")
    match = f'{MATCH_COLUMN} : "{" ".join(tokens)}"'
    return PhraseQuery(phrase=phrase, normalized=normalized, tokens=tokens, match=match)

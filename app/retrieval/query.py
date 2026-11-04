"""Build the FTS5 MATCH expression for an exact phrase (ARCHITECTURE §12).

The normalized phrase is passed as one FTS5 string, with every double quote doubled, behind a column
filter. FTS5 tokenizes that string with the same tokenizer as the index, so the query and the index
cannot disagree about where a token ends. Inside a quoted string, FTS5 operators such as ``AND``,
``NEAR``, ``-``, ``*``, ``:``, ``^`` and parentheses are ordinary text. The mapping from normalized
phrase characters back to the raw phrase is kept beside the query, as SPEC §4 requires.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from app.common.errors import QueryError
from app.common.text import NormalizedText, normalize_with_map

# The MATCH expression is restricted to the index text, so heading text adds no candidates.
MATCH_COLUMN = "index_text"


@dataclass(frozen=True)
class PhraseQuery:
    """A phrase as the caller wrote it, its normalized form with the raw range of each character, and the MATCH expression."""

    phrase: str
    mapping: NormalizedText
    match: str

    @property
    def normalized(self) -> str:
        return self.mapping.text

    def raw_range(self, start: int, end: int) -> tuple[int, int]:
        """The raw range of the phrase that the normalized characters ``[start, end)`` came from."""
        return self.mapping.raw_range(start, end)


def build_phrase_query(phrase: str) -> PhraseQuery:
    """Return the query for ``phrase``.

    Raises :class:`QueryError` when the phrase is not text, contains a control character, or has no
    letter or digit to search for.
    """
    if not isinstance(phrase, str):
        raise QueryError(f"a phrase must be text, not {type(phrase).__name__}")
    if any(unicodedata.category(character) == "Cc" and not character.isspace() for character in phrase):
        raise QueryError(f"the phrase {phrase!r} contains a control character")
    mapping = normalize_with_map(phrase)
    if not any(character.isalnum() for character in mapping.text):
        raise QueryError(f"the phrase {phrase!r} has no letter or digit to search for")
    escaped = mapping.text.replace('"', '""')
    return PhraseQuery(phrase=phrase, mapping=mapping, match=f'{MATCH_COLUMN} : "{escaped}"')

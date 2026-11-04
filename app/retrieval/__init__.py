"""Retrieval: exact phrase search over the store (ARCHITECTURE §4, §12). BM25 and rules arrive in P4."""

from app.common.errors import QueryError
from app.retrieval.phrase import find_phrase, fold_case, span_matches
from app.retrieval.query import PhraseQuery, build_phrase_query

__all__ = [
    "PhraseQuery",
    "QueryError",
    "build_phrase_query",
    "find_phrase",
    "fold_case",
    "span_matches",
]

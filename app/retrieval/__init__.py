"""Retrieval over the store: exact phrase search (ARCHITECTURE §12) and BM25 candidates with reviewed rules (§13)."""

from app.common.errors import QueryError
from app.retrieval.bm25 import (
    ColumnWeights,
    ContextRef,
    QueryTrace,
    RetrievalCandidate,
    RetrievalResult,
    search,
)
from app.retrieval.config import RetrievalConfig, load_retrieval_config
from app.retrieval.errors import RetrievalConfigError, RuleConfigError
from app.retrieval.phrase import find_phrase, fold_case, span_matches
from app.retrieval.query import PhraseQuery, build_phrase_query
from app.retrieval.rules import AppliedRule, Rule, RuleExample, RuleSet, expand_words, load_rules
from app.retrieval.terms import Term, TermKind, extract_terms

__all__ = [
    "AppliedRule",
    "ColumnWeights",
    "ContextRef",
    "PhraseQuery",
    "QueryError",
    "QueryTrace",
    "RetrievalCandidate",
    "RetrievalConfig",
    "RetrievalConfigError",
    "RetrievalResult",
    "Rule",
    "RuleConfigError",
    "RuleExample",
    "RuleSet",
    "Term",
    "TermKind",
    "build_phrase_query",
    "expand_words",
    "extract_terms",
    "find_phrase",
    "fold_case",
    "load_retrieval_config",
    "load_rules",
    "search",
    "span_matches",
]

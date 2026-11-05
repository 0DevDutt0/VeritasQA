"""BM25 candidate retrieval over one document (SPEC §4; ARCHITECTURE §13; D39-D43).

``search`` returns candidates, which are the units that the query words reached. It returns no evidence.
A candidate keeps its raw BM25 value for audit, and that value is never a probability. A candidate that
only a reviewed rule reached is ``expansion_only``, and no check may accept it as support (D38).
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Literal

from app.common.errors import StorageError
from app.common.text import normalize_text
from app.retrieval.config import RetrievalConfig, load_retrieval_config
from app.retrieval.forms import all_forms
from app.retrieval.phrase import fold_case, span_matches
from app.retrieval.query import build_phrase_query
from app.retrieval.rules import AppliedRule, RuleSet, expand_words, folded_words, load_rules
from app.retrieval.terms import Term, extract_terms
from app.storage.retrieval_reads import UnitSummary
from app.storage.store import Store

Via = Literal["original", "expansion"]


@dataclass(frozen=True)
class ColumnWeights:
    """The ``bm25()`` column weights for the index text and the heading text."""

    index_text: float
    heading_text: float


@dataclass(frozen=True)
class ContextRef:
    """The context of one candidate: body units around it and the headings of its sections (D42).

    Context is never a candidate, never replaces one, and is never quoted on its own.
    """

    before: tuple[str, ...]
    after: tuple[str, ...]
    section_heading_id: str | None
    parent_heading_id: str | None


@dataclass(frozen=True)
class RetrievalCandidate:
    """One unit that a query reached. ``rank`` is its 1-based position in the result."""

    rank: int
    evidence_id: str
    pdf_page: int
    ordinal: int
    content_type: str
    derived: bool
    extraction_quality: str
    via: Via
    rule_ids: tuple[str, ...]
    exact_terms: tuple[str, ...]
    bm25_raw: float
    duplicate_evidence_ids: tuple[str, ...]
    context: ContextRef

    @property
    def expansion_only(self) -> bool:
        """True when only a reviewed rule reached this unit. Such a unit never counts as support (D38)."""
        return self.via == "expansion"


@dataclass(frozen=True)
class QueryTrace:
    """What the search did, so that every expansion and every removal can be audited (ARCHITECTURE §13)."""

    words: tuple[str, ...]
    terms: tuple[Term, ...]
    rules_fingerprint: str
    applied_rules: tuple[AppliedRule, ...]
    index_rows: int
    k: int
    expansion_k: int
    weights: ColumnWeights
    context_window: int
    original_hits: int
    expansion_hits: int
    duplicates_removed: int
    truncated_original: int
    truncated_expansion: int
    statistics: str = "per_document"


@dataclass(frozen=True)
class RetrievalResult:
    document_id: str
    query: str
    candidates: tuple[RetrievalCandidate, ...]
    trace: QueryTrace


@dataclass
class _Entry:
    evidence_id: str
    bm25_raw: float
    summary: UnitSummary
    via: Via
    rule_ids: tuple[str, ...]
    duplicates: list[str]


def _quote(text: str) -> str:
    """One FTS5 string. Inside it, FTS5 operators are plain text, and a double quote is doubled."""
    return '"' + text.replace('"', '""') + '"'


def _unique_by_fold(words: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    unique: list[str] = []
    for word in words:
        key = fold_case(word)
        if key not in seen:
            seen.add(key)
            unique.append(word)
    return tuple(unique)


def _whole_number(name: str, value: int, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be a whole number of at least {minimum}, not {value!r}")
    return value


def _check_weights(weights: ColumnWeights) -> None:
    for name, value in (("index_text", weights.index_text), ("heading_text", weights.heading_text)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"the {name} weight must be a finite number above zero, not {value!r}")


def _text_key(raw_text: str) -> str:
    """The duplicate key: SHA-256 of the normalized raw text (case is kept)."""
    return hashlib.sha256(normalize_text(raw_text).encode("utf-8")).hexdigest()


def _keep_first(
    hits: list[tuple[str, float]],
    via: Via,
    summaries: dict[str, UnitSummary],
    kept_by_key: dict[str, _Entry],
    reached_by: dict[str, set[str]],
) -> list[_Entry]:
    """Keep the first hit of each normalized text. Each later hit with the same text is recorded on that entry."""
    kept: list[_Entry] = []
    for evidence_id, raw in hits:
        summary = summaries[evidence_id]
        key = _text_key(summary.raw_text)
        existing = kept_by_key.get(key)
        if existing is not None:
            existing.duplicates.append(evidence_id)
            continue
        entry = _Entry(
            evidence_id=evidence_id,
            bm25_raw=raw,
            summary=summary,
            via=via,
            rule_ids=tuple(sorted(reached_by.get(evidence_id, ()))),
            duplicates=[],
        )
        kept_by_key[key] = entry
        kept.append(entry)
    return kept


def search(
    store: Store,
    document_id: str,
    query: str,
    *,
    k: int | None = None,
    weights: ColumnWeights | None = None,
    context_window: int | None = None,
    expansion_k: int | None = None,
    rules: RuleSet | None = None,
    config: RetrievalConfig | None = None,
) -> RetrievalResult:
    """Rank the units of one document for a query. Every rule applied here is described in ARCHITECTURE §13.

    Any argument left at ``None`` takes its value from ``config/retrieval.toml`` (or from ``config``).
    Raises :class:`QueryError` when the query is not text or has no letter or digit,
    :class:`StorageError` when the store holds no such document, and :class:`ValueError` when a numeric
    argument is out of range.
    """
    settings = config if config is not None else load_retrieval_config()
    limit = _whole_number("k", settings.k if k is None else k, minimum=1)
    expansion_limit = _whole_number(
        "expansion_k", settings.expansion_k if expansion_k is None else expansion_k, minimum=0
    )
    window = _whole_number(
        "context_window", settings.context_window if context_window is None else context_window, minimum=0
    )
    column = weights if weights is not None else ColumnWeights(settings.weight_index, settings.weight_heading)
    _check_weights(column)
    rule_set = rules if rules is not None else load_rules()

    normalized = build_phrase_query(query).normalized
    words = tuple(word for word in normalized.split(" ") if any(character.isalnum() for character in word))
    folded_sequence = tuple(fold_case(word) for word in words)
    original_words = _unique_by_fold(words)
    word_keys = set(folded_sequence)
    terms = extract_terms(normalized)
    term_queries = [(term, build_phrase_query(term.text)) for term in terms]
    applied = expand_words(folded_sequence, rule_set)

    # One entry per alternative text. An alternative that an original word already reaches adds nothing.
    alternatives: dict[str, str] = {}
    rules_for_alternative: dict[str, set[str]] = {}
    for item in applied:
        key = " ".join(folded_words(item.alternative))
        if key in word_keys:
            continue
        alternatives.setdefault(key, item.alternative)
        rules_for_alternative.setdefault(key, set()).add(item.rule_id)

    # Each query word and its word forms (P13, D131) are original hits. A rule never adds them.
    original_match = " OR ".join(_quote(form) for form in all_forms(original_words))
    column_pair = (column.index_text, column.heading_text)

    with store.document_bm25_index(document_id) as index:
        original_hits = index.rank(original_match, column_pair)
        original_ids = {evidence_id for evidence_id, _ in original_hits}
        expansion_hits: list[tuple[str, float]] = []
        reached_by: dict[str, set[str]] = {}
        if alternatives:
            union = " OR ".join(_quote(alternative) for alternative in alternatives.values())
            expansion_hits = [hit for hit in index.rank(union, column_pair) if hit[0] not in original_ids]
            expansion_ids = {evidence_id for evidence_id, _ in expansion_hits}
            for key, alternative in alternatives.items():
                for evidence_id, _ in index.rank(_quote(alternative), column_pair):
                    if evidence_id in expansion_ids:
                        reached_by.setdefault(evidence_id, set()).update(rules_for_alternative[key])
        index_rows = index.row_count

        needed = [evidence_id for evidence_id, _ in original_hits] + [evidence_id for evidence_id, _ in expansion_hits]
        summaries = store.unit_summaries(document_id, needed)
    missing = [evidence_id for evidence_id in needed if evidence_id not in summaries]
    if missing:
        raise StorageError(f"the store has no unit {missing[0]} of document {document_id}, which the index returned")

    kept_by_key: dict[str, _Entry] = {}
    originals = _keep_first(original_hits, "original", summaries, kept_by_key, {})
    expansions = _keep_first(expansion_hits, "expansion", summaries, kept_by_key, reached_by)
    kept_originals = originals[:limit]
    kept_expansions = expansions[:expansion_limit]

    candidates: list[RetrievalCandidate] = []
    for rank, entry in enumerate(kept_originals + kept_expansions, start=1):
        summary = entry.summary
        before, after = store.body_neighbours(document_id, summary.pdf_page, summary.ordinal, window)
        heading, parent = store.section_headings(document_id, summary.section_id)
        exact = tuple(
            dict.fromkeys(term.text for term, phrase in term_queries if span_matches(summary.raw_text, phrase))
        )
        candidates.append(
            RetrievalCandidate(
                rank=rank,
                evidence_id=entry.evidence_id,
                pdf_page=summary.pdf_page,
                ordinal=summary.ordinal,
                content_type=summary.content_type,
                derived=summary.derived,
                extraction_quality=summary.extraction_quality,
                via=entry.via,
                rule_ids=entry.rule_ids,
                exact_terms=exact,
                bm25_raw=entry.bm25_raw,
                duplicate_evidence_ids=tuple(entry.duplicates),
                context=ContextRef(
                    before=tuple(before),
                    after=tuple(after),
                    section_heading_id=None if heading == entry.evidence_id else heading,
                    parent_heading_id=None if parent == entry.evidence_id else parent,
                ),
            )
        )

    trace = QueryTrace(
        words=words,
        terms=terms,
        rules_fingerprint=rule_set.fingerprint,
        applied_rules=applied,
        index_rows=index_rows,
        k=limit,
        expansion_k=expansion_limit,
        weights=column,
        context_window=window,
        original_hits=len(original_hits),
        expansion_hits=len(expansion_hits),
        duplicates_removed=sum(len(entry.duplicates) for entry in originals + expansions),
        truncated_original=len(originals) - len(kept_originals),
        truncated_expansion=len(expansions) - len(kept_expansions),
    )
    return RetrievalResult(document_id=document_id, query=query, candidates=tuple(candidates), trace=trace)

"""Retrieval-only baselines for the sweep phase: BM25 (the engine's own order), TF-IDF and Reciprocal Rank Fusion
(ARCHITECTURE §18.5, D94 to D96).

Nothing here calls ``answer()``, the verifier or the policy. A baseline only orders units, and its order is measured
with the definitions of ARCHITECTURE §17.7, through the same functions the harness uses. scikit-learn is imported inside
``tfidf_vectorizer_class`` and nowhere else, so importing this module needs no optional library (ARCHITECTURE §18.6).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.benchmark.errors import BenchmarkError
from app.common.text import normalize_text
from app.document_structure.models import EvidenceUnit
from app.evaluation.gold import GoldRecord
from app.evaluation.scoring import ObservedRetrieval, RetrievalMeasure, measure_retrieval, retrieval_summary
from app.question_processing.analysis import analyze
from app.retrieval import search
from app.retrieval.config import RetrievalConfig
from app.storage import Store

BASELINE_DEPTH = 50
RRF_CONSTANT = 60
ARMS = ("bm25", "tfidf", "rrf")


@dataclass(frozen=True)
class ComponentQuery:
    """One component with gold evidence: the text the engine searches with, and its gold quotes and pages."""

    index: int
    query: str
    gold_quotes: tuple[str, ...]
    gold_pages: tuple[int, ...]


@dataclass(frozen=True)
class TfidfModel:
    """A TF-IDF model fitted on one document's body units. Built by :func:`tfidf_model`."""

    vectorizer: Any
    matrix: Any
    evidence_ids: tuple[str, ...]


def tfidf_vectorizer_class() -> type:
    """The scikit-learn vectorizer class. Raises BenchmarkError when the optional group is not installed (§18.6)."""
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
    except ImportError as exc:
        raise BenchmarkError(
            "the TF-IDF baseline needs scikit-learn, which is in requirements-experimental.txt and not in the baseline"
        ) from exc
    return TfidfVectorizer


def body_units(store: Store, document_id: str) -> tuple[EvidenceUnit, ...]:
    """The body units of one document in reading order: the set that the BM25 index holds (ARCHITECTURE §13)."""
    units = [unit for unit in store.load_structure(document_id).units if unit.body_retrieval]
    return tuple(sorted(units, key=lambda unit: (unit.pdf_page, unit.ordinal)))


def text_key(raw_text: str) -> str:
    """The duplicate key of §13: the SHA-256 of the normalized raw text."""
    return hashlib.sha256(normalize_text(raw_text).encode("utf-8")).hexdigest()


def dedupe(ranking: Sequence[str], raw_text: Mapping[str, str], depth: int) -> list[str]:
    """Keep the first unit of each duplicate group, in rank order, and stop at ``depth`` (ARCHITECTURE §13, §18.5)."""
    seen: set[str] = set()
    kept: list[str] = []
    for evidence_id in ranking:
        key = text_key(raw_text[evidence_id])
        if key in seen:
            continue
        seen.add(key)
        kept.append(evidence_id)
        if len(kept) == depth:
            break
    return kept


def component_queries(records: Sequence[GoldRecord]) -> tuple[ComponentQuery, ...]:
    """The searchable components with gold evidence, in record order (ARCHITECTURE §17.7, §18.5)."""
    queries: list[ComponentQuery] = []
    for record in records:
        analysis = analyze(record.question)
        for index, component in enumerate(analysis.components, start=1):
            if not component.searchable:
                continue
            evidence = [item for item in record.evidence if item.component == index]
            if not evidence:
                continue
            queries.append(
                ComponentQuery(
                    index=index,
                    query=component.retrieval_query,
                    gold_quotes=tuple(item.quote for item in evidence),
                    gold_pages=tuple(item.pdf_page for item in evidence),
                )
            )
    return tuple(queries)


def bm25_ranking(store: Store, document_id: str, query: str, base: RetrievalConfig) -> list[str]:
    """The engine's BM25 order for one query: original words only, no expansion, to depth 50 (ARCHITECTURE §18.5)."""
    config = RetrievalConfig(
        k=BASELINE_DEPTH,
        expansion_k=0,
        weight_index=base.weight_index,
        weight_heading=base.weight_heading,
        context_window=0,
    )
    result = search(store, document_id, query, config=config)
    return [candidate.evidence_id for candidate in result.candidates]


def tfidf_model(units: Sequence[EvidenceUnit]) -> TfidfModel:
    """Fit TF-IDF on the index text of the units (ARCHITECTURE §18.5). Heading text is not used.

    The token pattern takes Unicode letters and digits, so it is close to the FTS5 tokenizer but not identical.
    """
    vectorizer = tfidf_vectorizer_class()(
        token_pattern=r"[^\W_]+",
        lowercase=True,
        strip_accents="unicode",
        norm="l2",
        use_idf=True,
        smooth_idf=True,
        sublinear_tf=False,
    )
    matrix = vectorizer.fit_transform([unit.index_text for unit in units])
    return TfidfModel(vectorizer=vectorizer, matrix=matrix, evidence_ids=tuple(unit.evidence_id for unit in units))


def tfidf_ranking(model: TfidfModel, query: str) -> list[str]:
    """The units with a positive TF-IDF score for the query: highest score first, then evidence ID.

    Duplicates are not removed here; the caller removes them (ARCHITECTURE §18.5).
    """
    vector = model.vectorizer.transform([query])
    scores = (model.matrix @ vector.T).toarray().ravel().tolist()
    positive = [index for index, score in enumerate(scores) if score > 0]
    positive.sort(key=lambda index: (-scores[index], model.evidence_ids[index]))
    return [model.evidence_ids[index] for index in positive]


def rrf_ranking(*rankings: Sequence[str]) -> list[str]:
    """Reciprocal Rank Fusion: score = the sum over the lists that hold the unit of 1 / (RRF_CONSTANT + rank), with rank
    counted from 1. Ties go to the lower evidence ID (ARCHITECTURE §18.5). The constant is fixed, not tuned."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, evidence_id in enumerate(ranking, start=1):
            scores[evidence_id] = scores.get(evidence_id, 0.0) + 1.0 / (RRF_CONSTANT + rank)
    return sorted(scores, key=lambda evidence_id: (-scores[evidence_id], evidence_id))


def _measure(query: ComponentQuery, ranking: Sequence[str], units: Mapping[str, tuple[int, str]]) -> RetrievalMeasure:
    entries = tuple((rank, evidence_id) for rank, evidence_id in enumerate(ranking, start=1))
    observed = ObservedRetrieval(component=query.index, k_cut=BASELINE_DEPTH, entries=entries)
    return measure_retrieval(query.index, observed, query.gold_quotes, query.gold_pages, units)


def measure_baselines(
    store: Store,
    document_id: str,
    records: Sequence[GoldRecord],
    *,
    base: RetrievalConfig,
) -> dict[str, Any]:
    """Measure the three arms on the components of ``records`` that have gold evidence (ARCHITECTURE §18.5).

    Raises BenchmarkError when scikit-learn is missing, before any ranking is computed.
    """
    tfidf_vectorizer_class()
    units = body_units(store, document_id)
    raw_text = {unit.evidence_id: unit.raw_text for unit in units}
    unit_view = {unit.evidence_id: (unit.pdf_page, unit.raw_text) for unit in units}
    model = tfidf_model(units)
    queries = component_queries(records)
    measures: dict[str, list[RetrievalMeasure]] = {arm: [] for arm in ARMS}
    for query in queries:
        bm25 = bm25_ranking(store, document_id, query.query, base)
        tfidf = dedupe(tfidf_ranking(model, query.query), raw_text, BASELINE_DEPTH)
        fused = dedupe(rrf_ranking(bm25, tfidf), raw_text, BASELINE_DEPTH)
        for arm, ranking in (("bm25", bm25), ("tfidf", tfidf), ("rrf", fused)):
            measures[arm].append(_measure(query, ranking, unit_view))
    return {
        "depth": BASELINE_DEPTH,
        "rrf_constant": RRF_CONSTANT,
        "components": len(queries),
        "arms": {arm: retrieval_summary(measures[arm]) for arm in ARMS},
    }

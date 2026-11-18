"""Rank single-source extractive clauses by document-local term coverage."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from app.common.text import normalize_text
from app.document_structure.models import ContentType, EvidenceUnit
from app.evidence.extractive import RULE_ID, Intent, allows_multiple, cell_keys, keywords, sentence_ranges
from app.evidence.selection import AnswerCandidate, unit_page_offsets
from app.ingestion.models import QualityStatus
from app.retrieval.bm25 import ContextRef, RetrievalCandidate
from app.storage import Store
from app.verification.grounding import PROSE, Grounding, aligned_clause


@dataclass(frozen=True)
class RankedClause:
    unit: EvidenceUnit
    quote: str
    page_start: int
    page_end: int
    ground: Grounding
    score: float

    @property
    def text(self) -> str:
        span = self.ground.span
        return self.quote[span.start : span.end]

    def candidate(self, intent: Intent, rank: int) -> AnswerCandidate:
        unit = self.unit
        span = self.ground.span
        return AnswerCandidate(
            component_id=intent.component.component_id,
            question_type=intent.component.question_type,
            retrieval=RetrievalCandidate(
                rank=rank,
                evidence_id=unit.evidence_id,
                pdf_page=unit.pdf_page,
                ordinal=unit.ordinal,
                content_type=unit.content_type.value,
                derived=False,
                extraction_quality=unit.extraction_quality.value,
                via="extractive",
                rule_ids=(RULE_ID,),
                exact_terms=(),
                bm25_raw=0.0,
                duplicate_evidence_ids=(),
                context=ContextRef((), (), None, None),
                lexical_score=self.score,
            ),
            pdf_page=unit.pdf_page,
            section_id=unit.section_id,
            rule_id=RULE_ID,
            granularity="cell" if unit.content_type == ContentType.TABLE_CELL else "sentence",
            quote=self.quote,
            page_start=self.page_start,
            page_end=self.page_end,
            answer_span=self.text,
            answer_page_start=self.page_start + span.start,
            answer_page_end=self.page_start + span.end,
            answer_kind=span.kind,
            values=(),
            negated=span.negative,
            attribute_hits=(),
            flags=(),
        )


@dataclass(frozen=True)
class _IndexedUnit:
    unit: EvidenceUnit
    keys: frozenset[str]


class ClauseIndex:
    """A read-only view over one document for one question, shared by its components."""

    def __init__(self, store: Store, document_id: str) -> None:
        self._units: list[_IndexedUnit] = []
        frequency: Counter[str] = Counter()
        for unit in store.body_units(document_id):
            cell = unit.content_type == ContentType.TABLE_CELL
            if unit.content_type not in PROSE and not cell:
                continue
            keys = keywords(unit.raw_text)
            if cell:
                keys |= cell_keys(unit)
            self._units.append(_IndexedUnit(unit, keys))
            frequency.update(keys)
        self._frequency = frequency

    def rank(self, intent: Intent) -> list[RankedClause]:
        if not intent.keys or len(intent.keys) > 80:
            return []
        size = len(self._units)
        weights = {word: 1 + math.log((size + 1) / (self._frequency[word] + 1)) for word in intent.keys}
        total = sum(weights.values())
        coordinated = allows_multiple(intent) and "and" in intent.core.casefold().split()
        found: dict[str, RankedClause] = {}
        for item in self._units:
            unit = item.unit
            if len(item.keys & intent.keys) < min(2, len(intent.keys)):
                continue
            cell = unit.content_type == ContentType.TABLE_CELL
            if (intent.table is not None) != cell:
                continue
            ranges = ((0, len(unit.raw_text)),) if cell else sentence_ranges(unit.raw_text)
            for start, end in ranges:
                quote = unit.raw_text[start:end]
                ground = aligned_clause(intent, quote, unit)
                if ground is None:
                    continue
                offsets = unit_page_offsets(unit, start, end)
                if offsets is None:
                    continue
                coverage = (
                    sum(weights[word] for word in ground.local)
                    + (0.9 if cell else 0.55) * sum(weights[word] for word in ground.scope)
                ) / total
                minimum = 0.55 if len(intent.keys) > 3 else 0.70
                if cell or (intent.count_nouns and ground.scope):
                    minimum = 0.60
                if coordinated:
                    minimum = min(minimum, 0.62)
                if intent.codes:
                    minimum = 0.45
                if coverage < minimum:
                    continue
                density = len(ground.local) / max(1, len(keywords(quote)))
                score = coverage + 0.07 * density
                if ground.span.kind != "clause":
                    score += 0.025
                if ground.span.kind == "prohibition" and intent.permission:
                    score += 0.065
                entry = RankedClause(unit, quote, *offsets, ground, round(score, 8))
                key = normalize_text(quote).casefold()
                existing = found.get(key)
                if existing is None or _order(entry) < _order(existing):
                    found[key] = entry
        return sorted(found.values(), key=_order)


def _order(entry: RankedClause) -> tuple[float, bool, int, int, int]:
    return (
        -entry.score,
        entry.unit.extraction_quality != QualityStatus.VERIFIED,
        entry.unit.pdf_page,
        entry.unit.ordinal,
        entry.page_start,
    )

"""The conflict screen: every passage of the document that carries the question's subject, compared claim by claim
(SPEC §8; ARCHITECTURE §16.2, §16.3; D70, D71).

``screen_component`` finds the units that contain every target word of a component (the exact check of P3, once per
word, intersected by unit). Within each unit it takes the sentences (a table cell is one passage, as in P5) that contain
every target word. It lists the claims of each piece and compares every pair of claims that the comparison can judge.
Each difference becomes a :class:`Relation` with an :class:`Impact`. The screen reports differences and never resolves
them. The decision step turns the impacts into a status (ARCHITECTURE §16.4).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from app.conflict.claims import Claim, claims_of, compare, normalize_date
from app.conflict.config import ConflictConfig, supersession_pattern
from app.document_structure.models import ContentType, EvidenceUnit
from app.evidence.markers import Marker, find_markers
from app.evidence.segment import sentence_spans
from app.evidence.selection import sentence_pairs, unit_page_offsets
from app.evidence.values import Value, ValueKind, find_values
from app.question_processing.analysis import QuestionComponent, QuestionType
from app.question_processing.vocabulary import (
    ATTRIBUTE_PLURALS,
    ATTRIBUTE_WORDS,
    FUNCTION_WORDS,
    NEGATION_WORDS,
    PRONOUNS,
    QUESTION_WORDS,
)
from app.retrieval.phrase import build_phrase_query, find_phrase, span_matches
from app.storage import Store
from app.verification.vocabulary import ANSWER_TYPES

_WORD = re.compile(r"[^\W\d_]+")


class ConflictRelation(StrEnum):
    """What the screen found when it compared two claims (ARCHITECTURE §16.3). SAME_VALUE is counted, not recorded."""

    SAME_VALUE = "same_value"
    DIFFERENT_SCOPE = "different_scope"
    DATED_CHANGE = "dated_change"
    EXPLICIT_SUPERSESSION = "explicit_supersession"
    POTENTIAL_DISCREPANCY = "potential_discrepancy"
    CONFIRMED_INCOMPATIBLE = "confirmed_incompatible"


class Impact(StrEnum):
    """What a relation means for the answer. CONFLICT needs two clean passages (SPEC §9). SOURCE means a passage
    with a source problem is involved. AMBIGUOUS means the passages may concern different cases."""

    CONFLICT = "conflict"
    SOURCE = "source"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class Piece:
    """One sentence (or passage) of a unit that contains every target word of its component.

    ``page_start`` and ``page_end`` are offsets in the page's raw text. They are None when the piece crosses a join
    between source spans, so it cannot be quoted. ``dates`` are the effective dates of the piece (not its claims) for
    ``how_many`` and ``whether``. ``scope`` is the set of its qualifying words (ARCHITECTURE §16.3). ``unit_span`` is
    the piece's offsets in its unit's raw text, so that two pieces sharing a sentence can be recognised (P14, §16.3).
    """

    evidence_id: str
    pdf_page: int
    ordinal: int
    printed_page: str | None
    section_id: str | None
    heading_text: str
    content_type: str
    extraction_quality: str
    derived: bool
    text: str
    page_start: int | None
    page_end: int | None
    claims: tuple[Claim, ...]
    scope: frozenset[str]
    dates: frozenset[str]
    supersession_phrase: str | None
    unit_span: tuple[int, int] | None = None

    @property
    def clean(self) -> bool:
        """A passage that may support a CONFLICT: verified source text, and not a generated table row."""
        return self.extraction_quality == "verified" and not self.derived

    @property
    def quotable(self) -> bool:
        return self.page_start is not None and self.page_end is not None


@dataclass(frozen=True)
class Relation:
    """A difference between two claims. ``first`` and ``second`` index :attr:`ConflictScreen.pieces`."""

    kind: ConflictRelation
    impact: Impact
    first: int
    second: int
    first_claim: str
    second_claim: str
    reason: str


@dataclass(frozen=True)
class ScreenCounts:
    units_with_every_word: int
    pieces_matched: int
    pieces_with_claims: int
    derived_pieces: int
    unquotable_pieces: int


@dataclass(frozen=True)
class ConflictScreen:
    component_id: str
    screened: bool
    pieces: tuple[Piece, ...]
    relations: tuple[Relation, ...]
    agreeing_pairs: int
    counts: ScreenCounts


def _empty_screen(component: QuestionComponent) -> ConflictScreen:
    return ConflictScreen(
        component_id=component.component_id,
        screened=False,
        pieces=(),
        relations=(),
        agreeing_pairs=0,
        counts=ScreenCounts(0, 0, 0, 0, 0),
    )


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def _words(text: str) -> list[str]:
    return _WORD.findall(_fold(text))


def _is_known(word: str, known: set[str]) -> bool:
    return word in known or (word.endswith("s") and word[:-1] in known)


def scope_words(
    text: str,
    target_terms: tuple[str, ...],
    values: tuple[Value, ...],
    markers: tuple[Marker, ...],
) -> frozenset[str]:
    """The qualifying words of a piece: its words minus the target words, the value and marker words, and the reviewed
    function, question, attribute, negation and pronoun words. Two pieces with different qualifying words may apply to
    different cases. The result only chooses a label (ARCHITECTURE §16.3)."""
    known = set(FUNCTION_WORDS | QUESTION_WORDS | ATTRIBUTE_WORDS | ATTRIBUTE_PLURALS | NEGATION_WORDS | PRONOUNS)
    for term in target_terms:
        known.update(_words(term))
    for value in values:
        known.update(_words(value.text))
    for marker in markers:
        known.update(_words(marker.text))
    return frozenset(word for word in _words(text) if not _is_known(word, known))


def _supersession(text: str, config: ConflictConfig) -> str | None:
    match = supersession_pattern(config.supersession_phrases).search(_fold(text))
    return None if match is None else " ".join(match.group(0).split())


def _piece(
    unit: EvidenceUnit,
    start: int,
    end: int,
    component: QuestionComponent,
    config: ConflictConfig,
) -> Piece:
    text = unit.raw_text[start:end]
    values = find_values(text, count_nouns=component.target_terms)
    markers = find_markers(text, "permission") if component.question_type == QuestionType.WHETHER else ()
    claims = claims_of(component.question_type, values, markers, config)
    if component.question_type == QuestionType.WHEN:
        dates: frozenset[str] = frozenset()
    else:
        dates = frozenset(normalize_date(value.text) for value in values if value.kind in (ValueKind.DATE, ValueKind.PERIOD))
    offsets = unit_page_offsets(unit, start, end)
    return Piece(
        evidence_id=unit.evidence_id,
        pdf_page=unit.pdf_page,
        ordinal=unit.ordinal,
        printed_page=unit.printed_page,
        section_id=unit.section_id,
        heading_text=unit.heading_text,
        content_type=unit.content_type.value,
        extraction_quality=unit.extraction_quality.value,
        derived=unit.derived,
        text=text,
        page_start=None if offsets is None else offsets[0],
        page_end=None if offsets is None else offsets[1],
        claims=claims,
        scope=scope_words(text, component.target_terms, values, markers),
        dates=dates,
        supersession_phrase=_supersession(text, config),
        unit_span=(start, end),
    )


def _units_with_every_word(store: Store, document_id: str, terms: tuple[str, ...]) -> list[EvidenceUnit]:
    """Units that contain every term under the exact check (P3). One exact search per term, intersected by unit."""
    found: dict[str, EvidenceUnit] | None = None
    for term in terms:
        hits = {unit.evidence_id: unit for unit in find_phrase(store, document_id, term)}
        found = hits if found is None else {key: unit for key, unit in found.items() if key in hits}
        if not found:
            return []
    assert found is not None  # terms is never empty here
    return sorted(found.values(), key=lambda unit: (unit.pdf_page, unit.ordinal))


def _classify(first: Piece, second: Piece) -> ConflictRelation:
    if first.supersession_phrase is not None or second.supersession_phrase is not None:
        return ConflictRelation.EXPLICIT_SUPERSESSION
    if first.dates and second.dates and first.dates != second.dates:
        return ConflictRelation.DATED_CHANGE
    if first.scope != second.scope:
        return ConflictRelation.DIFFERENT_SCOPE
    if first.dates == second.dates and not (first.derived or second.derived):
        return ConflictRelation.CONFIRMED_INCOMPATIBLE
    return ConflictRelation.POTENTIAL_DISCREPANCY


def _impact(kind: ConflictRelation, first: Piece, second: Piece) -> Impact:
    if kind in (ConflictRelation.EXPLICIT_SUPERSESSION, ConflictRelation.CONFIRMED_INCOMPATIBLE):
        return Impact.CONFLICT if first.clean and second.clean else Impact.SOURCE
    return Impact.AMBIGUOUS


def _reason(kind: ConflictRelation, first: Piece, second: Piece, first_claim: Claim, second_claim: Claim) -> str:
    values = f"{first_claim.text!r} and {second_claim.text!r}"
    if kind == ConflictRelation.EXPLICIT_SUPERSESSION:
        phrase = first.supersession_phrase or second.supersession_phrase
        return (
            f"a passage states a supersession ({phrase!r}) and the two passages give different values ({values}); "
            "precedence is not applied in this version, so the answer abstains"
        )
    if kind == ConflictRelation.CONFIRMED_INCOMPATIBLE:
        return f"the passages give different values ({values}) for the same subject, qualifiers and dates"
    if kind == ConflictRelation.DATED_CHANGE:
        return f"the passages give different values ({values}) under different dates, so the answer depends on the date"
    if kind == ConflictRelation.DIFFERENT_SCOPE:
        return (
            f"the passages give different values ({values}) with different qualifying words, so they may apply to "
            "different cases; they are not called a conflict"
        )
    return (
        f"the passages give different values ({values}), and the screen cannot show that they cover the same case "
        "(one has a date and the other does not, or a generated table row is involved)"
    )


def _share_a_sentence(first: Piece, second: Piece) -> bool:
    """True when two pieces are the same unit and their spans overlap. A sentence pair (P14) shares its sentences
    with its members and with the pairs next to it, so such pieces are never compared (ARCHITECTURE §16.3)."""
    if first.unit_span is None or second.unit_span is None or first.evidence_id != second.evidence_id:
        return False
    return first.unit_span[0] < second.unit_span[1] and second.unit_span[0] < first.unit_span[1]


def compare_pieces(pieces: list[Piece] | tuple[Piece, ...]) -> tuple[tuple[Relation, ...], int]:
    """Compare every pair of claims of ``pieces`` (in piece order). Returns the relations and the number of agreeing
    pairs. Public so that the rules can be tested without a store (ARCHITECTURE §16.3)."""
    relations: list[Relation] = []
    agreeing = 0
    with_claims = [index for index, piece in enumerate(pieces) if piece.claims]
    for position, first_index in enumerate(with_claims):
        first = pieces[first_index]
        for second_index in with_claims[position + 1 :]:
            second = pieces[second_index]
            if _share_a_sentence(first, second):
                continue
            for first_claim in first.claims:
                for second_claim in second.claims:
                    outcome = compare(first_claim, second_claim)
                    if outcome is None:
                        continue
                    if outcome:
                        agreeing += 1
                        continue
                    kind = _classify(first, second)
                    relations.append(
                        Relation(
                            kind=kind,
                            impact=_impact(kind, first, second),
                            first=first_index,
                            second=second_index,
                            first_claim=first_claim.text,
                            second_claim=second_claim.text,
                            reason=_reason(kind, first, second, first_claim, second_claim),
                        )
                    )
    return tuple(relations), agreeing


def _pieces_of(unit: EvidenceUnit) -> list[tuple[int, int]]:
    raw = unit.raw_text
    if unit.content_type == ContentType.TABLE_CELL:
        return [(0, len(raw))]
    return sentence_spans(raw)


def screen_component(
    store: Store,
    document_id: str,
    component: QuestionComponent,
    config: ConflictConfig,
) -> ConflictScreen:
    """Screen one component of an answer type over the whole document (ARCHITECTURE §16.2).

    A component of another type, one that cannot be searched, or one with no target word is not screened: its
    result says so (``screened`` is False), and it has no relations.
    """
    if component.question_type not in ANSWER_TYPES or not component.searchable or not component.target_terms:
        return _empty_screen(component)
    queries = [build_phrase_query(term) for term in component.target_terms]
    units = _units_with_every_word(store, document_id, component.target_terms)
    pieces: list[Piece] = []
    for unit in units:
        for start, end in _pieces_of(unit):
            text = unit.raw_text[start:end]
            if all(span_matches(text, query) for query in queries):
                pieces.append(_piece(unit, start, end, component, config))
        # P14 (ARCHITECTURE §16.2): the sentence pairs that the selection rule builds are pieces too.
        for _, _, start, end in sentence_pairs(component, unit, component.target_terms):
            pieces.append(_piece(unit, start, end, component, config))
    relations, agreeing = compare_pieces(pieces)
    counts = ScreenCounts(
        units_with_every_word=len(units),
        pieces_matched=len(pieces),
        pieces_with_claims=sum(1 for piece in pieces if piece.claims),
        derived_pieces=sum(1 for piece in pieces if piece.derived),
        unquotable_pieces=sum(1 for piece in pieces if not piece.quotable),
    )
    return ConflictScreen(
        component_id=component.component_id,
        screened=True,
        pieces=tuple(pieces),
        relations=relations,
        agreeing_pairs=agreeing,
        counts=counts,
    )


__all__ = [
    "ConflictRelation",
    "ConflictScreen",
    "Impact",
    "Piece",
    "Relation",
    "ScreenCounts",
    "scope_words",
    "screen_component",
]

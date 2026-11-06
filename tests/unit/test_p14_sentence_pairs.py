"""P14 sentence pairs (ARCHITECTURE §14 'Sentence pairs', §16.2 and §16.3; D133).

Units and pages are hand-written, so every expected quote and offset is known. The retrieval results are hand-built too:
selection needs only the evidence IDs, the flags and ``via``. The end-to-end cases are in
tests/integration/test_p14_sentence_pairs.py.
"""

from __future__ import annotations

from app.conflict.claims import claims_of
from app.conflict.config import load_conflict_config
from app.conflict.detector import ConflictRelation, Impact, Piece, compare_pieces
from app.document_structure.models import ContentType
from app.evidence import ComponentStatus, select_candidates
from app.evidence.values import find_values
from app.question_processing import analyze
from app.question_processing.analysis import QuestionType
from app.retrieval.bm25 import ContextRef, RetrievalCandidate, RetrievalResult
from tests.fixtures.store_records import make_unit

DOC = "doc-" + "9" * 16
CONFIG = load_conflict_config()

TARGET = "The Bluetooth security guide is listed in the catalogue."
DATE_SENTENCE = "Updates are included as of January 19, 2022."
WHEN_QUESTION = "When were the updates to the Bluetooth security guide included?"


def _unit(ordinal, page_text, spans, *, content_type=ContentType.PARAGRAPH, derived=False):
    return make_unit(DOC, 1, ordinal, content_type, page_text, spans, derived=derived)


def _whole(ordinal, text):
    return _unit(ordinal, text, [(0, len(text))])


def _retrieval(query, units):
    candidates = []
    for rank, unit in enumerate(units, start=1):
        candidates.append(
            RetrievalCandidate(
                rank=rank,
                evidence_id=unit.evidence_id,
                pdf_page=unit.pdf_page,
                ordinal=unit.ordinal,
                content_type=unit.content_type.value,
                derived=unit.derived,
                extraction_quality=unit.extraction_quality.value,
                via="original",
                rule_ids=(),
                exact_terms=(),
                bm25_raw=-1.0 - rank,
                duplicate_evidence_ids=(),
                context=ContextRef(before=(), after=(), section_heading_id=None, parent_heading_id=None),
            )
        )
    # The trace is not read by selection, so it is left out here.
    return RetrievalResult(document_id=DOC, query=query, candidates=tuple(candidates), trace=None)  # type: ignore[arg-type]


def _select(question, units):
    """Select for one question over the given units, all of which the retrieval returned for its query."""
    analysis = analyze(question)
    component = analysis.components[0]
    retrieved = {component.component_id: _retrieval(component.retrieval_query, units)}
    lookup = {unit.evidence_id: unit for unit in units}
    selection = select_candidates(analysis, retrieved, lookup)
    return selection.components[0]


def _assert_quotes_are_page_slices(page_text, component):
    for candidate in component.candidates:
        assert page_text[candidate.page_start : candidate.page_end] == candidate.quote
        if candidate.answer_span is not None:
            assert page_text[candidate.answer_page_start : candidate.answer_page_end] == candidate.answer_span
            assert candidate.answer_span in candidate.quote


# --- Selection: the neighbour is read, and only the neighbour inside one unit ---------------------------------------


def test_the_neighbouring_sentence_is_read_and_the_quote_is_the_verbatim_pair():
    page = f"{TARGET} {DATE_SENTENCE}"
    component = _select(WHEN_QUESTION, [_whole(1, page)])
    assert component.status == ComponentStatus.CANDIDATES
    assert len(component.candidates) == 1
    candidate = component.candidates[0]
    assert candidate.granularity == "sentence_pair"
    assert candidate.quote == page
    assert candidate.answer_span == "January 19, 2022"
    assert candidate.answer_kind == "date"
    assert candidate.rule_id == "when.date_or_period.v1"
    _assert_quotes_are_page_slices(page, component)


def test_a_value_two_sentences_away_is_not_linked():
    middle = "The catalogue is printed each year."
    page = f"{TARGET} {middle} {DATE_SENTENCE}"
    component = _select(WHEN_QUESTION, [_whole(1, page)])
    assert component.status == ComponentStatus.NO_CANDIDATES
    assert component.candidates == ()


def test_a_pair_is_not_built_when_one_of_its_sentences_is_already_a_candidate():
    page = "The Bluetooth security guide, with updates, is listed as of January 19, 2022. It is printed in March 3, 2023."
    component = _select(WHEN_QUESTION, [_whole(1, page)])
    assert len(component.candidates) == 1
    candidate = component.candidates[0]
    assert candidate.granularity == "sentence"
    assert candidate.quote == "The Bluetooth security guide, with updates, is listed as of January 19, 2022."
    _assert_quotes_are_page_slices(page, component)


def test_a_neighbour_with_a_second_value_leaves_no_single_span():
    neighbour = "Updates are included as of January 19, 2022, and the next review is on March 3, 2023."
    page = f"{TARGET} {neighbour}"
    component = _select(WHEN_QUESTION, [_whole(1, page)])
    assert len(component.candidates) == 1
    candidate = component.candidates[0]
    assert candidate.granularity == "sentence_pair"
    assert candidate.answer_span is None
    assert "multiple_values" in candidate.flags
    _assert_quotes_are_page_slices(page, component)


def test_a_pair_that_crosses_a_join_between_source_spans_is_dropped_with_a_record():
    page = f"{TARGET} {DATE_SENTENCE}"
    split = len(TARGET)
    unit = _unit(1, page, [(0, split), (split + 1, len(page))])
    component = _select(WHEN_QUESTION, [unit])
    assert component.candidates == ()
    reasons = [(item.evidence_id, item.reason) for item in component.dropped]
    assert reasons == [(unit.evidence_id, "crosses_source_span")]


def test_what_questions_keep_single_sentences_and_read_no_neighbour():
    page = f"{TARGET} {DATE_SENTENCE}"
    component = _select("What updates are included in the Bluetooth security guide?", [_whole(1, page)])
    assert component.question_type == QuestionType.WHAT
    assert component.status == ComponentStatus.NO_CANDIDATES
    assert component.candidates == ()


def test_a_value_cut_by_the_boundary_between_two_sentences_builds_no_pair(monkeypatch):
    # The sentence splitter never cuts a value, so the cut is forced here, to check the guard of the rule.
    from app.evidence import selection

    neighbour = "Updates are included as of January 19, 2022."
    page = f"{TARGET} {neighbour}"
    boundary = len(TARGET)

    def cut_value(question_type, text, count_nouns):
        return [(boundary - 2, boundary + 4)] if text.startswith(TARGET) else []

    monkeypatch.setattr(selection, "_counted_offsets", cut_value)
    component = _select(WHEN_QUESTION, [_whole(1, page)])
    assert component.candidates == ()


def test_whether_pairs_read_the_permission_marker_in_the_neighbour():
    neighbour = "Staff must not share updates before approval."
    page = f"{TARGET} {neighbour}"
    component = _select("Are updates to the Bluetooth security guide permitted?", [_whole(1, page)])
    assert len(component.candidates) == 1
    candidate = component.candidates[0]
    assert candidate.granularity == "sentence_pair"
    assert candidate.answer_span == "must not"
    assert candidate.negated is True
    _assert_quotes_are_page_slices(page, component)


# --- The screen: a pair is a piece, and pieces that share a sentence are never compared ------------------------------


def _piece(text, *, n, span, scope=frozenset(), question_type=QuestionType.HOW_MANY):
    values = find_values(text, count_nouns=("course", "due"))
    claims = claims_of(question_type, values, (), CONFIG)
    return Piece(
        evidence_id=f"doc-{'b' * 16}:p0001:u{n:04d}",
        pdf_page=1,
        ordinal=n,
        printed_page=None,
        section_id="s1",
        heading_text="",
        content_type="paragraph",
        extraction_quality="verified",
        derived=False,
        text=text,
        page_start=0,
        page_end=len(text),
        claims=claims,
        scope=scope,
        dates=frozenset(),
        supersession_phrase=None,
        unit_span=span,
    )


def test_a_pair_with_a_value_conflicts_with_a_differing_sentence_elsewhere():
    pair_text = "The course fee is paid in advance. It is due after 30 days."
    pair = _piece(pair_text, n=1, span=(0, len(pair_text)))
    other = _piece("The course fee is due after 45 days.", n=2, span=(0, 37))
    relations, _ = compare_pieces([pair, other])
    assert len(relations) == 1
    relation = relations[0]
    assert relation.kind == ConflictRelation.CONFIRMED_INCOMPATIBLE
    assert relation.impact == Impact.CONFLICT
    assert (relation.first, relation.second) == (0, 1)


def test_a_pair_is_never_compared_with_its_own_member_sentence():
    member_text = "The course fee is 30 days."
    pair_text = "The course fee is 30 days. It is due after 45 days."
    member = _piece(member_text, n=1, span=(0, len(member_text)))
    pair = _piece(pair_text, n=1, span=(0, len(pair_text)))
    relations, agreeing = compare_pieces([member, pair])
    assert relations == ()
    assert agreeing == 0


def test_two_pairs_that_share_a_sentence_are_not_compared_with_each_other():
    first_text = "The course fee is paid in advance. It is due after 30 days."
    second_text = "It is due after 30 days. The course is listed in March 3, 2023."
    overlap_start = first_text.index("It is due")
    first = _piece(first_text, n=1, span=(0, len(first_text)))
    second = _piece(second_text, n=1, span=(overlap_start, overlap_start + len(second_text)))
    relations, agreeing = compare_pieces([first, second])
    assert relations == ()
    assert agreeing == 0


def test_pieces_of_different_units_are_still_compared_as_before():
    relations, _ = compare_pieces(
        [
            _piece("The course fee is due after 30 days.", n=1, span=(0, 37)),
            _piece("The course fee is due after 45 days.", n=2, span=(0, 37)),
        ]
    )
    assert len(relations) == 1
    assert relations[0].kind == ConflictRelation.CONFIRMED_INCOMPATIBLE


"""The relation rules of the conflict screen (ARCHITECTURE §16.3, D71). Pieces are built directly, so each rule is tested on
its own, without a store. The end-to-end behaviour is in tests/integration/test_p7_decision.py."""

from __future__ import annotations

import pytest

from app.conflict.claims import claims_of
from app.conflict.config import load_conflict_config
from app.conflict.detector import ConflictRelation, Impact, Piece, compare_pieces
from app.evidence.values import find_values
from app.question_processing.analysis import QuestionType

CONFIG = load_conflict_config()


def piece(
    text: str,
    *,
    n: int = 1,
    scope: frozenset[str] = frozenset(),
    dates: frozenset[str] = frozenset(),
    quality: str = "verified",
    derived: bool = False,
    supersession: str | None = None,
    quotable: bool = True,
    question_type: QuestionType = QuestionType.HOW_MANY,
) -> Piece:
    values = find_values(text, count_nouns=("limit", "loans"))
    claims = claims_of(question_type, values, (), CONFIG)
    return Piece(
        evidence_id=f"doc-{'a' * 16}:p0001:u{n:04d}",
        pdf_page=1,
        ordinal=n,
        printed_page=None,
        section_id="s1",
        heading_text="",
        content_type="paragraph",
        extraction_quality=quality,
        derived=derived,
        text=text,
        page_start=0 if quotable else None,
        page_end=len(text) if quotable else None,
        claims=claims,
        scope=scope,
        dates=dates,
        supersession_phrase=supersession,
    )


def only_relation(pieces):
    relations, agreeing = compare_pieces(pieces)
    assert agreeing >= 0
    assert len(relations) == 1, relations
    return relations[0]


def test_equal_values_agree_and_record_no_relation():
    relations, agreeing = compare_pieces([piece("The limit is 30 days."), piece("The limit is 30 days.", n=2)])
    assert relations == ()
    assert agreeing == 1


def test_different_values_with_the_same_scope_and_no_dates_are_a_confirmed_conflict():
    relation = only_relation([piece("The limit is 30 days."), piece("The limit is 45 days.", n=2)])
    assert relation.kind == ConflictRelation.CONFIRMED_INCOMPATIBLE
    assert relation.impact == Impact.CONFLICT
    assert (relation.first, relation.second) == (0, 1)
    assert "30 days" in relation.reason and "45 days" in relation.reason


def test_a_confirmed_conflict_with_a_flagged_passage_is_a_source_problem_not_a_conflict():
    relation = only_relation([piece("The limit is 30 days."), piece("The limit is 45 days.", n=2, quality="warning")])
    assert relation.kind == ConflictRelation.CONFIRMED_INCOMPATIBLE
    assert relation.impact == Impact.SOURCE


def test_a_generated_table_row_can_show_a_difference_but_never_confirm_one():
    relation = only_relation([piece("The limit is 30 days."), piece("The limit is 45 days.", n=2, derived=True)])
    assert relation.kind == ConflictRelation.POTENTIAL_DISCREPANCY
    assert relation.impact == Impact.AMBIGUOUS


@pytest.mark.parametrize("first_scope, second_scope", [(frozenset({"staff"}), frozenset()), (frozenset(), frozenset({"visitors"}))])
def test_numbers_that_differ_across_scopes_are_never_called_a_conflict(first_scope, second_scope):
    relation = only_relation(
        [piece("The limit is 30 days.", scope=first_scope), piece("The limit is 45 days.", n=2, scope=second_scope)]
    )
    assert relation.kind == ConflictRelation.DIFFERENT_SCOPE
    assert relation.impact == Impact.AMBIGUOUS
    assert "not called a conflict" in relation.reason


def test_different_dates_make_a_dated_change_that_depends_on_the_date():
    relation = only_relation(
        [
            piece("From 1 January 2026 the limit is 45 days.", dates=frozenset({"1 january 2026"})),
            piece("Until 1 January 2025 the limit is 30 days.", n=2, dates=frozenset({"1 january 2025"})),
        ]
    )
    assert relation.kind == ConflictRelation.DATED_CHANGE
    assert relation.impact == Impact.AMBIGUOUS


def test_a_dated_passage_against_an_undated_one_is_a_potential_discrepancy():
    relation = only_relation(
        [
            piece("From 1 January 2026 the limit is 30 days.", dates=frozenset({"1 january 2026"})),
            piece("The limit is 45 days.", n=2),
        ]
    )
    assert relation.kind == ConflictRelation.POTENTIAL_DISCREPANCY
    assert relation.impact == Impact.AMBIGUOUS


def test_the_same_date_with_different_values_and_the_same_scope_is_a_confirmed_conflict():
    relation = only_relation(
        [
            piece("From 1 January 2026 the limit is 30 days.", dates=frozenset({"1 january 2026"})),
            piece("From 1 January 2026 the limit is 45 days.", n=2, dates=frozenset({"1 january 2026"})),
        ]
    )
    assert relation.kind == ConflictRelation.CONFIRMED_INCOMPATIBLE


def test_a_stated_supersession_is_reported_as_one_and_is_a_conflict_when_both_are_clean():
    relation = only_relation(
        [piece("The limit is 30 days."), piece("The limit is replaced by 45 days.", n=2, supersession="replaced by")]
    )
    assert relation.kind == ConflictRelation.EXPLICIT_SUPERSESSION
    assert relation.impact == Impact.CONFLICT
    assert "replaced by" in relation.reason


def test_a_supersession_with_a_flagged_passage_is_a_source_problem():
    relation = only_relation(
        [
            piece("The limit is 30 days."),
            piece("The limit is replaced by 45 days.", n=2, supersession="replaced by", quality="unverified"),
        ]
    )
    assert relation.impact == Impact.SOURCE


def test_the_supersession_rule_is_checked_before_the_date_and_scope_rules():
    relation = only_relation(
        [
            piece("From 1 January 2026 the limit is 30 days.", dates=frozenset({"1 january 2026"})),
            piece(
                "From 1 January 2025 the limit is replaced by 45 days.",
                n=2,
                dates=frozenset({"1 january 2025"}),
                supersession="replaced by",
            ),
        ]
    )
    assert relation.kind == ConflictRelation.EXPLICIT_SUPERSESSION


def test_quantities_from_different_families_are_not_compared():
    relations, agreeing = compare_pieces([piece("The limit is 30 days."), piece("The fee is 5 USD.", n=2)])
    assert relations == ()
    assert agreeing == 0


def test_pieces_without_claims_are_not_compared():
    relations, agreeing = compare_pieces([piece("The limit is 30 days."), piece("The limit is high.", n=2)])
    assert relations == ()
    assert agreeing == 0


def test_two_sentences_of_one_unit_are_compared_with_each_other():
    first = piece("The limit is 30 days and the limit is 45 days.", n=1)
    relations, _ = compare_pieces([first])
    assert relations == (), "one piece is never compared with itself"
    second = piece("The limit is 30 days.", n=1)
    relations, _ = compare_pieces([first, second])
    assert len(relations) == 1 and relations[0].kind == ConflictRelation.CONFIRMED_INCOMPATIBLE


def test_a_piece_knows_whether_it_is_clean_and_quotable():
    assert piece("The limit is 30 days.").clean is True
    assert piece("The limit is 30 days.", quality="warning").clean is False
    assert piece("The limit is 30 days.", derived=True).clean is False
    assert piece("The limit is 30 days.", quotable=False).quotable is False

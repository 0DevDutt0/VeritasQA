"""The overall status of a question (ARCHITECTURE §16.5, SPEC §9): one test per cell of the precedence table, including
the compound cases, and the mapping from relations to reason codes (§16.4)."""

from __future__ import annotations

import pytest

from app.conflict.detector import ConflictRelation
from app.decision.response import DecisionStatus, ReasonCode, aggregate_status, relation_reason_code

A = DecisionStatus.ANSWERED
I = DecisionStatus.INSUFFICIENT_EVIDENCE  # noqa: E741 - a table label, read as "insufficient"
Q = DecisionStatus.AMBIGUOUS_QUERY
C = DecisionStatus.CONFLICT
S = DecisionStatus.SOURCE_UNVERIFIED


@pytest.mark.parametrize(
    "components, expected",
    [
        ([A], A),
        ([A, A], A),
        ([A, I], DecisionStatus.PARTIAL),
        ([A, Q], DecisionStatus.PARTIAL),
        ([A, C], DecisionStatus.PARTIAL),
        ([A, S], DecisionStatus.PARTIAL),
        ([I], I),
        ([Q], Q),
        ([S], S),
        ([C], C),
        ([I, I], I),
        ([Q, I], Q),
        ([S, Q], S),
        ([S, I], S),
        ([C, S], C),
        ([C, Q, I], C),
        ([S, Q, I], S),
        ([A, C, S, Q, I], DecisionStatus.PARTIAL),
    ],
)
def test_the_overall_status_follows_the_precedence_table(components, expected):
    assert aggregate_status(components) == expected


def test_no_components_is_a_programming_error_not_an_abstention():
    with pytest.raises(ValueError, match="at least one component"):
        aggregate_status([])


def test_partial_is_an_overall_status_and_never_a_component_status():
    with pytest.raises(ValueError, match="no precedence rule"):
        aggregate_status([DecisionStatus.PARTIAL])


@pytest.mark.parametrize(
    "relation, code",
    [
        (ConflictRelation.CONFIRMED_INCOMPATIBLE, ReasonCode.CONFLICT_CONFIRMED),
        (ConflictRelation.EXPLICIT_SUPERSESSION, ReasonCode.CONFLICT_SUPERSESSION),
        (ConflictRelation.DIFFERENT_SCOPE, ReasonCode.SCOPE_DIFFERS),
        (ConflictRelation.DATED_CHANGE, ReasonCode.DATE_DIFFERS),
        (ConflictRelation.POTENTIAL_DISCREPANCY, ReasonCode.POTENTIAL_DISCREPANCY),
        (ConflictRelation.SAME_VALUE, None),
    ],
)
def test_each_relation_contributes_its_reason_code(relation, code):
    assert relation_reason_code(relation) == code


def test_every_status_and_reason_code_has_a_plain_value():
    assert {status.value for status in DecisionStatus} == {
        "ANSWERED",
        "INSUFFICIENT_EVIDENCE",
        "AMBIGUOUS_QUERY",
        "CONFLICT",
        "SOURCE_UNVERIFIED",
        "PARTIAL",
    }
    assert all(code.value == code.value.lower() for code in ReasonCode)

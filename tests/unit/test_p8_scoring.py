"""Scoring of hand-built responses (ARCHITECTURE §17.6 to §17.11; D78, D80, D81, D82, D83).

Each response is built by hand, so every outcome and every retrieval number is worked out in the test, not read from
the engine. The page used here holds two sentences, B and S, so that one page can carry two gold quotes.
"""

import math

import pytest

from app.evaluation.gold import GoldRecord
from app.evaluation.scoring import (
    ObservedComponent,
    ObservedEvidence,
    ObservedResponse,
    ObservedRetrieval,
    ObservedSpan,
    build_metrics,
    score_record,
)

B = "The limit for loans is 30 days after approval."
S = "Staff may share the guide with visitors."
PAGE = f"{B} {S}"
S_START = len(B) + 1
UNITS = {"e1": (1, B), "e2": (1, S)}
PAGES = {1: PAGE}
E1 = ObservedEvidence("e1", 1, B, 0, len(B), frozenset({1}))
E2 = ObservedEvidence("e2", 1, S, S_START, S_START + len(S), frozenset({2}))
SPAN_30 = ObservedSpan("30 days", "e1", 1, 1, PAGE.index("30 days"), PAGE.index("30 days") + len("30 days"))


def gold(status, evidence=(), answers=(), record_id="r1", category="direct_fact") -> GoldRecord:
    return GoldRecord.model_validate(
        {
            "record_id": record_id,
            "question": "How many days is the limit for loans?",
            "category": category,
            "source": "synthetic",
            "split": "dev",
            "annotator": "test",
            "expected_status": status,
            "evidence": list(evidence),
            "answers": list(answers),
        }
    )


def comp(index, accepted, evidence_ids=(), verified=None) -> ObservedComponent:
    verified_ids = tuple(evidence_ids) if verified is None else tuple(verified)
    return ObservedComponent(index, accepted, tuple(evidence_ids), frozenset(verified_ids))


def obs(components, *, status="ANSWERED", spans=(), evidence=(), retrieval=None, question_type="how_many"):
    if retrieval is None:
        retrieval = [ObservedRetrieval(c.index, 50, ((1, "e1"),)) for c in components]
    return ObservedResponse(
        status=status,
        question_type=question_type if len(components) == 1 else "compound",
        components=tuple(components),
        spans=tuple(spans),
        evidence=tuple(evidence),
        retrieval=tuple(retrieval),
    )


B_ANSWER = [{"component": 1, "pdf_page": 1, "quote": B}]
S_EVIDENCE = [{"component": 1, "pdf_page": 1, "quote": S}]
THIRTY = [{"component": 1, "text": "30 days"}]


def test_a_correct_span_on_gold_evidence_is_a_correct_answer():
    score = score_record(
        gold("ANSWERED", B_ANSWER, THIRTY),
        obs([comp(1, True, ("e1",))], spans=[SPAN_30], evidence=[E1]),
        UNITS,
        PAGES,
    )
    assert score.outcome == "correct_answer"
    assert score.components[0].correct is True
    assert score.answer_items[0].exact is True
    assert score.span_checks == (True,)
    assert score.quote_checks == (True,)


def test_a_wrong_answer_text_on_gold_evidence_is_an_incorrect_answer():
    wrong = [{"component": 1, "text": "approval"}]
    score = score_record(
        gold("ANSWERED", B_ANSWER, wrong),
        obs([comp(1, True, ("e1",))], spans=[SPAN_30], evidence=[E1]),
        UNITS,
        PAGES,
    )
    assert score.outcome == "incorrect_answer"
    assert score.components[0].correct is False


def test_a_supported_passage_without_gold_answers_is_a_correct_answer():
    s_for_component_one = ObservedEvidence("e2", 1, S, S_START, S_START + len(S), frozenset({1}))
    score = score_record(
        gold("ANSWERED", S_EVIDENCE),
        obs([comp(1, True, ("e2",))], evidence=[s_for_component_one]),
        UNITS,
        PAGES,
    )
    assert score.outcome == "correct_answer"


def test_no_accepted_component_on_an_answerable_record_is_an_incorrect_abstention():
    score = score_record(
        gold("ANSWERED", B_ANSWER, THIRTY),
        obs([comp(1, False)], status="INSUFFICIENT_EVIDENCE"),
        UNITS,
        PAGES,
    )
    assert score.outcome == "incorrect_abstention"
    assert score.accepted is False


def test_no_accepted_component_on_an_unanswerable_record_is_a_correct_abstention():
    score = score_record(
        gold("INSUFFICIENT_EVIDENCE"),
        obs([comp(1, False)], status="INSUFFICIENT_EVIDENCE"),
        UNITS,
        PAGES,
    )
    assert score.outcome == "correct_abstention"


def test_an_accepted_component_on_an_unanswerable_record_is_a_false_acceptance():
    score = score_record(
        gold("INSUFFICIENT_EVIDENCE"),
        obs([comp(1, True, ("e1",))], evidence=[E1]),
        UNITS,
        PAGES,
    )
    assert score.outcome == "false_acceptance"
    assert score.components[0].correct is False


def test_a_missing_component_on_a_fully_answerable_record_is_an_incomplete_answer():
    record = gold(
        "ANSWERED",
        [
            {"component": 1, "pdf_page": 1, "quote": B},
            {"component": 2, "pdf_page": 1, "quote": S},
        ],
        THIRTY,
    )
    score = score_record(
        record,
        obs([comp(1, True, ("e1",)), comp(2, False)], spans=[SPAN_30], evidence=[E1], status="PARTIAL"),
        UNITS,
        PAGES,
    )
    assert score.outcome == "incomplete_answer"


def test_a_wrong_accepted_component_makes_a_partial_response_incorrect_even_when_another_part_is_right():
    # Component 1 is answerable and correct. Component 2 has no gold evidence, yet it was accepted.
    record = gold("PARTIAL", B_ANSWER, THIRTY)
    score = score_record(
        record,
        obs(
            [comp(1, True, ("e1",)), comp(2, True, ("e2",))],
            status="PARTIAL",
            spans=[SPAN_30],
            evidence=[E1, E2],
        ),
        UNITS,
        PAGES,
    )
    assert score.components[0].correct is True
    assert score.components[1].correct is False
    assert score.outcome == "incorrect_answer"


def test_a_correct_partial_response_is_a_correct_answer():
    record = gold("PARTIAL", B_ANSWER, THIRTY)
    score = score_record(
        record,
        obs([comp(1, True, ("e1",)), comp(2, False)], status="PARTIAL", spans=[SPAN_30], evidence=[E1]),
        UNITS,
        PAGES,
    )
    assert score.outcome == "correct_answer"


def test_retrieval_hits_credits_and_first_ranks_for_two_gold_quotes():
    # Gold quotes B and S are on page 1. Ranks: 1 holds S, 2 holds nothing, 3 holds B, 4 holds S again.
    units = {
        "a": (1, f"intro {S}"),
        "x": (1, "other words"),
        "b": (1, f"{B} more"),
        "a2": (1, f"{S} again"),
    }
    record = gold("ANSWERED", [{"component": 1, "pdf_page": 1, "quote": B}, {"component": 1, "pdf_page": 1, "quote": S}])
    score = score_record(
        record,
        obs(
            [comp(1, True, ("b",))],
            evidence=[],
            retrieval=[ObservedRetrieval(1, 50, ((1, "a"), (2, "x"), (3, "b"), (4, "a2")))],
        ),
        units,
        PAGES,
    )
    measure = score.retrieval[0]
    assert measure.first_ranks == (3, 1)
    assert measure.hits == (True, False, True, True)
    assert measure.credits == (True, False, True, False)


def test_retrieval_metrics_match_the_hand_computed_values():
    units = {
        "a": (1, f"intro {S}"),
        "x": (1, "other words"),
        "b": (1, f"{B} more"),
        "a2": (1, f"{S} again"),
    }
    record = gold("ANSWERED", [{"component": 1, "pdf_page": 1, "quote": B}, {"component": 1, "pdf_page": 1, "quote": S}])
    score = score_record(
        record,
        obs(
            [comp(1, True, ("b",))],
            retrieval=[ObservedRetrieval(1, 50, ((1, "a"), (2, "x"), (3, "b"), (4, "a2")))],
        ),
        units,
        PAGES,
    )
    block = build_metrics([score])["retrieval"]
    assert block["measures"] == 1
    # The reported depths are 1, 5, 10 and 50. The four entries are all inside depth 5.
    assert block["recall_at_1"]["value"] == pytest.approx(0.5)
    assert block["recall_at_5"]["value"] == pytest.approx(1.0)
    assert block["precision_at_1"]["value"] == pytest.approx(1.0)
    assert block["precision_at_5"]["value"] == pytest.approx(3 / 5)
    assert block["ndcg_at_1"]["value"] == pytest.approx(1.0)
    assert block["ndcg_at_5"]["value"] == pytest.approx((1 + 1 / math.log2(4)) / (1 + 1 / math.log2(3)))
    assert block["mrr"]["value"] == pytest.approx(1.0)
    assert block["recall_at_5"]["n"] == 1


def test_a_depth_the_engine_did_not_search_is_not_reported():
    score = score_record(
        gold("ANSWERED", [{"component": 1, "pdf_page": 1, "quote": B}]),
        obs([comp(1, True, ("e1",))], retrieval=[ObservedRetrieval(1, 2, ((1, "e1"),))]),
        UNITS,
        PAGES,
    )
    block = build_metrics([score])["retrieval"]
    assert block["recall_at_1"]["n"] == 1
    assert block["recall_at_5"]["n"] == 0
    assert block["recall_at_5"]["value"] is None


def test_a_hit_on_another_page_is_not_counted():
    score = score_record(
        gold("ANSWERED", [{"component": 1, "pdf_page": 1, "quote": S}]),
        obs([comp(1, False)], retrieval=[ObservedRetrieval(1, 50, ((1, "a"),))]),
        {"a": (2, S)},
        PAGES,
    )
    assert score.retrieval[0].hits == (False,)
    assert score.retrieval[0].first_ranks == (None,)


def test_a_quote_split_across_two_units_is_a_hit_for_neither():
    score = score_record(
        gold("ANSWERED", [{"component": 1, "pdf_page": 1, "quote": S}]),
        obs([comp(1, False)], retrieval=[ObservedRetrieval(1, 50, ((1, "a"), (2, "b")))]),
        {"a": (1, "Staff may share"), "b": (1, "the guide with visitors.")},
        PAGES,
    )
    assert score.retrieval[0].hits == (False, False)


def test_the_quotation_and_span_checks_read_the_page_at_the_stored_offsets():
    wrong_offsets = ObservedEvidence("e2", 1, S, 0, len(S), frozenset({1}))
    wrong_span = ObservedSpan("30 days", "e1", 1, 1, 0, 7)
    score = score_record(
        gold("ANSWERED", B_ANSWER, THIRTY),
        obs([comp(1, True, ("e1",))], spans=[wrong_span], evidence=[wrong_offsets]),
        UNITS,
        PAGES,
    )
    assert score.quote_checks == (False,)
    assert score.span_checks == (False,)


def test_an_accepted_component_without_an_accepted_verification_is_unsupported():
    score = score_record(
        gold("ANSWERED", B_ANSWER, THIRTY),
        obs([ObservedComponent(1, True, ("e1",), frozenset())], spans=[SPAN_30], evidence=[E1]),
        UNITS,
        PAGES,
    )
    assert score.components[0].unsupported is True


def test_an_empty_denominator_in_the_breakdown_is_none():
    score = score_record(
        gold("ANSWERED", B_ANSWER, THIRTY, category="numeric_date"),
        obs([comp(1, True, ("e1",))], spans=[SPAN_30], evidence=[E1]),
        UNITS,
        PAGES,
    )
    metrics = build_metrics([score])
    assert metrics["outcomes"]["rates"]["false_acceptance_rate"]["value"] is None
    assert metrics["outcomes"]["rates"]["false_acceptance_rate"]["n"] == 0
    assert set(metrics["breakdown"]["category"]) == {"numeric_date"}
    assert set(metrics["breakdown"]["question_type"]) == {"how_many"}


def test_the_risk_curve_orders_accepted_records_by_their_best_rank():
    correct = score_record(
        gold("ANSWERED", B_ANSWER, THIRTY, record_id="a-correct"),
        obs([comp(1, True, ("e1",))], spans=[SPAN_30], evidence=[E1]),
        UNITS,
        PAGES,
    )
    wrong = score_record(
        gold("INSUFFICIENT_EVIDENCE", record_id="b-wrong"),
        obs([comp(1, True, ("e1",))], evidence=[E1], retrieval=[ObservedRetrieval(1, 50, ((2, "e1"), (1, "e2")))]),
        UNITS,
        PAGES,
    )
    points = build_metrics([wrong, correct])["risk_coverage"]["points"]
    assert [point["accepted"] for point in points] == [1, 2]
    assert points[0]["errors"] == 0
    assert points[1]["errors"] == 1
    assert points[1]["risk"] == pytest.approx(0.5)

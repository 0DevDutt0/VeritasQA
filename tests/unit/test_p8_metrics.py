"""Hand-computed values for each P8a metric (ARCHITECTURE §17.7 to §17.11; D79 to D83).

The expected numbers are worked out by hand in each test. None of them is read from the code under test.
"""

import math

import pytest

from app.evaluation.metrics import (
    Z_95,
    mean_of,
    ndcg_at_k,
    precision_at_k,
    rate,
    reciprocal_rank,
    recall_at_k,
    risk_coverage,
    token_f1,
    wilson_interval,
    exact_match,
)


def test_wilson_interval_for_zero_of_ten():
    low, high = wilson_interval(0, 10)
    assert low == 0.0
    assert high == pytest.approx(0.27753, abs=1e-4)


def test_wilson_interval_for_five_of_ten():
    low, high = wilson_interval(5, 10)
    assert low == pytest.approx(0.23659, abs=1e-4)
    assert high == pytest.approx(0.76341, abs=1e-4)


def test_wilson_interval_for_ten_of_ten_is_clipped_to_one():
    low, high = wilson_interval(10, 10)
    assert low == pytest.approx(0.72247, abs=1e-4)
    assert high == pytest.approx(1.0)
    assert high <= 1.0


def test_wilson_interval_for_one_of_one():
    low, high = wilson_interval(1, 1)
    assert low == pytest.approx(0.20654, abs=1e-4)
    assert high == 1.0


def test_wilson_interval_rejects_an_empty_sample():
    with pytest.raises(ValueError):
        wilson_interval(0, 0)


def test_a_rate_over_no_records_is_none_and_never_zero():
    empty = rate(0, 0)
    assert empty.value is None
    assert empty.low is None and empty.high is None
    assert empty.n == 0


def test_a_rate_carries_its_count_and_interval():
    observed = rate(5, 10)
    assert observed.value == 0.5
    assert observed.n == 10
    assert observed.low == pytest.approx(0.23659, abs=1e-4)


def test_a_rate_refuses_successes_above_n():
    with pytest.raises(ValueError):
        rate(3, 2)


def test_zero_successes_out_of_two_gives_zero_with_its_interval():
    observed = rate(0, 2)
    assert observed.value == 0.0
    assert observed.low == 0.0
    assert observed.high == pytest.approx(0.65770, abs=1e-4)
    assert observed.n == 2


def test_the_z_value_is_the_standard_normal_quantile_for_95_percent():
    assert Z_95 == pytest.approx(1.959963984540054)
    assert math.isclose(Z_95, 1.96, abs_tol=0.001)


def test_a_mean_skips_undefined_values_and_reports_its_count():
    observed = mean_of([1.0, None, 0.0])
    assert observed.n == 2
    assert observed.value == 0.5


def test_a_mean_over_nothing_is_none():
    observed = mean_of([None, None])
    assert observed.n == 0
    assert observed.value is None


def test_recall_counts_gold_quotes_whose_first_hit_is_within_k():
    first_ranks = (1, 3)
    assert recall_at_k(first_ranks, 1) == 0.5
    assert recall_at_k(first_ranks, 2) == 0.5
    assert recall_at_k(first_ranks, 3) == 1.0


def test_recall_without_gold_quotes_is_none():
    assert recall_at_k((), 5) is None


def test_precision_divides_by_k_even_when_fewer_units_came_back():
    hits = (True, False, True)
    assert precision_at_k(hits, 1) == 1.0
    assert precision_at_k(hits, 2) == 0.5
    assert precision_at_k(hits, 3) == pytest.approx(2 / 3)
    assert precision_at_k(hits, 5) == pytest.approx(2 / 5)


def test_reciprocal_rank_is_one_over_the_first_hit():
    assert reciprocal_rank((False, False, True)) == pytest.approx(1 / 3)
    assert reciprocal_rank((False, False)) == 0.0


def test_ndcg_with_binary_gain_and_one_credit_per_quote():
    # credits at ranks 1 and 3, two gold quotes: DCG = 1 + 1/log2(4); IDCG = 1 + 1/log2(3)
    expected = (1 + 1 / math.log2(4)) / (1 + 1 / math.log2(3))
    assert ndcg_at_k((True, False, True), 2, 3) == pytest.approx(expected)


def test_ndcg_is_one_when_every_quote_is_credited_at_the_top():
    assert ndcg_at_k((True, True), 2, 2) == pytest.approx(1.0)


def test_ndcg_is_zero_when_nothing_is_credited():
    assert ndcg_at_k((False, False), 1, 2) == 0.0


def test_ndcg_without_gold_quotes_is_none():
    assert ndcg_at_k((True,), 0, 1) is None


def test_exact_match_is_whitespace_tolerant_and_case_exact():
    assert exact_match("30 days", "30\ndays")
    assert not exact_match("30 Days", "30 days")
    assert not exact_match("30 days.", "30 days")


def test_token_f1_for_a_prefix_of_the_gold_answer():
    # prediction: 2 tokens, gold: 4 tokens, 2 shared. Precision 1.0, recall 0.5, F1 2/3.
    assert token_f1("30 days", "30 days after approval") == pytest.approx(2 / 3)


def test_token_f1_for_identical_texts_is_one():
    assert token_f1("30 days", "30 days") == 1.0


def test_token_f1_when_one_side_has_no_word_tokens_compares_the_texts():
    assert token_f1("--", "--") == 1.0
    assert token_f1("--", "x") == 0.0


def test_risk_coverage_orders_by_key_and_counts_errors_in_prefixes():
    items = [((1, "b"), False), ((1, "a"), True), ((2, "c"), False)]
    points = risk_coverage(items, 4)
    assert [p.accepted for p in points] == [1, 2, 3]
    assert [p.coverage for p in points] == [0.25, 0.5, 0.75]
    assert [p.errors for p in points] == [1, 1, 1]
    assert points[0].risk == 1.0
    assert points[1].risk == 0.5
    assert points[2].risk == pytest.approx(1 / 3)


def test_risk_coverage_over_no_records_is_empty():
    assert risk_coverage([], 0) == ()

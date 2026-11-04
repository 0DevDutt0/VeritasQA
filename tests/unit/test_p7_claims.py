"""Claims and their comparison (ARCHITECTURE §16.2): what a piece states, and when two statements can be compared."""

from __future__ import annotations

import pytest

from app.conflict.claims import claims_of, compare, normalize_date, normalize_number
from app.conflict.config import load_conflict_config
from app.conflict.detector import scope_words
from app.evidence.markers import find_markers
from app.evidence.values import find_values
from app.question_processing.analysis import QuestionType

CONFIG = load_conflict_config()


def claims(question_type, text, count_nouns=()):
    values = find_values(text, count_nouns=count_nouns)
    markers = find_markers(text, "permission") if question_type == QuestionType.WHETHER else ()
    return claims_of(question_type, values, markers, CONFIG)


def one(question_type, text, count_nouns=()):
    found = claims(question_type, text, count_nouns)
    assert len(found) == 1, found
    return found[0]


@pytest.mark.parametrize(
    "text, negative, expected",
    [
        ("1,000", False, "1000"),
        ("3.50", False, "3.5"),
        ("3.5", True, "-3.5"),
        ("0.0", True, "0"),
        ("no digits", False, None),
    ],
)
def test_normalize_number_reads_the_first_number(text, negative, expected):
    assert normalize_number(text, negative) == expected


def test_normalize_date_folds_case_spacing_and_closing_punctuation():
    assert normalize_date("1 January 2026.") == "1 january 2026"
    assert normalize_date("1  January\n2026") == "1 january 2026"


def test_a_when_piece_claims_its_dates_and_periods():
    date = one(QuestionType.WHEN, "The deadline is 1 March 2026.")
    assert (date.kind, date.family, date.value) == ("date", "date", "1 march 2026")
    period = one(QuestionType.WHEN, "The window runs from 1 March 2026 to 31 March 2026.")
    assert (period.kind, period.family) == ("date", "period")


def test_a_how_many_piece_claims_quantities_and_bare_numbers_but_not_dates():
    found = claims(QuestionType.HOW_MANY, "The limit is 30 days, 5 USD and 45, from 1 January 2026.", ("limit",))
    assert [(claim.kind, claim.family) for claim in found] == [("quantity", "time"), ("quantity", "money"), ("bare", "bare")]
    assert found[0].number == "30" and found[0].unit == "day"


def test_percent_and_currency_claims_keep_their_magnitude_word():
    rate, money = claims(QuestionType.HOW_MANY, "The rate is 5% and the cap is $5 million.")
    assert (rate.family, rate.value) == ("percent", "5")
    assert (money.family, money.value, money.unit) == ("money", "5|million", "$")


def test_a_whether_piece_claims_the_polarity_of_each_marker():
    positive = one(QuestionType.WHETHER, "Staff may share the guide.")
    negative = one(QuestionType.WHETHER, "Staff must not share the guide.")
    assert (positive.kind, positive.value) == ("polarity", "positive")
    assert (negative.kind, negative.value) == ("polarity", "negative")


def test_other_question_types_claim_nothing():
    assert claims(QuestionType.WHAT, "The limit is 30 days.") == ()


def test_quantities_are_compared_only_within_a_family():
    thirty = one(QuestionType.HOW_MANY, "It is 30 days.")
    forty_five = one(QuestionType.HOW_MANY, "It is 45 days.")
    month = one(QuestionType.HOW_MANY, "It is 1 month.")
    dollars = one(QuestionType.HOW_MANY, "It is 30 USD.")
    # Every unit that the value parser knows is listed. An unlisted unit arrives as a count noun of the question.
    unlisted = one(QuestionType.HOW_MANY, "It is 30 members.", ("members",))
    assert unlisted.family is None
    assert compare(thirty, thirty) is True
    assert compare(thirty, forty_five) is False
    assert compare(thirty, month) is False, "30 days and 1 month differ; there is no unit conversion"
    assert compare(thirty, dollars) is None, "30 days and 30 USD are not compared"
    assert compare(thirty, unlisted) is False, "an unlisted unit is compared, never skipped"


def test_a_magnitude_word_is_part_of_a_currency_claim():
    billion = one(QuestionType.HOW_MANY, "It is $5 billion.")
    million = one(QuestionType.HOW_MANY, "It is $5 million.")
    bare_five = one(QuestionType.HOW_MANY, "It is $5.")
    assert compare(million, million) is True
    assert compare(million, billion) is False
    assert compare(bare_five, million) is False


def test_a_negative_number_differs_from_its_positive_form():
    negative = one(QuestionType.HOW_MANY, "The change is -3.5 days.")
    positive = one(QuestionType.HOW_MANY, "The change is 3.5 days.")
    assert compare(negative, positive) is False


def test_ranges_are_compared_by_their_text_and_never_as_bare_numbers():
    low = one(QuestionType.HOW_MANY, "It is 3 to 5 days.")
    other = one(QuestionType.HOW_MANY, "It is 3 to 6 days.")
    bare = one(QuestionType.HOW_MANY, "It is 45.")
    assert compare(low, low) is True
    assert compare(low, other) is False
    assert compare(low, bare) is None


def test_a_bare_number_is_compared_by_its_number_with_any_quantity():
    bare_forty_five = one(QuestionType.HOW_MANY, "It is 45.")
    thirty_days = one(QuestionType.HOW_MANY, "It is 30 days.")
    bare_thirty = one(QuestionType.HOW_MANY, "It is 30.")
    assert compare(bare_forty_five, thirty_days) is False
    assert compare(bare_thirty, thirty_days) is True


def test_dates_and_polarity_are_compared_by_their_text():
    march = one(QuestionType.WHEN, "It is due 1 March 2026.")
    march_again = one(QuestionType.WHEN, "It is due 1 March 2026.")
    april = one(QuestionType.WHEN, "It is due 2 March 2026.")
    assert compare(march, march_again) is True
    assert compare(march, april) is False
    thirty = one(QuestionType.HOW_MANY, "It is 30 days.")
    assert compare(march, thirty) is None
    positive = one(QuestionType.WHETHER, "Staff may share the guide.")
    negative = one(QuestionType.WHETHER, "Staff must not share the guide.")
    assert compare(positive, negative) is False
    assert compare(positive, march) is None


def test_scope_words_are_the_words_outside_the_subject_the_values_and_the_vocabulary():
    text = "The limit for loans is 30 days after approval."
    values = find_values(text, count_nouns=("limit", "loans"))
    assert scope_words(text, ("limit", "loans"), values, ()) == frozenset({"approval"})
    staff = "The limit for loans for staff is 45 days."
    staff_values = find_values(staff, count_nouns=("limit", "loans"))
    assert scope_words(staff, ("limit", "loans"), staff_values, ()) == frozenset({"staff"})


def test_scope_words_drop_the_marker_and_the_subject_of_a_permission():
    text = "Staff must not share the guide with visitors."
    markers = find_markers(text, "permission")
    values = find_values(text, count_nouns=("staff",))
    assert scope_words(text, ("staff", "share", "guide", "visitors"), values, markers) == frozenset()

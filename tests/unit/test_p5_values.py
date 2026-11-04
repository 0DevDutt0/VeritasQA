"""P5 value grammar: numbers, units, percentages, currency, dates and periods, with exact spans (D51).

The negative cases matter as much as the positive ones. Each identifier, list or footnote mark that the grammar must
not read as a value is listed here with its reason (ARCHITECTURE §14). Every expected string is written out by hand.
"""

from __future__ import annotations

import pytest

from app.evidence.values import ValueKind, find_values


def _texts(text: str, **kwargs) -> list[str]:
    return [value.text for value in find_values(text, **kwargs)]


def _one(text: str, **kwargs):
    values = find_values(text, **kwargs)
    assert len(values) == 1, [value.text for value in values]
    return values[0]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("The limit is 30 days.", ("30 days", "days")),
        ("The limit is 30 \n\ndays after approval.", ("30 \n\ndays", "days")),
        ("Wait 30-day period.", ("30-day", "day")),
        ("A fee of 5 kg applies.", ("5 kg", "kg")),
        ("Between 3 and 5 years apply.", ("Between 3 and 5 years", "years")),
        ("It takes 3 to 5 days.", ("3 to 5 days", "days")),
    ],
)
def test_a_number_with_a_unit_is_one_value_with_the_unit_label(text, expected):
    value = _one(text)
    assert value.kind == ValueKind.NUMBER
    assert (value.text, value.unit) == expected
    assert text[value.start : value.end] == value.text


def test_a_line_break_may_separate_a_number_from_its_unit_and_the_quote_keeps_it():
    value = _one("The period is at least 30\n\ndays long.")
    assert value.text == "30\n\ndays"
    assert value.unit == "days"


def test_a_unit_must_end_its_word():
    value = _one("The period is 30 dayscare long.")
    assert value.text == "30" and value.unit is None


def test_a_superscript_after_a_unit_is_not_read_as_that_unit():
    value = _one("The area is 3 m².")
    assert value.text == "3" and value.unit is None


@pytest.mark.parametrize(
    "text, kind, text_expected",
    [
        ("Pay $1,000 now.", ValueKind.CURRENCY, "$1,000"),
        ("Pay USD 20 now.", ValueKind.CURRENCY, "USD 20"),
        ("Pay 20 EUR now.", ValueKind.CURRENCY, "20 EUR"),
        ("Pay 15 dollars now.", ValueKind.CURRENCY, "15 dollars"),
        ("About 10% of staff.", ValueKind.PERCENT, "10%"),
        ("About 10 per cent of staff.", ValueKind.PERCENT, "10 per cent"),
    ],
)
def test_currency_and_percentages_are_values_of_their_own_kind(text, kind, text_expected):
    value = _one(text)
    assert value.kind == kind
    assert value.text == text_expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Due on 4 March 2024.", "4 March 2024"),
        ("Due on March 4, 2024.", "March 4, 2024"),
        ("Due in March 2024.", "March 2024"),
        ("Due on 2024-01-31.", "2024-01-31"),
        ("Due on 1st Jan. 2020.", "1st Jan. 2020"),
    ],
)
def test_dates_are_read_in_each_common_form(text, expected):
    value = _one(text)
    assert value.kind == ValueKind.DATE
    assert value.text == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Covered for 2019–2021 only.", "2019–2021"),
        ("Covered from 2019 to 2021 only.", "from 2019 to 2021"),
        ("Covered between 2019 and 2021 only.", "between 2019 and 2021"),
        ("Covered from 1 January 2020 to 31 December 2020.", "from 1 January 2020 to 31 December 2020"),
    ],
)
def test_periods_are_one_value_each(text, expected):
    values = find_values(text)
    assert [value.kind for value in values] == [ValueKind.PERIOD]
    assert values[0].text == expected


def test_the_year_inside_a_period_is_not_read_again_as_a_number():
    assert _texts("Covered from 2019 to 2021 only.") == ["from 2019 to 2021"]


@pytest.mark.parametrize(
    "text, forbidden",
    [
        ("The control is 3.5.2 in the plan.", "3.5"),  # a dotted identifier is not the value 3.5
        ("Section 3.5.2 applies.", "3.5"),
        ("The table lists 1,2,3 as codes.", "2"),  # a list of separated numbers is not a value
        ("Refer to ABC-123 for details.", "123"),  # a hyphen-glued identifier
        ("See SP 800-53 for controls.", "800"),
        ("See SP 800-53 for controls.", "53"),
        ("The time is 10:30 today.", "10"),  # a time of day
        ("This is the 3rd review.", "3"),  # an ordinal glued to its letters
        ("Agencies FISMA,1 the Secretary shall act.", "1"),  # a footnote mark after a letter and a comma
        ("Compliance is required for federal agencies.2 FISMA requires it.", "2"),  # a footnote after a full stop
    ],
)
def test_identifiers_lists_and_footnote_marks_are_not_values(text, forbidden):
    assert forbidden not in _texts(text)


def test_a_dotted_number_is_read_whole_and_never_as_its_prefix():
    # 3.5.2 is an identifier, so only the bare 3.5 at the end of the sentence is a value.
    assert _texts("The rule is 3.5.2, not 3.5.") == ["3.5"]
    assert _texts("The limit is 13.5 mg.") == ["13.5 mg"]
    assert _texts("The limit is 3.55 mg.") == ["3.55 mg"]
    assert _texts("The limit is 3.5 mg.") == ["3.5 mg"]


def test_a_footnote_mark_before_a_unit_is_not_a_value_of_its_own():
    assert [value.text for value in find_values("Fees, FISMA,1 the 30 days apply.")] == ["30 days"]


def test_a_minus_sign_is_part_of_the_value_and_is_recorded():
    value = _one("The change was -5 days.")
    assert value.text == "-5 days"
    assert value.negative is True
    assert "The change was -5 days."[value.start : value.end] == "-5 days"


def test_a_count_noun_from_the_question_gives_a_unit_in_plural_or_singular():
    assert _one("The board has 9 members.", count_nouns=["members"]).unit == "members"
    assert _one("The board has 1 member.", count_nouns=["members"]).unit == "members"


def test_a_word_that_only_starts_like_the_count_noun_is_not_taken():
    assert _one("The board has 9 memberships.", count_nouns=["members"]).unit is None


def test_written_numbers_are_not_values():
    assert find_values("The notice period is three days.") == ()


def test_offsets_are_exact_for_every_value_in_a_mixed_sentence():
    text = (
        "Fees of $1,000 or 10% apply from 4 March 2024 to 3 April 2024 for 30 days, "
        "and 9 members must sign within 2019–2021."
    )
    values = find_values(text, count_nouns=["members"])
    assert [value.kind for value in values] == [
        ValueKind.CURRENCY,
        ValueKind.PERCENT,
        ValueKind.PERIOD,
        ValueKind.NUMBER,
        ValueKind.NUMBER,
        ValueKind.PERIOD,
    ]
    for value in values:
        assert text[value.start : value.end] == value.text


def test_the_same_text_gives_the_same_values_in_the_same_order():
    text = "A 10% fee of 30 days from 4 March 2024, or 3 to 5 years, 9 members, USD 20."
    first = find_values(text, count_nouns=["members"])
    second = find_values(text, count_nouns=["members"])
    assert first == second
    assert [value.start for value in first] == sorted(value.start for value in first)


def test_an_empty_text_has_no_values():
    assert find_values("") == ()


@pytest.mark.parametrize(
    "text, count_nouns",
    [
        ("See Section 3 for the rule.", ["rule"]),
        ("Table 2 members are listed.", ["members"]),
        ("Go to page 5 of the guide.", ["guide"]),
        ("Step 3 days are allowed.", ["days"]),
    ],
)
def test_a_number_after_a_label_word_is_an_identifier_and_not_a_value(text, count_nouns):
    assert [value.text for value in find_values(text, count_nouns=count_nouns)] == []


def test_a_section_number_before_a_capitalised_count_noun_is_not_a_count_value():
    values = find_values("3.2 Risk board assessments", count_nouns=["risk"])
    assert [(value.text, value.unit) for value in values] == [("3.2", None)]


def test_a_lower_case_count_noun_after_a_number_is_the_unit():
    value = _one("The board has 9 members.", count_nouns=["members"])
    assert (value.text, value.unit) == ("9 members", "members")


def test_a_capitalised_count_noun_is_not_a_count_value_even_when_the_number_is_not_dotted():
    # No dotted number and no line start here, so only the capital letter keeps `Members` from counting.
    values = find_values("Quota: 9 Members assigned.", count_nouns=["members"])
    assert [(value.text, value.unit) for value in values] == [("9", None)]


def test_a_number_that_opens_a_line_is_not_read_as_a_count_value():
    values = find_values("Board\n9 members attend.", count_nouns=["members"])
    assert [(value.text, value.unit) for value in values] == [("9", None)]

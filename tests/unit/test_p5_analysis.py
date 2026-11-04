"""P5 question analysis: types, compound splits, subjects, pronouns, comparisons and refusals (SPEC §5; D52, D53).

Every expected type, term and reason below is written out by hand. The tests check the rules, not a parser's output.
"""

from __future__ import annotations

import pytest

from app.question_processing import QuestionError, QuestionType, ValueIntent, analyze


def _types(question: str) -> list[QuestionType]:
    return [component.question_type for component in analyze(question).components]


@pytest.mark.parametrize(
    "question, expected",
    [
        ("What is the maximum loan amount for small businesses?", QuestionType.WHAT),
        ("Who approves the loan?", QuestionType.WHO),
        ("When is the report due?", QuestionType.WHEN),
        ("What is the deadline for the report?", QuestionType.WHEN),
        ("Where is the office located?", QuestionType.WHERE),
        ("How many days after approval must reports be filed?", QuestionType.HOW_MANY),
        ("How much is the fee for gold accounts?", QuestionType.HOW_MANY),
        ("What percentage of staff completed training?", QuestionType.HOW_MANY),
        ("Which forms are required for a loan?", QuestionType.WHICH),
        ("What are the types of approval?", QuestionType.WHICH),
        ("Is it permitted to share data?", QuestionType.WHETHER),
        ("Are visitors allowed in the lab?", QuestionType.WHETHER),
        ("Whether the fee is refundable?", QuestionType.WHETHER),
        ("Under what conditions is the fee waived?", QuestionType.CONDITIONS),
        ("What exceptions apply to the rule?", QuestionType.CONDITIONS),
        ("Compare the fees of gold and silver accounts.", QuestionType.COMPARISON),
    ],
)
def test_each_supported_question_word_gives_its_type(question, expected):
    components = analyze(question).components
    assert [component.question_type for component in components][0] == expected
    assert components[0].reason is None


@pytest.mark.parametrize(
    "question, reason_part",
    [
        ("Why is the rule applied?", "why questions"),
        ("How is the fee calculated?", "how questions about a process"),
        ("Explain the policy.", "does not open with a supported question word"),
    ],
)
def test_unsupported_questions_are_reported_with_a_reason_and_never_searched(question, reason_part):
    component = analyze(question).components[0]
    assert component.question_type == QuestionType.UNSUPPORTED
    assert reason_part in component.reason
    assert component.retrieval_query == ""
    assert component.searchable is False


def test_a_question_with_no_subject_words_is_ambiguous_and_says_so():
    component = analyze("What is the maximum amount?").components[0]
    assert component.question_type == QuestionType.WHAT
    assert component.reason == "the question names no subject to search for"
    assert component.flags == ("no_target_terms",)


def test_target_and_attribute_terms_are_separated_and_the_query_keeps_their_order():
    component = analyze("What is the maximum loan amount for small businesses?").components[0]
    assert component.target_terms == ("loan", "small", "businesses")
    assert component.attribute_terms == ("maximum", "amount")
    assert component.retrieval_query == "loan small businesses maximum amount"


def test_the_retrieval_query_has_no_duplicates():
    component = analyze("What is the loan limit, and the loan limit amount?").components[0]
    assert len(component.retrieval_query.split()) == len(set(component.retrieval_query.split()))


def test_plural_attribute_words_are_attributes_too():
    component = analyze("How many days after approval must reports be filed?").components[0]
    assert "days" in component.attribute_terms
    assert "days" not in component.target_terms


def test_a_list_question_is_one_component_and_its_commas_are_not_split():
    analysis = analyze("What are the fees, penalties and deadlines for the loan?")
    assert analysis.compound is False
    assert len(analysis.components) == 1


def test_a_conjunction_that_does_not_open_a_question_is_never_split():
    analysis = analyze("What is the rule and the exception for staff?")
    assert analysis.compound is False
    assert analysis.components[0].text == "What is the rule and the exception for staff"


def test_two_questions_in_one_message_are_two_components_in_order():
    analysis = analyze("Who approves the loan? What is the limit for the loan?")
    assert [c.component_id for c in analysis.components] == ["c1", "c2"]
    assert [c.question_type for c in analysis.components] == [QuestionType.WHO, QuestionType.WHAT]
    assert analysis.compound is True


def test_a_compound_clause_that_opens_a_new_question_is_split():
    analysis = analyze("What is the fee and when is it due?")
    assert [c.text for c in analysis.components] == ["What is the fee", "when is it due"]
    assert [c.question_type for c in analysis.components] == [QuestionType.WHAT, QuestionType.WHEN]


def test_a_split_clause_takes_the_subject_of_the_clause_before_it():
    analysis = analyze("What is the rule for staff and when are they reviewed?")
    second = analysis.components[1]
    assert second.question_type == QuestionType.WHEN
    assert second.target_terms == ("rule", "staff")
    assert second.flags == ("target_inherited",)


def test_a_pronoun_in_a_split_clause_with_no_earlier_subject_is_ambiguous_not_searched_on_a_predicate():
    analysis = analyze("What is the fee and when is it due?")
    second = analysis.components[1]
    assert second.reason == "a pronoun refers to an earlier subject, but no earlier subject was named"
    assert second.flags == ("pronoun_without_subject",)
    assert second.searchable is False


def test_an_expletive_it_in_a_single_question_does_not_block_the_search():
    component = analyze("Is it permitted to share data?").components[0]
    assert component.question_type == QuestionType.WHETHER
    assert component.target_terms == ("share", "data")
    assert component.searchable is True


def test_a_question_whose_only_subject_is_a_pronoun_is_ambiguous():
    component = analyze("Is it allowed?").components[0]
    assert component.reason == "the question names no subject to search for"


def test_a_comparison_with_explicit_subjects_gives_one_component_per_subject():
    analysis = analyze("Compare the fees of gold and silver accounts.")
    assert [c.text for c in analysis.components] == ["the fees of gold", "silver accounts"]
    assert all(c.flags[0] == "comparison_subject" for c in analysis.components)
    assert analysis.components[1].target_terms == ("silver", "accounts")


def test_a_comparison_whose_subjects_name_only_properties_is_ambiguous():
    analysis = analyze("What is the difference between the limit and the threshold?")
    assert [c.reason is None for c in analysis.components] == [False, False]
    assert all(c.question_type == QuestionType.COMPARISON for c in analysis.components)


def test_a_comparison_without_explicit_subjects_is_ambiguous_with_a_reason():
    component = analyze("Compare the limits.").components[0]
    assert component.question_type == QuestionType.COMPARISON
    assert component.reason == "the subjects of this comparison are not explicit"
    assert component.flags == ("subjects_unclear",)


def test_a_negated_question_is_recorded_for_later_checks():
    assert analyze("Is it not allowed to share data?").components[0].negated is True
    assert analyze("Is it allowed to share data?").components[0].negated is False


def test_condition_words_in_a_question_are_recorded():
    component = analyze("Is the fee waived if the staff member is temporary?").components[0]
    assert component.condition_terms == ("if",)


@pytest.mark.parametrize(
    "question, intent",
    [
        ("How many days apply?", ValueIntent.NUMBER),
        ("When is the report due?", ValueIntent.DATE_OR_PERIOD),
        ("What is the policy?", ValueIntent.NONE),
    ],
)
def test_the_value_intent_follows_the_question_type(question, intent):
    assert analyze(question).components[0].value_intent == intent


def test_each_component_text_is_a_verbatim_slice_of_the_question():
    question = "Who approves the loan? What is the limit, and when is it due?"
    for component in analyze(question).components:
        assert component.text in question


def test_analysis_is_deterministic():
    question = "What is the fee for gold accounts and when is it due?"
    assert analyze(question) == analyze(question)


@pytest.mark.parametrize("bad", ["", "   ", None, 42, "???", "ab\x00cd?"])
def test_an_unusable_question_is_refused(bad):
    with pytest.raises(QuestionError):
        analyze(bad)

"""P4 rules: the rules file is validated, each rule is checked against its own examples, and expansion is one-way.

The shipped file holds no approved rule (D43). The mechanism is tested with ``tests/fixtures/retrieval_rules_test.toml``,
whose rules are synthetic and never shipped.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.retrieval import RuleConfigError, expand_words, load_rules
from app.retrieval.rules import RuleSet, folded_words

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "retrieval_rules_test.toml"

RULE_BODY = """
id = "test-fee-charge"
version = 1
query_terms = ["fee"]
alternatives = ["charge"]
positive_examples = [{ query = "fee", text = "The charge applies." }]
counter_examples = [{ query = "fee", text = "The discharge applies." }]
reviewer_note = "Synthetic."
"""


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "rules.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_the_shipped_file_holds_no_approved_rule():
    rules = load_rules()
    assert rules.rules == ()
    assert expand_words(("fee",), rules) == ()


def test_the_fixture_rules_load_in_file_order():
    rules = load_rules(FIXTURE)
    assert [rule.id for rule in rules.rules] == ["test-fee-charge", "test-risk-review", "test-run-forms"]
    assert rules.rules[1].version == 2
    assert rules.rules[0].alternatives == ("charge", "charges")


def test_an_alternative_is_logged_with_its_rule_id_and_version():
    applied = expand_words(("fee",), load_rules(FIXTURE))
    assert [(item.query_term, item.rule_id, item.rule_version, item.alternative) for item in applied] == [
        ("fee", "test-fee-charge", 1, "charge"),
        ("fee", "test-fee-charge", 1, "charges"),
    ]


def test_expansion_is_one_way():
    # "charge" is an alternative of the fee rule, but it is not a query term of any rule.
    assert expand_words(("charge",), load_rules(FIXTURE)) == ()


def test_expansion_matches_whole_words_only():
    assert expand_words(("discharge",), load_rules(FIXTURE)) == ()
    assert expand_words(("fees",), load_rules(FIXTURE)) == ()


def test_a_multi_word_query_term_needs_its_words_to_be_adjacent():
    rules = load_rules(FIXTURE)
    assert len(expand_words(("risk", "assessment"), rules)) == 1
    assert expand_words(("risk", "alone", "assessment"), rules) == ()


def test_a_stemming_form_is_listed_not_computed():
    rules = load_rules(FIXTURE)
    assert [item.alternative for item in expand_words(("run",), rules)] == ["running", "runs"]
    assert expand_words(("rerun",), rules) == ()


def test_the_fingerprint_changes_when_a_rule_changes():
    rules = load_rules(FIXTURE)
    same = load_rules(FIXTURE)
    changed_rule = rules.rules[0].model_copy(update={"version": 2})
    changed = RuleSet(rules=(changed_rule, *rules.rules[1:]))
    assert rules.fingerprint == same.fingerprint
    assert rules.fingerprint != changed.fingerprint


def test_folded_words_follow_the_index_folding():
    assert folded_words("Risk Assessment") == ("risk", "assessment")


@pytest.mark.parametrize(
    "body, reason",
    [
        ("DUPLICATE", "two rules with one id"),
        (RULE_BODY.replace('"The charge applies."', '"The fee is due."'), "a positive example without the alternative"),
        (RULE_BODY.replace('"The discharge applies."', '"The charge applies."'), "a counter-example with the alternative"),
        (RULE_BODY.replace('alternatives = ["charge"]', 'alternatives = ["fee"]'), "an alternative that repeats a query term"),
        (RULE_BODY.replace('reviewer_note = "Synthetic."\n', ""), "a missing reviewer note"),
        (RULE_BODY.replace('id = "test-fee-charge"', 'id = "Test-Fee"'), "an id that is not lowercase"),
        (RULE_BODY.replace('alternatives = ["charge"]', "alternatives = []"), "no alternatives"),
        (RULE_BODY.replace('query_terms = ["fee"]', 'query_terms = ["--"]'), "a term with no letter or digit"),
        (
            RULE_BODY.replace('[{ query = "fee", text = "The discharge applies." }]', '[{ query = "tax", text = "The discharge applies." }]'),
            "a counter-example whose query has no query term",
        ),
        (RULE_BODY.replace('query_terms = ["fee"]', 'query_terms = ["fee", "Fee"]'), "a query term listed twice"),
    ],
)
def test_invalid_rules_are_refused(tmp_path, body, reason):
    if body == "DUPLICATE":
        path = _write(tmp_path, "rules_version = 1\n\n[[rule]]\n" + RULE_BODY + "\n[[rule]]\n" + RULE_BODY)
    else:
        path = _write(tmp_path, "rules_version = 1\n\n[[rule]]\n" + body)
    with pytest.raises(RuleConfigError):
        load_rules(path)


def test_a_wrong_file_version_is_refused(tmp_path):
    with pytest.raises(RuleConfigError, match="rules_version = 1"):
        load_rules(_write(tmp_path, "rules_version = 2\n"))


def test_a_missing_rules_file_is_refused(tmp_path):
    with pytest.raises(RuleConfigError, match="not found"):
        load_rules(tmp_path / "absent.toml")

"""The controlled vocabulary of verification, version 1 (ARCHITECTURE §15, D62 to D64).

Every list here was reviewed by reading. None was calibrated on a gold answer. The expected P5 rule IDs are repeated
here on purpose, so that verification does not import the selection's decisions. A test checks them against
``app.evidence.selection.RULE_IDS``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.question_processing.analysis import QuestionType

VERIFIER_VERSION = "verify.v1"
VOCABULARY_VERSION = "verify.vocabulary.v1"

EXPECTED_RULE_IDS: dict[QuestionType, str] = {
    QuestionType.WHAT: "what.sentence.v1",
    QuestionType.WHO: "who.sentence.v1",
    QuestionType.WHERE: "where.sentence.v1",
    QuestionType.WHICH: "which.sentence.v1",
    QuestionType.WHEN: "when.date_or_period.v1",
    QuestionType.HOW_MANY: "how_many.value_with_unit.v1",
    QuestionType.WHETHER: "whether.permission_marker.v1",
    QuestionType.CONDITIONS: "conditions.passage.v1",
    QuestionType.COMPARISON: "comparison.subject_sentence.v1",
}

# The types whose answer is one value or one marker that a rule can give (SPEC §6). Every other type is passage only.
ANSWER_TYPES = frozenset({QuestionType.WHEN, QuestionType.HOW_MANY, QuestionType.WHETHER})

# P5 flags that block a candidate from passing (D64). Each one gives UNRESOLVED on ``candidate_flags``.
BLOCKING_FLAG_REASONS: dict[str, str] = {
    "no_answer_span": "the rule gives no answer span for this passage",
    "multiple_values": "the passage holds more than one value of the required kind",
    "multiple_markers": "the passage holds more than one permission or prohibition marker",
    "table_cell": "a table cell is passage only, because its meaning depends on its row and column (D48)",
    "list_marker": "the passage is a list item, so its scope depends on the list's introduction",
    "comparison_subject": "the comparison subject is not checked by a rule",
    "replacement_character": "the passage holds a replacement character, so its text may be damaged (D55)",
}


def _phrase_pattern(phrases: Iterable[str]) -> re.Pattern[str]:
    """A case-insensitive pattern for whole phrases. Spaces in a phrase match any run of whitespace."""
    ordered = sorted(phrases, key=len, reverse=True)
    body = "|".join(r"\s+".join(re.escape(part) for part in phrase.split()) for phrase in ordered)
    # The group matters: without it, the word boundaries would attach only to the first and last alternatives.
    return re.compile(rf"(?<![A-Za-z])(?:{body})(?![A-Za-z])", re.IGNORECASE)


# Qualifiers that can change what a passage claims. In the passage they make the condition check UNRESOLVED. In a
# neighbouring unit they make the context check UNRESOLVED (D62).
STRONG_QUALIFIERS = _phrase_pattern(
    (
        "except",
        "unless",
        "only if",
        "provided that",
        "does not apply",
        "do not apply",
        "however",
        "subject to",
    )
)

# Negation words and the contraction "n't". A negation outside a marker makes the negation check UNRESOLVED (D62).
NEGATION = re.compile(
    r"(?<![A-Za-z])(?:not|no|never|none|nor|neither|cannot|without|nothing)(?![A-Za-z])|n['’]t(?![A-Za-z])",
    re.IGNORECASE,
)

# Hedges that mark uncertainty. "may be" is left out on purpose: it is usually a permission in policy text.
HEDGE = _phrase_pattern(
    (
        "might",
        "could",
        "possibly",
        "probably",
        "perhaps",
        "unclear",
        "uncertain",
        "appears to",
        "seems to",
        "is likely",
        "are likely",
    )
)

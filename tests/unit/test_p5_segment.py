"""P5 sentence boundaries and markers (D50; ARCHITECTURE §14). Every expected sentence is written out by hand.

The abbreviation rule is the risky one. Not splitting is the safe direction, so the cases below test both sides:
a full stop that must not end a sentence, and one that must.
"""

from __future__ import annotations

import pytest

from app.evidence.markers import find_markers
from app.evidence.segment import sentence_spans


def _sentences(text: str) -> list[str]:
    return [text[start:end] for start, end in sentence_spans(text)]


@pytest.mark.parametrize(
    "text, expected",
    [
        # An abbreviation followed by a proper noun does not end the sentence.
        (
            "The U.S. Department of Commerce issued it.",
            ["The U.S. Department of Commerce issued it."],
        ),
        # The same abbreviation before a word that opens a sentence does end it.
        (
            "It is in the U.S. The next sentence follows.",
            ["It is in the U.S.", "The next sentence follows."],
        ),
        # e.g. followed by lower case does not end the sentence.
        (
            "Use one, e.g. the rule for staff. Then stop.",
            ["Use one, e.g. the rule for staff.", "Then stop."],
        ),
        # A title and a surname do not end the sentence; the sentence after it does.
        (
            "Dr. Smith said. Then this happened.",
            ["Dr. Smith said.", "Then this happened."],
        ),
        # A number mark and an initial do not end the sentence.
        (
            "See No. 800-53 for controls. J. Smith agreed.",
            ["See No. 800-53 for controls.", "J. Smith agreed."],
        ),
        # A full stop before a digit is not a boundary.
        (
            "It costs 5. 6 more are needed.",
            ["It costs 5. 6 more are needed."],
        ),
        # A full stop before a lower-case letter is not a boundary.
        (
            "Version 2. the rule applies here.",
            ["Version 2. the rule applies here."],
        ),
        # Question and exclamation marks end sentences.
        (
            "Is it allowed? Yes! Staff may apply.",
            ["Is it allowed?", "Yes!", "Staff may apply."],
        ),
        # A closing quotation mark stays with its sentence.
        (
            'The rule says "use it." Then stop.',
            ['The rule says "use it."', "Then stop."],
        ),
    ],
)
def test_sentence_boundaries_follow_the_rules(text, expected):
    assert _sentences(text) == expected


def test_a_line_wrap_is_whitespace_and_never_ends_a_sentence():
    text = "The policy applies to\n\nall staff who\n\nhandle data. It is binding."
    assert _sentences(text) == ["The policy applies to\n\nall staff who\n\nhandle data.", "It is binding."]


def test_spans_are_ordered_non_empty_and_trimmed():
    text = "  First one.   Second one.\n\n Third one.  "
    spans = sentence_spans(text)
    assert [text[start:end] for start, end in spans] == ["First one.", "Second one.", "Third one."]
    for (start, end), (next_start, _) in zip(spans, spans[1:]):
        assert start < end <= next_start
    for start, end in spans:
        assert text[start] != " " and text[end - 1] != " "


@pytest.mark.parametrize("text", ["", "   ", "\n\n\t"])
def test_blank_text_has_no_sentences(text):
    assert sentence_spans(text) == ()


def test_text_without_end_punctuation_is_one_sentence():
    assert _sentences("A heading without a full stop") == ["A heading without a full stop"]


def test_the_splitter_is_deterministic():
    text = "The U.S. Department said so. It is in the U.S. The next one. Dr. Smith agreed."
    assert sentence_spans(text) == sentence_spans(text)


# ----------------------------------------------------------------------------- markers

def _marker_texts(text: str, kind: str) -> list[tuple[str, bool]]:
    return [(marker.text, marker.negative) for marker in find_markers(text, kind)]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Staff must not share passwords.", [("must not", True)]),
        ("Sharing is not permitted for staff.", [("is not permitted", True)]),
        ("Sharing is prohibited.", [("is prohibited", True)]),
        ("Staff must share the log.", [("must", False)]),
        ("Visitors may enter the lobby.", [("may", False)]),
        ("Sharing is permitted for staff.", [("is permitted", False)]),
        ("Reports are required each month.", [("are required", False)]),
        ("No marker appears in this sentence.", []),
    ],
)
def test_permission_markers_are_found_with_their_polarity(text, expected):
    assert _marker_texts(text, "permission") == expected


def test_a_negative_phrase_claims_its_words_so_must_is_not_counted_twice():
    assert [marker.text for marker in find_markers("They must never leave.", "permission")] == ["must never"]


def test_condition_and_list_markers_are_found():
    assert [m.text for m in find_markers("Fees apply unless waived, subject to review.", "condition")] == [
        "unless",
        "subject to",
    ]
    assert [m.text for m in find_markers("The forms include A and B, such as C.", "list")] == [
        "include",
        "such as",
    ]


def test_a_marker_word_inside_a_longer_word_is_not_a_marker():
    assert find_markers("The mustard and the maybe list.", "permission") == ()


def test_markers_carry_exact_offsets():
    text = "Staff must not share, unless approved."
    for marker in find_markers(text, "permission") + find_markers(text, "condition"):
        assert text[marker.start : marker.end] == marker.text


def test_an_unknown_marker_family_is_refused():
    with pytest.raises(ValueError):
        find_markers("text", "permisson")

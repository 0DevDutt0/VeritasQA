"""P2 normalization (ARCHITECTURE §11): index text is reversible to raw offsets, and only index text is folded.

Run: pytest tests/unit/test_p2_normalization.py -q
"""

from __future__ import annotations

import pytest

from app.common.text import normalize_text, normalize_with_map


def test_plain_ascii_is_unchanged():
    assert normalize_text("Risk limit 3.5 percent") == "Risk limit 3.5 percent"


def test_ligature_expands_and_both_characters_map_to_the_one_raw_character():
    result = normalize_with_map("ﬁx")
    assert result.text == "fix"
    assert result.spans[0] == result.spans[1] == (0, 1)


def test_non_breaking_space_becomes_a_space():
    assert normalize_text("3.5 percent") == "3.5 percent"


def test_soft_hyphen_inside_a_word_is_removed():
    assert normalize_text("con­tract") == "contract"


def test_curly_quotes_and_dash_variants_become_ascii():
    assert normalize_text("“limit” – 5—10 ‑ 2") == '"limit" - 5-10 - 2'


def test_combining_mark_composes_with_its_base_and_maps_to_both_raw_characters():
    result = normalize_with_map("café")
    assert result.text == "café"
    assert result.spans[-1] == (3, 5)


def test_fullwidth_digits_and_latin_are_folded():
    assert normalize_text("２０２４ ＡＢ") == "2024 AB"


def test_arabic_presentation_form_folds_and_directional_marks_are_removed():
    raw = "‏ﻻ"
    result = normalize_with_map(raw)
    assert "‏" not in result.text
    assert result.text == "لا"
    assert result.spans == ((1, 2), (1, 2))


def test_hyphen_at_line_end_joins_only_before_a_lowercase_letter():
    assert normalize_text("exam-\nple") == "example"
    assert normalize_text("risk-\nBased") == "risk- Based"


def test_soft_hyphen_at_line_end_joins_before_a_lowercase_letter():
    assert normalize_text("contin­\nuous") == "continuous"


def test_newline_runs_and_spaces_collapse_and_trim():
    assert normalize_text("  alpha\n\nbeta   gamma  ") == "alpha beta gamma"


def test_raw_range_maps_an_index_match_back_to_its_raw_offsets():
    raw = "The  Limit is 3.5"
    result = normalize_with_map(raw)
    start = result.text.index("Limit")
    raw_start, raw_end = result.raw_range(start, start + len("Limit"))
    assert raw[raw_start:raw_end] == "Limit"


def test_every_output_character_has_a_span_and_spans_never_go_backwards():
    raw = "Ligatures ﬁ and “quotes” – with spaces\n\nand con­tinuation­\nlines, plus café."
    result = normalize_with_map(raw)
    assert len(result.spans) == len(result.text)
    starts = [span[0] for span in result.spans]
    assert starts == sorted(starts)
    for start, end in result.spans:
        assert 0 <= start < end <= len(raw)


def test_raw_range_rejects_an_empty_or_out_of_bounds_range():
    result = normalize_with_map("abc")
    with pytest.raises(ValueError):
        result.raw_range(1, 1)
    with pytest.raises(ValueError):
        result.raw_range(0, 4)

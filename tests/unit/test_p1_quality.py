"""P1 exit criteria (classification): every page status follows from its measured features.

The classifier is pure, so these tests build feature records by hand. Run:
pytest tests/unit/test_p1_quality.py -q
"""

from __future__ import annotations

import pytest

from app.ingestion.config import load_ingestion_config
from app.ingestion.models import ISSUE_CODES, PageStatus, QualityStatus, quality_for
from app.ingestion.quality import PageFeatures, TextProfile, classify_page, text_profile

CONFIG = load_ingestion_config()


def _text(**overrides) -> TextProfile:
    values = dict(
        non_space_chars=200,
        letters=170,
        tokens=40,
        single_letter_tokens=0,
        replacement_chars=0,
        control_chars=0,
        private_use_chars=0,
    )
    values.update(overrides)
    return TextProfile(**values)


def _features(text: TextProfile | None = None, **overrides) -> PageFeatures:
    values = dict(
        text=text if text is not None else _text(),
        image_coverage=0.0,
        ink_ratio=None,
        visible_chars=200,
        hidden_chars=0,
        table_count=0,
        table_error=None,
        rotation=0,
        reading_uncertain=(),
    )
    values.update(overrides)
    return PageFeatures(**values)


def _status(features: PageFeatures) -> PageStatus:
    status, _ = classify_page(features, CONFIG)
    return status


def _codes(features: PageFeatures) -> set[str]:
    _, issues = classify_page(features, CONFIG)
    return {issue.code for issue in issues}


# --- text profile -----------------------------------------------------------------------------

def test_text_profile_counts_letters_tokens_and_bad_characters():
    profile = text_profile("a�\x01 b")
    assert profile.non_space_chars == 5
    assert profile.letters == 2
    assert profile.replacement_chars == 1
    assert profile.private_use_chars == 1
    assert profile.control_chars == 1
    assert profile.tokens == 2
    assert profile.single_letter_tokens == 1  # only "b"; the first token has four characters


def test_text_profile_counts_single_letter_tokens():
    profile = text_profile("I saw a dog")
    assert profile.tokens == 4
    assert profile.single_letter_tokens == 2


def test_empty_text_profile_is_all_zero():
    profile = text_profile("   \n\t ")
    assert profile.non_space_chars == 0
    assert profile.tokens == 0


# --- no-text pages ----------------------------------------------------------------------------

def test_image_dominated_page_without_text_is_scanned():
    features = _features(_text(non_space_chars=0, letters=0, tokens=0), image_coverage=0.8, visible_chars=0, hidden_chars=0)
    assert _status(features) is PageStatus.SCANNED
    assert "image_only_page" in _codes(features)


def test_page_with_almost_no_ink_and_no_text_is_blank():
    features = _features(_text(non_space_chars=0, letters=0, tokens=0), ink_ratio=0.0, visible_chars=0, hidden_chars=0)
    assert _status(features) is PageStatus.BLANK
    assert "blank_page" in _codes(features)


def test_page_with_ink_and_no_text_is_suspicious():
    features = _features(_text(non_space_chars=0, letters=0, tokens=0), ink_ratio=0.02, visible_chars=0, hidden_chars=0)
    assert _status(features) is PageStatus.SUSPICIOUS
    assert "no_text_with_content" in _codes(features)


# --- image-dominated pages with text ----------------------------------------------------------

def test_image_dominated_page_with_text_is_a_text_layer_of_unknown_origin():
    features = _features(image_coverage=0.9)
    assert _status(features) is PageStatus.SCANNED_TEXT_LAYER
    assert "image_with_text_layer" in _codes(features)


def test_invisible_text_on_an_image_page_is_reported_as_a_hidden_layer():
    features = _features(image_coverage=0.9, visible_chars=0, hidden_chars=40)
    assert _status(features) is PageStatus.SCANNED_TEXT_LAYER
    assert {"image_with_text_layer", "hidden_text_layer"} <= _codes(features)


def test_image_dominance_takes_precedence_over_garbled_text():
    features = _features(_text(replacement_chars=30), image_coverage=0.9)
    assert _status(features) is PageStatus.SCANNED_TEXT_LAYER


# --- text pages -------------------------------------------------------------------------------

def test_clean_text_page_is_ok_with_no_issues():
    status, issues = classify_page(_features(), CONFIG)
    assert status is PageStatus.OK
    assert issues == []


def test_text_made_only_of_invisible_characters_is_suspicious():
    features = _features(visible_chars=0, hidden_chars=25)
    assert _status(features) is PageStatus.SUSPICIOUS
    assert "hidden_text_only" in _codes(features)


def test_garbled_text_above_the_limit_is_garbled():
    features = _features(_text(replacement_chars=30))
    assert _status(features) is PageStatus.GARBLED
    assert "garbled_text" in _codes(features)


def test_a_few_private_use_bullets_below_the_limit_do_not_garble_a_page():
    features = _features(_text(private_use_chars=5))  # 5 of 200 = 2.5%, under the 5% limit
    assert _status(features) is PageStatus.OK


def test_text_with_too_few_letters_is_suspicious():
    features = _features(_text(letters=40))  # 40 of 200 = 0.2, under the 0.4 minimum
    assert _status(features) is PageStatus.SUSPICIOUS
    assert "suspicious_text" in _codes(features)


def test_text_with_many_single_letter_tokens_is_suspicious():
    features = _features(_text(tokens=40, single_letter_tokens=30))
    assert _status(features) is PageStatus.SUSPICIOUS


def test_short_text_is_not_judged_by_the_ratio_checks():
    features = _features(_text(non_space_chars=20, letters=5, tokens=4, single_letter_tokens=4))
    assert _status(features) is PageStatus.OK


def test_invisible_text_beside_visible_text_is_a_warning():
    features = _features(hidden_chars=3, visible_chars=300)  # 1% invisible, under the 2% limit
    assert _status(features) is PageStatus.WARNING
    assert "hidden_text_present" in _codes(features)


def test_invisible_share_above_the_limit_is_suspicious():
    features = _features(hidden_chars=60, visible_chars=40)  # 60% invisible
    assert _status(features) is PageStatus.SUSPICIOUS
    assert "hidden_text_share_high" in _codes(features)


def test_invisible_share_exactly_at_the_limit_is_still_a_warning():
    limit = CONFIG.hidden_text_share_max
    visible = 1000
    hidden = round(limit * visible / (1 - limit))  # hidden / (hidden + visible) == limit
    features = _features(hidden_chars=hidden, visible_chars=visible)
    assert hidden / (hidden + visible) <= limit + 1e-9
    assert _status(features) is PageStatus.WARNING


@pytest.mark.parametrize("hidden", [1, 3, 40, 500])
def test_any_invisible_text_keeps_a_page_below_ok(hidden):
    status = _status(_features(hidden_chars=hidden, visible_chars=500))
    assert status is not PageStatus.OK


def test_unreadable_render_mode_is_a_warning():
    features = _features(visible_chars=None, hidden_chars=None)
    assert _status(features) is PageStatus.WARNING
    assert "text_render_mode_unknown" in _codes(features)


def test_ruled_table_is_a_warning():
    features = _features(table_count=2)
    assert _status(features) is PageStatus.WARNING
    assert "table_detected" in _codes(features)


def test_table_check_failure_is_a_warning():
    features = _features(table_count=None, table_error="pdfplumber failed on this page (ValueError)")
    assert _status(features) is PageStatus.WARNING
    assert "table_check_failed" in _codes(features)


def test_uncertain_reading_order_is_a_warning():
    features = _features(reading_uncertain=("narrow_gutter x1",))
    assert _status(features) is PageStatus.WARNING
    assert "reading_order_uncertain" in _codes(features)


def test_rotated_page_is_a_warning():
    features = _features(rotation=90)
    assert _status(features) is PageStatus.WARNING
    assert "page_rotated" in _codes(features)


def test_every_non_ok_status_carries_at_least_one_issue():
    scenarios = [
        _features(_text(non_space_chars=0, letters=0, tokens=0), image_coverage=0.8, visible_chars=0, hidden_chars=0),
        _features(_text(non_space_chars=0, letters=0, tokens=0), ink_ratio=0.0, visible_chars=0, hidden_chars=0),
        _features(_text(non_space_chars=0, letters=0, tokens=0), ink_ratio=0.5, visible_chars=0, hidden_chars=0),
        _features(image_coverage=0.9),
        _features(visible_chars=0, hidden_chars=3),
        _features(_text(replacement_chars=30)),
        _features(_text(letters=40)),
        _features(hidden_chars=3),
        _features(table_count=1),
    ]
    for features in scenarios:
        status, issues = classify_page(features, CONFIG)
        assert status is PageStatus.OK or issues, status
        assert all(issue.code in ISSUE_CODES for issue in issues)


@pytest.mark.parametrize(
    ("status", "quality"),
    [
        (PageStatus.OK, QualityStatus.VERIFIED),
        (PageStatus.WARNING, QualityStatus.WARNING),
        (PageStatus.SCANNED, QualityStatus.UNVERIFIED),
        (PageStatus.SCANNED_TEXT_LAYER, QualityStatus.UNVERIFIED),
        (PageStatus.OCR_TEXT, QualityStatus.UNVERIFIED),
        (PageStatus.BLANK, QualityStatus.UNVERIFIED),
        (PageStatus.GARBLED, QualityStatus.UNVERIFIED),
        (PageStatus.SUSPICIOUS, QualityStatus.UNVERIFIED),
    ],
)
def test_status_maps_to_the_documented_quality_state(status, quality):
    assert quality_for(status) is quality

"""Page classification (ARCHITECTURE §10). Pure: measured features in, one status and its issues out.

The decision order is fixed. The first rule that matches decides the status, and every non-OK
status carries an issue that gives its measured reason.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from app.ingestion.config import IngestionConfig
from app.ingestion.models import Issue, PageStatus


@dataclass(frozen=True)
class TextProfile:
    non_space_chars: int
    letters: int
    tokens: int
    single_letter_tokens: int
    replacement_chars: int
    control_chars: int
    private_use_chars: int


def text_profile(text: str) -> TextProfile:
    """Count the characters and tokens that the classification rules need."""
    non_space = letters = replacement = control = private_use = 0
    for character in text:
        if character.isspace():
            continue
        non_space += 1
        if character.isalpha():
            letters += 1
        if character == "�":
            replacement += 1
            continue
        category = unicodedata.category(character)
        if category == "Co":
            private_use += 1
        elif category == "Cc":
            control += 1
    tokens = text.split()
    single_letter = sum(1 for token in tokens if len(token) == 1 and token.isalpha())
    return TextProfile(
        non_space_chars=non_space,
        letters=letters,
        tokens=len(tokens),
        single_letter_tokens=single_letter,
        replacement_chars=replacement,
        control_chars=control,
        private_use_chars=private_use,
    )


@dataclass(frozen=True)
class PageFeatures:
    text: TextProfile
    image_coverage: float
    ink_ratio: float | None
    visible_chars: int | None
    hidden_chars: int | None
    table_count: int | None
    table_error: str | None
    rotation: int
    reading_uncertain: tuple[str, ...]


def classify_page(features: PageFeatures, config: IngestionConfig) -> tuple[PageStatus, list[Issue]]:
    """Return the page status and the issues that explain it."""
    text = features.text
    coverage = features.image_coverage
    image_dominated = coverage >= config.scanned_image_coverage_min

    if text.non_space_chars == 0:
        if image_dominated:
            return PageStatus.SCANNED, [
                Issue(
                    code="image_only_page",
                    severity="warning",
                    detail=(
                        f"no text; images cover {coverage:.1%} of the page "
                        f"(limit {config.scanned_image_coverage_min:.1%})"
                    ),
                )
            ]
        ink = features.ink_ratio
        if ink is not None and ink <= config.blank_ink_ratio_max:
            return PageStatus.BLANK, [
                Issue(
                    code="blank_page",
                    severity="warning",
                    detail=(
                        f"no text; ink ratio {ink:.6f} at {config.blank_check_dpi} DPI "
                        f"(limit {config.blank_ink_ratio_max})"
                    ),
                )
            ]
        return PageStatus.SUSPICIOUS, [
            Issue(
                code="no_text_with_content",
                severity="warning",
                detail=f"no text, images cover {coverage:.1%}, and the page is not blank",
            )
        ]

    if image_dominated:
        issues = [
            Issue(
                code="image_with_text_layer",
                severity="warning",
                detail=(
                    f"images cover {coverage:.1%} of the page, which also carries "
                    f"{text.non_space_chars} text characters of unknown origin"
                ),
            )
        ]
        if features.hidden_chars:
            issues.append(
                Issue(
                    code="hidden_text_layer",
                    severity="warning",
                    detail=f"{features.hidden_chars} invisible characters (text render mode 3 or 7)",
                )
            )
        return PageStatus.SCANNED_TEXT_LAYER, issues

    if features.visible_chars == 0 and features.hidden_chars:
        return PageStatus.SUSPICIOUS, [
            Issue(
                code="hidden_text_only",
                severity="warning",
                detail=f"all {features.hidden_chars} text characters are invisible; nothing visible supports them",
            )
        ]

    if features.hidden_chars and features.visible_chars is not None:
        total = features.hidden_chars + features.visible_chars
        hidden_share = features.hidden_chars / total
        if hidden_share > config.hidden_text_share_max:
            return PageStatus.SUSPICIOUS, [
                Issue(
                    code="hidden_text_share_high",
                    severity="warning",
                    detail=(
                        f"{features.hidden_chars} of {total} text characters ({hidden_share:.1%}) are invisible; "
                        f"limit {config.hidden_text_share_max:.1%}"
                    ),
                )
            ]

    garbled = text.replacement_chars + text.control_chars + text.private_use_chars
    garbled_ratio = garbled / text.non_space_chars
    if garbled_ratio > config.garbled_char_ratio_max:
        return PageStatus.GARBLED, [
            Issue(
                code="garbled_text",
                severity="warning",
                detail=(
                    f"{garbled} of {text.non_space_chars} non-space characters ({garbled_ratio:.1%}; "
                    f"limit {config.garbled_char_ratio_max:.1%}): replacement {text.replacement_chars}, "
                    f"control {text.control_chars}, private-use {text.private_use_chars}"
                ),
            )
        ]

    problems: list[str] = []
    if text.non_space_chars >= config.suspicious_min_non_space_chars:
        letter_ratio = text.letters / text.non_space_chars
        if letter_ratio < config.suspicious_letter_ratio_min:
            problems.append(
                f"letter ratio {letter_ratio:.2f} (minimum {config.suspicious_letter_ratio_min:.2f})"
            )
    if text.tokens >= config.suspicious_min_tokens:
        single_ratio = text.single_letter_tokens / text.tokens
        if single_ratio > config.suspicious_single_letter_token_ratio_max:
            problems.append(
                f"single-letter token ratio {single_ratio:.2f} "
                f"(maximum {config.suspicious_single_letter_token_ratio_max:.2f})"
            )
    if problems:
        return PageStatus.SUSPICIOUS, [
            Issue(code="suspicious_text", severity="warning", detail="; ".join(problems))
        ]

    warnings: list[Issue] = []
    if features.hidden_chars:
        warnings.append(
            Issue(
                code="hidden_text_present",
                severity="warning",
                detail=f"{features.hidden_chars} invisible characters beside {features.visible_chars} visible",
            )
        )
    if features.hidden_chars is None:
        warnings.append(
            Issue(
                code="text_render_mode_unknown",
                severity="warning",
                detail="the text render mode could not be read from the page",
            )
        )
    if features.table_error:
        warnings.append(Issue(code="table_check_failed", severity="warning", detail=features.table_error))
    elif features.table_count:
        warnings.append(
            Issue(
                code="table_detected",
                severity="warning",
                detail=(
                    f"{features.table_count} ruled table(s) found (pdfplumber, lines strategy); "
                    "cell text is read in column order until P2 rebuilds the rows"
                ),
            )
        )
    if features.reading_uncertain:
        warnings.append(
            Issue(
                code="reading_order_uncertain",
                severity="warning",
                detail="; ".join(features.reading_uncertain),
            )
        )
    if features.rotation:
        warnings.append(
            Issue(code="page_rotated", severity="warning", detail=f"page rotation is {features.rotation} degrees")
        )
    if warnings:
        return PageStatus.WARNING, warnings
    return PageStatus.OK, []

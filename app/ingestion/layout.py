"""Pure layout rules: header and footer detection, and reading order.

Nothing here touches PyMuPDF. The functions take boxes (x0, y0, x1, y1) in page points, so the
rules are tested on hand-made geometry. The native PDF content order is never used.

The extractor passes one box per text line, not per PyMuPDF block. PyMuPDF can place the lines of
two columns on one baseline inside one block, so lines are the reliable unit for ordering.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Sequence

Box = tuple[float, float, float, float]

# Vertical overlap below this many points is treated as touching, not overlapping.
_VERTICAL_TOLERANCE = 1.0

_DIGITS = re.compile(r"\d+")
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class TextBox:
    """A text unit: ``key`` is the caller's index, ``box`` its bounds, ``text`` its content."""

    key: int
    box: Box
    text: str


@dataclass(frozen=True)
class LayoutRules:
    wide_block_width_fraction: float
    min_gutter_fraction: float
    overlap_area_fraction_max: float


@dataclass(frozen=True)
class ReadingOrderResult:
    """Reading order of the text units on one page.

    ``order`` holds (key, column_index) pairs in reading order. Full-width units have column 0.
    ``bands`` gives, for each entry of ``order``, the band it belongs to. A full-width unit is a
    band of its own, and each run of narrow units between two full-width units is another band.
    """

    order: tuple[tuple[int, int], ...]
    bands: tuple[int, ...]
    column_count: int
    method: str  # "none", "single_column" or "multi_column"
    uncertain_reasons: tuple[str, ...]


def repetition_key(text: str) -> str:
    """Normalize text so that running headers and page numbers match across pages."""
    return _WHITESPACE.sub(" ", _DIGITS.sub("#", text)).strip().lower()


def _margin_role(box: Box, height: float, band_fraction: float) -> str | None:
    if height <= 0:
        return None
    if box[3] <= height * band_fraction:
        return "header"
    if box[1] >= height * (1.0 - band_fraction):
        return "footer"
    return None


def find_repeated_margins(
    pages: Sequence[Sequence[TextBox]],
    page_heights: Sequence[float],
    *,
    band_fraction: float,
    min_pages: int,
) -> dict[tuple[int, int], str]:
    """Return {(page_index, unit_key): "header" | "footer"} for margin text that repeats.

    A margin text repeats when its normalized form appears on at least
    ``max(min_pages, ceil(page_count / 2))`` pages.
    """
    threshold = max(min_pages, math.ceil(len(pages) / 2))
    seen: dict[tuple[str, str], set[int]] = {}
    candidates: dict[tuple[int, int], tuple[str, str]] = {}
    for page_index, boxes in enumerate(pages):
        height = page_heights[page_index]
        for box in boxes:
            role = _margin_role(box.box, height, band_fraction)
            if role is None:
                continue
            key = repetition_key(box.text)
            if not key:
                continue
            seen.setdefault((role, key), set()).add(page_index)
            candidates[(page_index, box.key)] = (role, key)
    return {
        position: role
        for position, (role, key) in candidates.items()
        if len(seen[(role, key)]) >= threshold
    }


def _area(box: Box) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _overlap_fraction(first: Box, second: Box) -> float:
    width = min(first[2], second[2]) - max(first[0], second[0])
    height = min(first[3], second[3]) - max(first[1], second[1])
    if width <= 0 or height <= 0:
        return 0.0
    smaller = min(_area(first), _area(second))
    if smaller <= 0:
        return 0.0
    return (width * height) / smaller


def _vertical_overlap(first: Box, second: Box) -> float:
    return min(first[3], second[3]) - max(first[1], second[1])


def _emit_band(
    band: Sequence[TextBox],
    band_id: int,
    extent: float,
    rules: LayoutRules,
    entries: list[tuple[int, int, int]],
    reasons: list[str],
) -> int:
    """Cluster the narrow units of one band into columns and append them. Returns the column count."""
    if not band:
        return 0
    columns: list[list[TextBox]] = []
    right_edges: list[float] = []
    for item in sorted(band, key=lambda entry: (entry.box[0], entry.box[1], entry.key)):
        if columns and item.box[0] < right_edges[-1]:
            columns[-1].append(item)
            right_edges[-1] = max(right_edges[-1], item.box[2])
        else:
            columns.append([item])
            right_edges.append(item.box[2])
    narrow_gutters = 0
    for index in range(1, len(columns)):
        gutter = min(entry.box[0] for entry in columns[index]) - right_edges[index - 1]
        if gutter < rules.min_gutter_fraction * extent:
            narrow_gutters += 1
    if narrow_gutters:
        reasons.append(f"narrow_gutter x{narrow_gutters}")
    for column_index, column in enumerate(columns):
        for item in sorted(column, key=lambda entry: (entry.box[1], entry.box[0], entry.key)):
            entries.append((item.key, column_index, band_id))
    return len(columns)


def reading_order(boxes: Sequence[TextBox], rules: LayoutRules) -> ReadingOrderResult:
    """Order the text units of one page.

    Full-width units separate the page into bands, read top to bottom. Narrow units in each band
    are clustered into columns by horizontal overlap, read left to right, then top to bottom.
    """
    if not boxes:
        return ReadingOrderResult(order=(), bands=(), column_count=0, method="none", uncertain_reasons=())

    reasons: list[str] = []
    overlapping_pairs = 0
    for position, first in enumerate(boxes):
        for second in boxes[position + 1 :]:
            if _overlap_fraction(first.box, second.box) > rules.overlap_area_fraction_max:
                overlapping_pairs += 1
    if overlapping_pairs:
        reasons.append(f"overlapping_text x{overlapping_pairs}")

    left = min(item.box[0] for item in boxes)
    right = max(item.box[2] for item in boxes)
    extent = right - left

    def is_wide(item: TextBox) -> bool:
        return extent > 0 and (item.box[2] - item.box[0]) >= rules.wide_block_width_fraction * extent

    wide_units = [item for item in boxes if is_wide(item)]
    narrow_units = [item for item in boxes if not is_wide(item)]

    wide_overlaps = 0
    for narrow in narrow_units:
        if any(_vertical_overlap(narrow.box, wide.box) > _VERTICAL_TOLERANCE for wide in wide_units):
            wide_overlaps += 1
    if wide_overlaps:
        reasons.append(f"wide_block_overlap x{wide_overlaps}")

    entries: list[tuple[int, int, int]] = []
    band: list[TextBox] = []
    band_id = 0
    column_count = 0
    for item in sorted(boxes, key=lambda entry: (entry.box[1], entry.box[0], entry.key)):
        if is_wide(item):
            column_count = max(column_count, _emit_band(band, band_id, extent, rules, entries, reasons))
            band = []
            band_id += 1
            entries.append((item.key, 0, band_id))
            band_id += 1
        else:
            band.append(item)
    column_count = max(column_count, _emit_band(band, band_id, extent, rules, entries, reasons))

    column_count = max(column_count, 1)
    method = "multi_column" if column_count >= 2 else "single_column"
    return ReadingOrderResult(
        order=tuple((key, column) for key, column, _ in entries),
        bands=tuple(band_of for _, _, band_of in entries),
        column_count=column_count,
        method=method,
        uncertain_reasons=tuple(reasons),
    )

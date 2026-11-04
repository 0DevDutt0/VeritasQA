"""P1 exit criteria (layout): reading order and repeated margins on hand-made geometry.

No PDF is involved. Boxes are (x0, y0, x1, y1) in points. The rules must never take the native
content order as the reading order. Run:  pytest tests/unit/test_p1_layout.py -q
"""

from __future__ import annotations

from app.ingestion.layout import LayoutRules, TextBox, find_repeated_margins, reading_order, repetition_key

RULES = LayoutRules(wide_block_width_fraction=0.6, min_gutter_fraction=0.02, overlap_area_fraction_max=0.1)

LEFT = (60, 130, 290, 300)
RIGHT = (305, 130, 535, 300)
HEADING = (60, 60, 535, 100)
MID_HEADING = (60, 310, 535, 340)
BOTTOM_LEFT = (60, 350, 290, 520)
BOTTOM_RIGHT = (305, 350, 535, 520)


def _box(key: int, box: tuple, text: str = "") -> TextBox:
    return TextBox(key=key, box=box, text=text or f"block {key}")


def _keys(result) -> list[int]:
    return [key for key, _ in result.order]


def _columns(result) -> list[int]:
    return [column for _, column in result.order]


# --- repeated headers and footers -------------------------------------------------------------

def test_repetition_key_ignores_digits_and_spacing():
    assert repetition_key("Page 12  of 40") == "page # of #"
    assert repetition_key("Page 3 of 9") == repetition_key("Page 4 of 9")


def test_running_header_and_footer_repeat_and_unique_text_does_not_():
    pages = []
    for number in range(4):
        blocks = [
            _box(0, (72, 30, 200, 43), "ACME Policy Manual"),
            _box(1, (72, 400, 500, 440), f"Body paragraph {number}"),
            _box(2, (72, 811, 130, 822), f"Page {number + 1} of 4"),
        ]
        if number == 0:
            blocks.append(_box(3, (72, 60, 300, 75), "Unique opening heading"))
        pages.append(blocks)
    roles = find_repeated_margins(pages, [842] * 4, band_fraction=0.08, min_pages=2)
    assert all(roles[(page, 0)] == "header" for page in range(4))
    assert all(roles[(page, 2)] == "footer" for page in range(4))
    assert (0, 3) not in roles
    assert not any(key[1] == 1 for key in roles)


def test_margin_text_on_fewer_than_half_the_pages_is_not_flagged():
    pages = [
        [_box(0, (72, 30, 200, 43), "Only here")],
        [_box(0, (72, 30, 200, 43), "Something else")],
        [_box(0, (72, 30, 200, 43), "Another one")],
        [_box(0, (72, 30, 200, 43), "And another")],
    ]
    assert find_repeated_margins(pages, [842] * 4, band_fraction=0.08, min_pages=2) == {}


def test_single_page_has_no_repeated_margins():
    pages = [[_box(0, (72, 30, 200, 43), "Header"), _box(1, (72, 811, 130, 822), "Footer")]]
    assert find_repeated_margins(pages, [842], band_fraction=0.08, min_pages=2) == {}


# --- reading order ----------------------------------------------------------------------------

def test_single_ragged_column_stays_one_column_in_vertical_order():
    boxes = [
        _box(0, (72, 100, 400, 140)),
        _box(1, (72, 150, 520, 200)),
        _box(2, (72, 210, 300, 240)),
    ]
    result = reading_order(boxes, RULES)
    assert result.method == "single_column"
    assert result.column_count == 1
    assert _keys(result) == [0, 1, 2]
    assert result.uncertain_reasons == ()


def test_right_column_drawn_first_is_still_read_second():
    boxes = [_box(0, RIGHT, "right"), _box(1, LEFT, "left")]  # native order: right first
    result = reading_order(boxes, RULES)
    assert result.method == "multi_column"
    assert result.column_count == 2
    assert _keys(result) == [1, 0]
    assert _columns(result) == [0, 1]
    assert result.uncertain_reasons == ()


def test_full_width_heading_above_the_columns_is_read_first():
    boxes = [_box(0, LEFT), _box(1, RIGHT), _box(2, HEADING, "heading")]
    result = reading_order(boxes, RULES)
    assert _keys(result) == [2, 0, 1]
    assert result.column_count == 2


def test_full_width_block_between_two_column_sections_separates_them():
    boxes = [
        _box(0, BOTTOM_RIGHT, "bottom right"),
        _box(1, MID_HEADING, "middle heading"),
        _box(2, RIGHT, "top right"),
        _box(3, BOTTOM_LEFT, "bottom left"),
        _box(4, LEFT, "top left"),
    ]
    result = reading_order(boxes, RULES)
    assert _keys(result) == [4, 2, 1, 3, 0]
    assert result.uncertain_reasons == ()


def test_overlapping_text_blocks_make_the_order_uncertain():
    boxes = [_box(0, (72, 100, 300, 200)), _box(1, (150, 150, 400, 250))]
    result = reading_order(boxes, RULES)
    assert any(reason.startswith("overlapping_text") for reason in result.uncertain_reasons)


def test_narrow_gutter_makes_the_order_uncertain():
    boxes = [_box(0, (60, 130, 299, 300)), _box(1, (301, 130, 535, 300))]
    result = reading_order(boxes, RULES)
    assert result.method == "multi_column"
    assert any(reason.startswith("narrow_gutter") for reason in result.uncertain_reasons)


def test_narrow_block_sharing_height_with_a_full_width_block_is_uncertain():
    boxes = [_box(0, HEADING, "heading"), _box(1, (60, 90, 290, 130), "side note")]
    result = reading_order(boxes, RULES)
    assert any(reason.startswith("wide_block_overlap") for reason in result.uncertain_reasons)


def test_no_text_gives_no_order():
    result = reading_order([], RULES)
    assert result.method == "none"
    assert result.order == ()
    assert result.column_count == 0

"""P2 table geometry helpers (app/document_structure/tables.py): cell assignment on synthetic boxes.

Run: pytest tests/unit/test_p2_tables.py -q
"""

from __future__ import annotations

from app.document_structure.segment import heading_label_depth, quantize
from app.document_structure.tables import TableGeometry, assign_cells, centre_inside, count_inside

TABLE = TableGeometry(
    bbox=(0.0, 0.0, 200.0, 100.0),
    rows=(
        ((0.0, 0.0, 100.0, 50.0), (100.0, 0.0, 200.0, 50.0)),
        ((0.0, 50.0, 100.0, 100.0), None),
    ),
)


def test_centre_inside_uses_the_tolerance_on_every_side():
    assert centre_inside((10.0, 10.0, 20.0, 20.0), (21.0, 15.0), tolerance=1.0)
    assert not centre_inside((10.0, 10.0, 20.0, 20.0), (22.5, 15.0), tolerance=1.0)


def test_each_centre_is_assigned_to_the_cell_that_holds_it_or_to_none():
    centres = [(50.0, 25.0), (150.0, 25.0), (50.0, 75.0), (150.0, 75.0), (300.0, 300.0)]
    assert assign_cells(TABLE, centres, tolerance=0.0) == [(0, 0), (0, 1), (1, 0), None, None]


def test_count_inside_counts_centres_in_the_table_box_only():
    centres = [(50.0, 25.0), (150.0, 75.0), (300.0, 300.0)]
    assert count_inside(TABLE, centres, tolerance=0.0) == 2


def test_heading_label_depth_follows_the_numbering():
    assert heading_label_depth("1 Purpose") == 1
    assert heading_label_depth("1.1 Definition") == 2
    assert heading_label_depth("2.3.4 Detail") == 3
    assert heading_label_depth("Introduction") == 1


def test_font_sizes_are_quantized_to_half_points():
    assert quantize(8.9, 0.5) == 9.0
    assert quantize(9.1, 0.5) == 9.0
    assert quantize(10.26, 0.5) == 10.5

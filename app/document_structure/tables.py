"""Table geometry for P2 (ARCHITECTURE §11, tables).

pdfplumber supplies only the geometry: table boxes and cell boxes. The text of every cell comes from
P1's raw_text, by assigning each P1 line to the cell that contains the line's centre. A table whose
geometry disagrees with the text is skipped, and its lines stay paragraphs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import pdfplumber

from app.ingestion.models import Box

_GEOMETRY_MISMATCH = "table_geometry_mismatch"
_READ_FAILED = "table_read_failed"


@dataclass(frozen=True)
class TableGeometry:
    bbox: Box
    rows: tuple[tuple[Box | None, ...], ...]


@dataclass(frozen=True)
class PageGeometry:
    tables: tuple[TableGeometry, ...] = ()
    issue_code: str | None = None
    detail: str = ""


def read_table_geometry(path: Path | str, page_numbers: Iterable[int]) -> dict[int, PageGeometry]:
    """Read the table boxes of the given 1-based pages with pdfplumber's lines strategy."""
    wanted = sorted(set(page_numbers))
    if not wanted:
        return {}
    try:
        plumber = pdfplumber.open(Path(path))
    except Exception as exc:  # noqa: BLE001 - every page reports the same reason
        reason = f"pdfplumber could not open the file ({type(exc).__name__})"
        return {number: PageGeometry(issue_code=_READ_FAILED, detail=reason) for number in wanted}
    result: dict[int, PageGeometry] = {}
    with plumber:
        for number in wanted:
            if number > len(plumber.pages):
                result[number] = PageGeometry(issue_code=_READ_FAILED, detail="pdfplumber found fewer pages than PyMuPDF")
                continue
            page = plumber.pages[number - 1]
            if page.bbox[0] != 0 or page.bbox[1] != 0:
                result[number] = PageGeometry(
                    issue_code=_GEOMETRY_MISMATCH,
                    detail="the page box does not start at the origin, so its boxes are not comparable with the text",
                )
                continue
            try:
                found = page.find_tables()
            except Exception as exc:  # noqa: BLE001 - reported per page, the rest of the document goes on
                result[number] = PageGeometry(issue_code=_READ_FAILED, detail=f"pdfplumber failed on this page ({type(exc).__name__})")
                continue
            tables = tuple(
                TableGeometry(
                    bbox=_box(table.bbox),
                    rows=tuple(tuple(None if cell is None else _box(cell) for cell in row.cells) for row in table.rows),
                )
                for table in found
            )
            result[number] = PageGeometry(tables=tables)
    return result


def _box(values: Sequence[float]) -> Box:
    x0, y0, x1, y1 = (float(value) for value in values)
    return (x0, y0, x1, y1)


def centre_inside(box: Box, centre: tuple[float, float], tolerance: float) -> bool:
    x, y = centre
    return box[0] - tolerance <= x <= box[2] + tolerance and box[1] - tolerance <= y <= box[3] + tolerance


def count_inside(table: TableGeometry, centres: Sequence[tuple[float, float]], tolerance: float) -> int:
    """How many line centres fall inside the table box."""
    return sum(1 for centre in centres if centre_inside(table.bbox, centre, tolerance))


def assign_cells(
    table: TableGeometry, centres: Sequence[tuple[float, float]], tolerance: float
) -> list[tuple[int, int] | None]:
    """Return the (row, column) of the cell holding each centre, or None when no cell holds it."""
    cells = [
        (row_index, column_index, box)
        for row_index, row in enumerate(table.rows)
        for column_index, box in enumerate(row)
        if box is not None
    ]
    assigned: list[tuple[int, int] | None] = []
    for centre in centres:
        holder = None
        for row_index, column_index, box in cells:
            if centre_inside(box, centre, tolerance):
                holder = (row_index, column_index)
                break
        assigned.append(holder)
    return assigned

"""Read and index helpers for P4 retrieval (ARCHITECTURE §13). Every query takes a ``document_id``.

The per-document BM25 index is a temporary FTS5 table with the columns and tokenizer of ``evidence_fts``.
It holds only the body units of one document, so its statistics belong to that document alone (D39). It
is built when a search opens it and dropped when the search closes it. The stored ``evidence_fts`` table
is never changed here.
"""

from __future__ import annotations

import contextlib
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass

from app.common.errors import StorageError

INDEX_TABLE = "document_bm25"
_CHUNK = 500


@dataclass(frozen=True)
class UnitSummary:
    """The fields of one unit that retrieval needs, without its spans or its index text."""

    evidence_id: str
    pdf_page: int
    ordinal: int
    content_type: str
    section_id: str | None
    raw_text: str
    derived: bool
    body_retrieval: bool
    extraction_quality: str


def _temp_table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_temp_master WHERE type = 'table' AND name = ?", (name,)).fetchone()
    return row is not None


def open_document_index(conn: sqlite3.Connection, document_id: str) -> int:
    """Build the index for ``document_id`` and return its row count.

    Raises StorageError when another index is already open, or when the build fails. A failed build
    drops whatever it created, so the next search starts clean.
    """
    if _temp_table_exists(conn, INDEX_TABLE):
        raise StorageError("a document BM25 index is already open on this store")
    try:
        conn.execute(
            f"CREATE VIRTUAL TABLE temp.{INDEX_TABLE} USING fts5(index_text, heading_text, evidence_id UNINDEXED)"
        )
        conn.execute(
            f"INSERT INTO temp.{INDEX_TABLE} (index_text, heading_text, evidence_id) "
            "SELECT index_text, heading_text, evidence_id FROM evidence_units "
            "WHERE document_id = ? AND body_retrieval = 1 ORDER BY pdf_page, ordinal",
            (document_id,),
        )
        return int(conn.execute(f"SELECT COUNT(*) FROM temp.{INDEX_TABLE}").fetchone()[0])
    except BaseException as exc:
        _drop_quietly(conn)
        if isinstance(exc, sqlite3.Error):
            raise StorageError(f"could not build the BM25 index of document {document_id}: {exc}") from exc
        raise


def close_document_index(conn: sqlite3.Connection) -> None:
    conn.execute(f"DROP TABLE IF EXISTS temp.{INDEX_TABLE}")


def _drop_quietly(conn: sqlite3.Connection) -> None:
    """Drop the index during error handling. A failure here must not hide the original error."""
    with contextlib.suppress(sqlite3.Error):
        close_document_index(conn)


class DocumentBm25Index:
    """The open per-document index. A :class:`Store` creates it with ``document_bm25_index``."""

    def __init__(self, conn: sqlite3.Connection, row_count: int) -> None:
        self._conn = conn
        self._row_count = row_count

    @property
    def row_count(self) -> int:
        return self._row_count

    def rank(self, fts_match: str, weights: tuple[float, float]) -> list[tuple[str, float]]:
        """``(evidence_id, bm25_raw)`` for every unit that ``fts_match`` reaches, best first.

        FTS5 returns smaller values for better matches, so the order is ascending. Ties are broken by
        ``evidence_id``. ``weights`` are the (index text, heading text) column weights of ``bm25()``.
        """
        rows = self._conn.execute(
            f"SELECT evidence_id, bm25({INDEX_TABLE}, ?, ?) AS score FROM temp.{INDEX_TABLE} "
            f"WHERE {INDEX_TABLE} MATCH ? ORDER BY score, evidence_id",
            (weights[0], weights[1], fts_match),
        ).fetchall()
        return [(str(row[0]), float(row[1])) for row in rows]

    def indexed_ids(self) -> frozenset[str]:
        rows = self._conn.execute(f"SELECT evidence_id FROM temp.{INDEX_TABLE}").fetchall()
        return frozenset(str(row[0]) for row in rows)


def _chunks(values: list[str]) -> Iterable[list[str]]:
    for start in range(0, len(values), _CHUNK):
        yield values[start : start + _CHUNK]


def read_unit_summaries(
    conn: sqlite3.Connection, document_id: str, evidence_ids: Iterable[str]
) -> dict[str, UnitSummary]:
    unique = list(dict.fromkeys(evidence_ids))
    found: dict[str, UnitSummary] = {}
    for chunk in _chunks(unique):
        marks = ", ".join("?" for _ in chunk)
        rows = conn.execute(
            "SELECT evidence_id, pdf_page, ordinal, content_type, section_id, raw_text, derived, body_retrieval, "
            f"extraction_quality FROM evidence_units WHERE document_id = ? AND evidence_id IN ({marks})",
            (document_id, *chunk),
        ).fetchall()
        for row in rows:
            found[row["evidence_id"]] = UnitSummary(
                evidence_id=row["evidence_id"],
                pdf_page=row["pdf_page"],
                ordinal=row["ordinal"],
                content_type=row["content_type"],
                section_id=row["section_id"],
                raw_text=row["raw_text"],
                derived=bool(row["derived"]),
                body_retrieval=bool(row["body_retrieval"]),
                extraction_quality=row["extraction_quality"],
            )
    return found


def read_body_neighbours(
    conn: sqlite3.Connection, document_id: str, pdf_page: int, ordinal: int, window: int
) -> tuple[list[str], list[str]]:
    """Up to ``window`` body units before and after a position, each list in reading order."""
    if window == 0:
        return [], []
    before = conn.execute(
        "SELECT evidence_id FROM evidence_units WHERE document_id = ? AND body_retrieval = 1 "
        "AND (pdf_page, ordinal) < (?, ?) ORDER BY pdf_page DESC, ordinal DESC LIMIT ?",
        (document_id, pdf_page, ordinal, window),
    ).fetchall()
    after = conn.execute(
        "SELECT evidence_id FROM evidence_units WHERE document_id = ? AND body_retrieval = 1 "
        "AND (pdf_page, ordinal) > (?, ?) ORDER BY pdf_page, ordinal LIMIT ?",
        (document_id, pdf_page, ordinal, window),
    ).fetchall()
    return [str(row[0]) for row in reversed(before)], [str(row[0]) for row in after]


def read_section_headings(
    conn: sqlite3.Connection, document_id: str, section_id: str | None
) -> tuple[str | None, str | None]:
    """The heading unit IDs of a section and of its parent section, or ``None`` where there is none."""
    if section_id is None:
        return None, None
    row = conn.execute(
        "SELECT s.heading_id AS own_heading, p.heading_id AS parent_heading "
        "FROM sections AS s LEFT JOIN sections AS p "
        "ON p.section_id = s.parent_section_id AND p.document_id = s.document_id "
        "WHERE s.document_id = ? AND s.section_id = ?",
        (document_id, section_id),
    ).fetchone()
    if row is None:
        return None, None
    return row["own_heading"], row["parent_heading"]

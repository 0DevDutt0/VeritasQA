"""The VeritasQA store: one SQLite database that holds any number of documents (ARCHITECTURE §6, §12).

A store is opened with :meth:`Store.open`, which checks FTS5 first and then the schema version.
Writes are all-or-nothing per document. Reads take a ``document_id`` and never return another
document's rows.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Self

from pydantic import BaseModel

from app.common.errors import StorageError
from app.document_structure.models import DocumentStructure, EvidenceUnit
from app.ingestion.models import ExtractedDocument
from app.storage import repository, retrieval_reads
from app.storage.fts5 import ensure_fts5_available
from app.storage.integrity import check_for_write
from app.storage.retrieval_reads import DocumentBm25Index, UnitSummary
from app.storage.schema import ensure_schema


class DocumentRecord(BaseModel):
    """The ``documents`` row of one document."""

    document_id: str
    source_name: str
    sha256: str
    size_bytes: int
    page_count: int
    extractor_version: str
    structure_version: str
    pymupdf_version: str
    pdfplumber_version: str
    extraction_config_sha256: str
    structure_config_sha256: str
    created_at: str


@contextmanager
def _write_transaction(conn: sqlite3.Connection) -> Iterator[None]:
    """One BEGIN IMMEDIATE transaction. Foreign keys are checked at COMMIT, because the unit links point both ways."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("PRAGMA defer_foreign_keys = ON")
        yield
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


class Store:
    """A handle on one SQLite database. Use it as a context manager, or call :meth:`close`."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    @classmethod
    def open(cls, path: str | os.PathLike[str] = ":memory:") -> Self:
        """Open or create a store. Raises :class:`StorageError` when FTS5 or the schema is unusable."""
        ensure_fts5_available()
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        try:
            connection = sqlite3.connect(str(path), isolation_level=None)
        except sqlite3.Error as exc:
            raise StorageError(f"cannot open the store at {path}: {exc}") from exc
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
                raise StorageError("SQLite did not enable foreign keys")
            ensure_schema(connection)
        except (sqlite3.Error, StorageError) as exc:
            connection.close()
            if isinstance(exc, StorageError):
                raise
            raise StorageError(f"cannot prepare the store at {path}: {exc}") from exc
        return cls(connection)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    # ------------------------------------------------------------------ writes

    def write_document(
        self,
        extracted: ExtractedDocument,
        structure: DocumentStructure,
        *,
        created_at: str | None = None,
    ) -> None:
        """Store one document, replacing any earlier rows for the same ``document_id``.

        The records are checked first (see ARCHITECTURE §6), so an inconsistent input raises
        :class:`StorageIntegrityError` and writes nothing. A failure during the write rolls the
        transaction back, so the store keeps the previous content of that document.
        """
        check_for_write(extracted, structure)
        stamp = created_at if created_at is not None else datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            with _write_transaction(self._conn):
                repository.delete_document(self._conn, structure.document_id)
                repository.insert_document(self._conn, extracted, structure, stamp)
                repository.insert_pages(self._conn, extracted)
                repository.insert_sections(self._conn, structure)
                repository.insert_units(self._conn, structure)
                repository.insert_locations(self._conn, structure)
                repository.insert_table_cells(self._conn, structure)
                repository.insert_issues(self._conn, structure)
                repository.insert_fts(self._conn, structure)
        except sqlite3.Error as exc:
            raise StorageError(f"could not write document {structure.document_id}: {exc}") from exc

    # ------------------------------------------------------------------ reads

    def document_ids(self) -> list[str]:
        return repository.read_document_ids(self._conn)

    def has_document(self, document_id: str) -> bool:
        return repository.read_document_row(self._conn, document_id) is not None

    def document_record(self, document_id: str) -> DocumentRecord | None:
        row = repository.read_document_row(self._conn, document_id)
        if row is None:
            return None
        return DocumentRecord(
            document_id=row["document_id"],
            source_name=row["source_name"],
            sha256=row["sha256"],
            size_bytes=row["size_bytes"],
            page_count=row["page_count"],
            extractor_version=row["extractor_version"],
            structure_version=row["structure_version"],
            pymupdf_version=row["pymupdf_version"],
            pdfplumber_version=row["pdfplumber_version"],
            extraction_config_sha256=row["extraction_config_sha256"],
            structure_config_sha256=row["structure_config_sha256"],
            created_at=row["created_at"],
        )

    def load_structure(self, document_id: str) -> DocumentStructure:
        """The structure of one document, equal to the structure that was written."""
        row = repository.read_document_row(self._conn, document_id)
        if row is None:
            raise StorageError(f"the store holds no document {document_id}")
        return repository.read_structure(self._conn, document_id, row)

    def load_unit(self, document_id: str, evidence_id: str) -> EvidenceUnit | None:
        units = repository.read_units(self._conn, document_id, evidence_id=evidence_id)
        return units[0] if units else None

    def page_texts(self, document_id: str, pdf_pages: Iterable[int]) -> dict[int, str]:
        """The immutable raw text of each requested page. Quotations are slices of these strings."""
        return repository.read_page_texts(self._conn, document_id, pdf_pages)

    def match_units(self, document_id: str, fts_match: str) -> list[EvidenceUnit]:
        """Body-retrieval units of one document whose FTS row matches ``fts_match``, in page order.

        ``fts_match`` must be a MATCH expression built by :mod:`app.retrieval.query`. This is a
        candidate step only; the exact check belongs to :mod:`app.retrieval.phrase`.
        """
        return repository.read_units(self._conn, document_id, fts_match=fts_match)

    # ------------------------------------------------------------ retrieval reads (P4, ARCHITECTURE §13)

    @contextmanager
    def document_bm25_index(self, document_id: str) -> Iterator[DocumentBm25Index]:
        """Open the BM25 index of one document for the duration of the ``with`` block.

        The index holds that document's body units only, so its statistics are per document (D39).
        It is dropped when the block ends, including when it ends with an error.
        """
        if not self.has_document(document_id):
            raise StorageError(f"the store holds no document {document_id}")
        row_count = retrieval_reads.open_document_index(self._conn, document_id)
        try:
            yield DocumentBm25Index(self._conn, row_count)
        finally:
            retrieval_reads.close_document_index(self._conn)

    def unit_summaries(self, document_id: str, evidence_ids: Iterable[str]) -> dict[str, UnitSummary]:
        """The retrieval fields of the named units of one document. Unknown IDs are left out."""
        return retrieval_reads.read_unit_summaries(self._conn, document_id, evidence_ids)

    def body_neighbours(self, document_id: str, pdf_page: int, ordinal: int, window: int) -> tuple[list[str], list[str]]:
        """Up to ``window`` body units before and after a position, as evidence IDs in reading order."""
        return retrieval_reads.read_body_neighbours(self._conn, document_id, pdf_page, ordinal, window)

    def section_headings(self, document_id: str, section_id: str | None) -> tuple[str | None, str | None]:
        """The heading unit IDs of a section and of its parent section."""
        return retrieval_reads.read_section_headings(self._conn, document_id, section_id)

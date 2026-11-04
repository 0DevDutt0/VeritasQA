"""SQLite schema for VeritasQA (ARCHITECTURE §6).

The statements below are the contract. ``PRAGMA user_version`` records the schema version, and a
database with another version, or with tables but no version, is refused rather than migrated.
"""

from __future__ import annotations

import sqlite3

from app.common.errors import StorageError

SCHEMA_VERSION = 1

_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE documents (
        document_id TEXT PRIMARY KEY,
        source_name TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        size_bytes INTEGER NOT NULL,
        page_count INTEGER NOT NULL CHECK (page_count >= 1),
        extractor_version TEXT NOT NULL,
        structure_version TEXT NOT NULL,
        pymupdf_version TEXT NOT NULL,
        pdfplumber_version TEXT NOT NULL,
        extraction_config_sha256 TEXT NOT NULL,
        structure_config_sha256 TEXT NOT NULL,
        issues_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE pages (
        document_id TEXT NOT NULL REFERENCES documents(document_id),
        pdf_page INTEGER NOT NULL CHECK (pdf_page >= 1),
        printed_page TEXT,
        width REAL NOT NULL,
        height REAL NOT NULL,
        rotation INTEGER NOT NULL,
        status TEXT NOT NULL,
        quality_status TEXT NOT NULL,
        extraction_method TEXT NOT NULL,
        warnings_json TEXT NOT NULL,
        raw_text TEXT NOT NULL,
        raw_text_sha256 TEXT NOT NULL,
        PRIMARY KEY (document_id, pdf_page)
    )
    """,
    """
    CREATE TABLE sections (
        section_id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL REFERENCES documents(document_id),
        position INTEGER NOT NULL,
        level INTEGER NOT NULL CHECK (level >= 1),
        title TEXT NOT NULL,
        parent_section_id TEXT REFERENCES sections(section_id),
        start_pdf_page INTEGER NOT NULL,
        heading_id TEXT NOT NULL REFERENCES evidence_units(evidence_id),
        UNIQUE (document_id, position)
    )
    """,
    """
    CREATE TABLE evidence_units (
        evidence_id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL REFERENCES documents(document_id),
        pdf_page INTEGER NOT NULL,
        printed_page TEXT,
        ordinal INTEGER NOT NULL CHECK (ordinal >= 1),
        content_type TEXT NOT NULL,
        raw_text TEXT NOT NULL,
        index_text TEXT NOT NULL,
        heading_text TEXT NOT NULL,
        section_id TEXT REFERENCES sections(section_id),
        parent_id TEXT REFERENCES evidence_units(evidence_id),
        prev_id TEXT REFERENCES evidence_units(evidence_id),
        next_id TEXT REFERENCES evidence_units(evidence_id),
        extraction_quality TEXT NOT NULL,
        body_retrieval INTEGER NOT NULL CHECK (body_retrieval IN (0, 1)),
        derived INTEGER NOT NULL CHECK (derived IN (0, 1)),
        table_id TEXT,
        row_index INTEGER,
        col_index INTEGER,
        row_header TEXT,
        col_header TEXT,
        caption TEXT,
        x0 REAL NOT NULL,
        y0 REAL NOT NULL,
        x1 REAL NOT NULL,
        y1 REAL NOT NULL,
        UNIQUE (document_id, pdf_page, ordinal),
        FOREIGN KEY (document_id, pdf_page) REFERENCES pages(document_id, pdf_page)
    )
    """,
    """
    CREATE TABLE source_locations (
        location_id INTEGER PRIMARY KEY,
        document_id TEXT NOT NULL REFERENCES documents(document_id),
        evidence_id TEXT NOT NULL REFERENCES evidence_units(evidence_id),
        span_index INTEGER NOT NULL CHECK (span_index >= 0),
        pdf_page INTEGER NOT NULL,
        source_start INTEGER NOT NULL CHECK (source_start >= 0),
        source_end INTEGER NOT NULL,
        UNIQUE (evidence_id, span_index),
        CHECK (source_start < source_end)
    )
    """,
    """
    CREATE TABLE table_cells (
        evidence_id TEXT PRIMARY KEY REFERENCES evidence_units(evidence_id),
        table_id TEXT NOT NULL,
        row_index INTEGER NOT NULL CHECK (row_index >= 0),
        col_index INTEGER NOT NULL CHECK (col_index >= 0),
        row_header TEXT,
        col_header TEXT,
        caption TEXT
    )
    """,
    """
    CREATE TABLE structure_issues (
        issue_id INTEGER PRIMARY KEY,
        document_id TEXT NOT NULL REFERENCES documents(document_id),
        pdf_page INTEGER NOT NULL,
        code TEXT NOT NULL,
        detail TEXT NOT NULL,
        FOREIGN KEY (document_id, pdf_page) REFERENCES pages(document_id, pdf_page)
    )
    """,
    """
    CREATE VIRTUAL TABLE evidence_fts USING fts5(
        index_text, heading_text, evidence_id UNINDEXED, document_id UNINDEXED
    )
    """,
    """
    CREATE TABLE evaluations (
        run_id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        split TEXT NOT NULL,
        config_json TEXT NOT NULL,
        metrics_json TEXT NOT NULL,
        dataset_sha256 TEXT NOT NULL
    )
    """,
)


def create_schema(conn: sqlite3.Connection) -> None:
    """Create every table in one transaction and record :data:`SCHEMA_VERSION`."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        for statement in _STATEMENTS:
            conn.execute(statement)
        conn.execute(f"PRAGMA user_version = {int(SCHEMA_VERSION)}")
        conn.execute("COMMIT")
    except sqlite3.Error:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the schema on an empty database; accept a matching one; refuse anything else."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version == SCHEMA_VERSION:
        return
    if version != 0:
        raise StorageError(
            f"the database schema is version {version}; this build expects version {SCHEMA_VERSION}"
        )
    existing = conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0]
    if existing:
        raise StorageError(
            "the database has tables but no VeritasQA schema version, so it is refused rather than changed"
        )
    create_schema(conn)

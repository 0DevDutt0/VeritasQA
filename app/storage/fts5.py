"""Startup check for the SQLite FTS5 features VeritasQA depends on.

VeritasQA relies on three SQLite capabilities:

1. the FTS5 virtual-table module,
2. the ``bm25()`` ranking function,
3. phrase queries (``MATCH '"alpha beta"'``).

Some Python builds ship SQLite without FTS5. The probe runs on a private in-memory database,
so it never touches a user's index file, and it fails loudly with :class:`StorageError` instead
of letting searches silently return nothing.
"""

from __future__ import annotations

import sqlite3

from app.common.errors import StorageError

_PROBE_TABLE = "veritasqa_fts5_probe"


def _run_probe(conn: sqlite3.Connection) -> None:
    conn.execute(f"CREATE VIRTUAL TABLE {_PROBE_TABLE} USING fts5(body)")
    conn.execute(
        f"INSERT INTO {_PROBE_TABLE}(body) VALUES (?)",
        ("alpha beta gamma",),
    )
    phrase_hits = conn.execute(
        f"SELECT COUNT(*) FROM {_PROBE_TABLE} WHERE {_PROBE_TABLE} MATCH ?",
        ('"alpha beta"',),
    ).fetchone()[0]
    if phrase_hits != 1:
        raise StorageError(f"FTS5 phrase query returned {phrase_hits} rows; expected 1")
    score = conn.execute(
        f"SELECT bm25({_PROBE_TABLE}) FROM {_PROBE_TABLE} WHERE {_PROBE_TABLE} MATCH ?",
        ("alpha",),
    ).fetchone()[0]
    if not isinstance(score, (int, float)):
        raise StorageError("FTS5 bm25() did not return a number")


def ensure_fts5_available() -> str:
    """Raise :class:`StorageError` unless FTS5, bm25() and phrase queries work.

    Returns the SQLite library version string on success.
    """
    try:
        conn = sqlite3.connect(":memory:")
    except sqlite3.Error as exc:  # pragma: no cover - in-memory connect does not fail in practice
        raise StorageError(f"Cannot open a SQLite probe connection: {exc}") from exc
    try:
        _run_probe(conn)
    except (sqlite3.Error, StorageError) as exc:
        raise StorageError(
            f"SQLite {sqlite3.sqlite_version} lacks the FTS5 features VeritasQA needs ({exc}). "
            "Use a Python build whose SQLite includes FTS5."
        ) from exc
    finally:
        conn.close()
    return sqlite3.sqlite_version


def fts5_available() -> bool:
    """Return True when :func:`ensure_fts5_available` succeeds."""
    try:
        ensure_fts5_available()
    except StorageError:
        return False
    return True

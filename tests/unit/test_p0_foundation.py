"""P0 exit criteria: package skeleton imports, the FTS5/BM25 startup probe works and fails loudly
when FTS5 is missing, SQLite BM25 ranks better matches first, and UTF-8 file helpers round-trip
non-ASCII text.

Run:  pytest tests/unit/test_p0_foundation.py -q
"""

from __future__ import annotations

import sqlite3

import pytest

from app import __version__
from app.common import files
from app.common.errors import StorageError, VeritasQAError
from app.storage import fts5


def test_package_skeleton_and_error_hierarchy():
    assert __version__ == "0.1.0"
    assert issubclass(StorageError, VeritasQAError)


def test_fts5_probe_passes_on_this_sqlite_build():
    version = fts5.ensure_fts5_available()
    assert version == sqlite3.sqlite_version
    assert fts5.fts5_available() is True


class _SqliteWithoutFts5:
    """Stand-in connection for a SQLite build compiled without the FTS5 module."""

    def execute(self, sql, params=()):
        raise sqlite3.OperationalError("no such module: fts5")

    def close(self):
        return None


def test_missing_fts5_fails_loudly(monkeypatch):
    monkeypatch.setattr(fts5.sqlite3, "connect", lambda *args, **kwargs: _SqliteWithoutFts5())
    assert fts5.fts5_available() is False
    with pytest.raises(StorageError, match="FTS5"):
        fts5.ensure_fts5_available()


def test_bm25_ranks_better_match_first_and_scores_are_negative():
    # SQLite FTS5 returns smaller (more negative) bm25() values for better matches.
    # VeritasQA sorts by bm25() ascending, so this test pins the direction the engine relies on.
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE VIRTUAL TABLE docs USING fts5(body)")
        conn.executemany(
            "INSERT INTO docs(body) VALUES (?)",
            [("alpha gamma delta epsilon zeta",), ("alpha alpha alpha beta",)],
        )
        rows = conn.execute(
            "SELECT body, bm25(docs) FROM docs WHERE docs MATCH ? ORDER BY bm25(docs)",
            ("alpha",),
        ).fetchall()
    finally:
        conn.close()
    assert rows[0][0] == "alpha alpha alpha beta"
    assert rows[0][1] < rows[1][1] < 0


def test_phrase_query_requires_adjacent_terms():
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE VIRTUAL TABLE docs USING fts5(body)")
        conn.executemany(
            "INSERT INTO docs(body) VALUES (?)",
            [("alpha beta is adjacent",), ("alpha gamma beta is not",)],
        )
        hits = conn.execute(
            "SELECT body FROM docs WHERE docs MATCH ?", ('"alpha beta"',)
        ).fetchall()
    finally:
        conn.close()
    assert hits == [("alpha beta is adjacent",)]


def test_utf8_round_trip_preserves_non_ascii(tmp_path):
    text = "Café — naïve 東京 €100 ﬁ 👍 combining é مرحبا"
    path = files.write_json(tmp_path / "unicode.json", {"text": text})

    assert files.read_json(path)["text"] == text

    raw = path.read_bytes()
    raw.decode("utf-8")  # must be valid UTF-8, not cp1252
    assert "Café".encode("utf-8") in raw
    assert b"\r\n" not in raw  # LF newlines on every platform


def test_write_text_creates_parent_directories(tmp_path):
    target = files.write_text(tmp_path / "a" / "b" / "note.txt", "ümlaut\n")
    assert target.read_text(encoding="utf-8") == "ümlaut\n"

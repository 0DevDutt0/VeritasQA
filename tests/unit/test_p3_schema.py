"""P3 schema: the tables of ARCHITECTURE §6, the version marker, foreign keys and the open-time checks."""

from __future__ import annotations

import sqlite3

import pytest

from app.common.errors import StorageError
from app.storage import Store
from app.storage import store as store_module
from app.storage.schema import SCHEMA_VERSION

EXPECTED_TABLES = {
    "documents",
    "pages",
    "sections",
    "evidence_units",
    "source_locations",
    "table_cells",
    "structure_issues",
    "evidence_fts",
    "evaluations",
}


def _table_names(path) -> set[str]:
    with sqlite3.connect(str(path)) as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')").fetchall()
    return {row[0] for row in rows}


def test_open_creates_every_table_of_the_schema(tmp_path):
    path = tmp_path / "store.sqlite"
    with Store.open(path):
        pass
    assert EXPECTED_TABLES <= _table_names(path)


def test_schema_version_is_recorded_in_user_version(tmp_path):
    path = tmp_path / "store.sqlite"
    with Store.open(path):
        pass
    with sqlite3.connect(str(path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 1


def test_foreign_keys_are_enabled_on_every_open(tmp_path):
    path = tmp_path / "store.sqlite"
    for _ in range(2):
        with Store.open(path) as store:
            assert store._conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_a_reopened_store_keeps_its_documents(tmp_path):
    from tests.fixtures.store_records import DOC_A, sample_document

    path = tmp_path / "store.sqlite"
    extracted, structure = sample_document(DOC_A)
    with Store.open(path) as store:
        store.write_document(extracted, structure, created_at="2026-01-01T00:00:00Z")
    with Store.open(path) as store:
        assert store.document_ids() == [DOC_A]
        assert store.load_structure(DOC_A) == structure


def test_a_database_with_another_schema_version_is_refused(tmp_path):
    path = tmp_path / "store.sqlite"
    with Store.open(path):
        pass
    with sqlite3.connect(str(path)) as connection:
        connection.execute("PRAGMA user_version = 99")
    with pytest.raises(StorageError, match="schema is version 99"):
        Store.open(path)


def test_a_database_with_tables_but_no_version_is_refused(tmp_path):
    path = tmp_path / "other.sqlite"
    with sqlite3.connect(str(path)) as connection:
        connection.execute("CREATE TABLE unrelated (x INTEGER)")
    with pytest.raises(StorageError, match="no VeritasQA schema version"):
        Store.open(path)
    assert _table_names(path) == {"unrelated"}


def test_fts5_is_checked_when_the_store_opens(monkeypatch):
    def unavailable() -> str:
        raise StorageError("FTS5 is missing (simulated)")

    monkeypatch.setattr(store_module, "ensure_fts5_available", unavailable)
    with pytest.raises(StorageError, match="FTS5 is missing"):
        Store.open()


def test_the_context_manager_closes_the_connection():
    store = Store.open()
    with store:
        pass
    with pytest.raises(sqlite3.ProgrammingError):
        store._conn.execute("SELECT 1")


def test_a_document_id_is_bound_as_a_parameter_not_as_sql(tmp_path):
    path = tmp_path / "store.sqlite"
    hostile = "doc-x'); DROP TABLE documents; --"
    with Store.open(path) as store:
        assert store.document_record(hostile) is None
        assert store.has_document(hostile) is False
        assert store.load_unit(hostile, "anything") is None
    assert EXPECTED_TABLES <= _table_names(path)

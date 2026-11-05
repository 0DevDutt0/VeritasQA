"""The evaluations table through the store (ARCHITECTURE §17.12; D85). The schema is not changed."""

import pytest

from app.common.errors import StorageError
from app.storage import Store
from app.storage.schema import SCHEMA_VERSION


def test_a_recorded_run_reads_back_unchanged():
    store = Store.open(":memory:")
    try:
        store.record_evaluation(
            run_id="run-1",
            created_at="2026-01-01T00:00:00Z",
            split="dev",
            config_json='{"split": "dev"}',
            metrics_json='{"outcomes": {}}',
            dataset_sha256="0" * 64,
        )
        row = store.read_evaluation("run-1")
    finally:
        store.close()
    assert row == {
        "run_id": "run-1",
        "created_at": "2026-01-01T00:00:00Z",
        "split": "dev",
        "config_json": '{"split": "dev"}',
        "metrics_json": '{"outcomes": {}}',
        "dataset_sha256": "0" * 64,
    }


def test_an_unknown_run_reads_as_none():
    store = Store.open(":memory:")
    try:
        assert store.read_evaluation("missing") is None
    finally:
        store.close()


def test_a_repeated_run_id_is_refused_and_the_first_row_is_kept():
    store = Store.open(":memory:")
    try:
        store.record_evaluation(
            run_id="run-1", created_at="t1", split="dev", config_json="{}", metrics_json='{"a": 1}', dataset_sha256="a" * 64
        )
        with pytest.raises(StorageError, match="already recorded"):
            store.record_evaluation(
                run_id="run-1", created_at="t2", split="dev", config_json="{}", metrics_json='{"a": 2}', dataset_sha256="b" * 64
            )
        assert store.read_evaluation("run-1")["metrics_json"] == '{"a": 1}'
    finally:
        store.close()


def test_the_schema_version_is_unchanged_by_the_evaluation_rows():
    store = Store.open(":memory:")
    try:
        version = store._conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        store.close()
    assert version == SCHEMA_VERSION

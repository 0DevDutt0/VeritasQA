"""P3 repository: round trip, write rules (nothing written on failure), rewrites, rollback and isolation."""

from __future__ import annotations

import sqlite3

import pytest

from app.common.errors import StorageError, StorageIntegrityError
from app.document_structure.models import ContentType
from app.storage import Store, repository
from tests.fixtures.store_records import DOC_A, DOC_B, make_page, sample_document, sha256_text

CREATED = "2026-01-01T00:00:00Z"
DOCUMENT_TABLES = (
    "documents",
    "pages",
    "sections",
    "evidence_units",
    "source_locations",
    "table_cells",
    "structure_issues",
    "evidence_fts",
)


def _count(store: Store, table: str, document_id: str) -> int:
    if table == "documents":
        sql = "SELECT COUNT(*) FROM documents WHERE document_id = ?"
    elif table == "evidence_fts":
        sql = "SELECT COUNT(*) FROM evidence_fts WHERE document_id = ?"
    elif table == "table_cells":
        sql = (
            "SELECT COUNT(*) FROM table_cells t JOIN evidence_units u ON u.evidence_id = t.evidence_id "
            "WHERE u.document_id = ?"
        )
    elif table == "source_locations":
        sql = "SELECT COUNT(*) FROM source_locations WHERE document_id = ?"
    else:
        sql = f"SELECT COUNT(*) FROM {table} WHERE document_id = ?"
    return store._conn.execute(sql, (document_id,)).fetchone()[0]


def _counts(store: Store, document_id: str) -> dict[str, int]:
    return {table: _count(store, table, document_id) for table in DOCUMENT_TABLES}


def test_a_written_structure_is_read_back_equal(tmp_path):
    extracted, structure = sample_document(DOC_A)
    with Store.open(tmp_path / "store.sqlite") as store:
        store.write_document(extracted, structure, created_at=CREATED)
        assert store.load_structure(DOC_A) == structure


def test_a_multi_span_unit_has_one_location_row_per_span(tmp_path):
    extracted, structure = sample_document(DOC_A)
    row_unit = next(unit for unit in structure.units if unit.content_type == ContentType.TABLE_ROW)
    assert len(row_unit.source_spans) == 3
    with Store.open(tmp_path / "store.sqlite") as store:
        store.write_document(extracted, structure, created_at=CREATED)
        rows = store._conn.execute(
            "SELECT span_index, source_start, source_end FROM source_locations WHERE evidence_id = ? "
            "ORDER BY span_index",
            (row_unit.evidence_id,),
        ).fetchall()
        assert [(row["span_index"], row["source_start"], row["source_end"]) for row in rows] == [
            (index, start, end) for index, (start, end) in enumerate(row_unit.source_spans)
        ]
        assert store.load_unit(DOC_A, row_unit.evidence_id) == row_unit


def test_only_body_retrieval_units_enter_the_fts_index(tmp_path):
    extracted, structure = sample_document(DOC_A)
    footer = next(unit for unit in structure.units if unit.content_type == ContentType.FOOTER)
    body = [unit for unit in structure.units if unit.body_retrieval]
    with Store.open(tmp_path / "store.sqlite") as store:
        store.write_document(extracted, structure, created_at=CREATED)
        indexed = {row[0] for row in store._conn.execute("SELECT evidence_id FROM evidence_fts")}
        assert footer.evidence_id not in indexed
        assert indexed == {unit.evidence_id for unit in body}


def test_derived_table_rows_are_indexed_and_marked_derived(tmp_path):
    extracted, structure = sample_document(DOC_A)
    row_unit = next(unit for unit in structure.units if unit.content_type == ContentType.TABLE_ROW)
    with Store.open(tmp_path / "store.sqlite") as store:
        store.write_document(extracted, structure, created_at=CREATED)
        indexed = {row[0] for row in store._conn.execute("SELECT evidence_id FROM evidence_fts")}
        assert row_unit.evidence_id in indexed
        assert store.load_unit(DOC_A, row_unit.evidence_id).derived is True


def test_rewriting_a_document_replaces_its_rows(tmp_path):
    extracted, structure = sample_document(DOC_A)
    with Store.open(tmp_path / "store.sqlite") as store:
        store.write_document(extracted, structure, created_at=CREATED)
        first = _counts(store, DOC_A)
        store.write_document(extracted, structure, created_at="2026-02-02T00:00:00Z")
        assert _counts(store, DOC_A) == first
        assert store.document_record(DOC_A).created_at == "2026-02-02T00:00:00Z"
        assert store.load_structure(DOC_A) == structure


def test_a_failed_rewrite_keeps_the_previous_version(tmp_path, monkeypatch):
    extracted, structure = sample_document(DOC_A)
    changed = structure.model_copy(update={"config_sha256": "f" * 64})
    with Store.open(tmp_path / "store.sqlite") as store:
        store.write_document(extracted, structure, created_at=CREATED)

        def fail(conn, _structure):
            raise RuntimeError("simulated failure during the FTS insert")

        monkeypatch.setattr(repository, "insert_fts", fail)
        with pytest.raises(RuntimeError, match="simulated failure"):
            store.write_document(extracted, changed, created_at=CREATED)
        assert store.load_structure(DOC_A) == structure
        assert store._conn.in_transaction is False


def test_a_failed_first_write_leaves_no_rows(tmp_path, monkeypatch):
    extracted, structure = sample_document(DOC_A)
    with Store.open(tmp_path / "store.sqlite") as store:

        def fail(conn, _structure):
            raise sqlite3.OperationalError("simulated disk failure while writing units")

        monkeypatch.setattr(repository, "insert_units", fail)
        with pytest.raises(StorageError, match="could not write document"):
            store.write_document(extracted, structure, created_at=CREATED)
        assert store.document_ids() == []
        assert all(count == 0 for count in _counts(store, DOC_A).values())
        assert store._conn.in_transaction is False


def test_two_documents_coexist_and_stay_separate(tmp_path):
    extracted_a, structure_a = sample_document(DOC_A)
    extracted_b, structure_b = sample_document(DOC_B)
    with Store.open(tmp_path / "store.sqlite") as store:
        store.write_document(extracted_a, structure_a, created_at=CREATED)
        store.write_document(extracted_b, structure_b, created_at=CREATED)
        assert store.document_ids() == sorted([DOC_A, DOC_B])
        assert store.load_structure(DOC_A) == structure_a
        assert store.load_structure(DOC_B) == structure_b
        assert all(unit.document_id == DOC_A for unit in store.load_structure(DOC_A).units)


def test_rewriting_one_document_leaves_the_other_untouched(tmp_path):
    extracted_a, structure_a = sample_document(DOC_A)
    extracted_b, structure_b = sample_document(DOC_B)
    with Store.open(tmp_path / "store.sqlite") as store:
        store.write_document(extracted_a, structure_a, created_at=CREATED)
        store.write_document(extracted_b, structure_b, created_at=CREATED)
        before = _counts(store, DOC_B)
        store.write_document(extracted_a, structure_a, created_at="2026-03-03T00:00:00Z")
        assert _counts(store, DOC_B) == before
        assert store.load_structure(DOC_B) == structure_b


def test_document_record_carries_the_provenance_fields(tmp_path):
    extracted, structure = sample_document(DOC_A)
    with Store.open(tmp_path / "store.sqlite") as store:
        store.write_document(extracted, structure, created_at=CREATED)
        record = store.document_record(DOC_A)
    assert record.source_name == extracted.source_name
    assert record.sha256 == extracted.sha256
    assert record.page_count == 2
    assert record.structure_version == structure.structure_version
    assert record.extraction_config_sha256 == extracted.config_sha256
    assert record.structure_config_sha256 == structure.config_sha256
    assert record.created_at == CREATED


def test_foreign_keys_are_satisfied_after_a_write(tmp_path):
    extracted, structure = sample_document(DOC_A)
    with Store.open(tmp_path / "store.sqlite") as store:
        store.write_document(extracted, structure, created_at=CREATED)
        assert store._conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_a_page_without_stored_text_is_an_integrity_error(tmp_path):
    extracted, structure = sample_document(DOC_A)
    with Store.open(tmp_path / "store.sqlite") as store:
        store.write_document(extracted, structure, created_at=CREATED)
        with pytest.raises(StorageIntegrityError, match="no stored text"):
            store.page_texts(DOC_A, [1, 99])


def test_an_unknown_document_cannot_be_loaded(tmp_path):
    with Store.open(tmp_path / "store.sqlite") as store:
        with pytest.raises(StorageError, match="holds no document"):
            store.load_structure(DOC_A)


def _mutate_structure(structure, change):
    units = [unit.model_copy() for unit in structure.units]
    sections = [section.model_copy() for section in structure.sections]
    cells = [cell.model_copy() for cell in structure.table_cells]
    result = structure.model_copy(update={"units": units, "sections": sections, "table_cells": cells})
    change(result)
    return result


def _mutate_page_text(extracted, change):
    pages = [page.model_copy() for page in extracted.pages]
    result = extracted.model_copy(update={"pages": pages})
    change(result)
    return result


def _replace_unit(result, index, **updates):
    result.units[index] = result.units[index].model_copy(update=updates)


CASES = {
    "structure belongs to another document": lambda extracted, structure: (
        extracted,
        structure.model_copy(update={"document_id": DOC_B}),
    ),
    "page hash does not match its text": lambda extracted, structure: (
        _mutate_page_text(extracted, lambda record: setattr(record.pages[0], "raw_text", "changed text")),
        structure,
    ),
    "spans do not reproduce raw_text": lambda extracted, structure: (
        extracted,
        _mutate_structure(structure, lambda record: _replace_unit(record, 1, raw_text="not the source")),
    ),
    "a span leaves its page": lambda extracted, structure: (
        extracted,
        _mutate_structure(structure, lambda record: _replace_unit(record, 1, source_spans=[(0, 10**6)])),
    ),
    "a unit names a missing page": lambda extracted, structure: (
        extracted,
        _mutate_structure(structure, lambda record: _replace_unit(record, 1, pdf_page=9)),
    ),
    "a unit names a missing parent": lambda extracted, structure: (
        extracted,
        _mutate_structure(structure, lambda record: _replace_unit(record, 1, parent_id="nope")),
    ),
    "a section names a missing heading": lambda extracted, structure: (
        extracted,
        _mutate_structure(
            structure,
            lambda record: record.sections.__setitem__(0, record.sections[0].model_copy(update={"heading_id": "nope"})),
        ),
    ),
    "a table cell record disagrees with its unit": lambda extracted, structure: (
        extracted,
        _mutate_structure(
            structure,
            lambda record: record.table_cells.__setitem__(
                0, record.table_cells[0].model_copy(update={"col_header": "Wrong"})
            ),
        ),
    ),
    "evidence IDs repeat": lambda extracted, structure: (
        extracted,
        _mutate_structure(structure, lambda record: _replace_unit(record, 2, evidence_id=record.units[1].evidence_id)),
    ),
}


@pytest.mark.parametrize("case", sorted(CASES))
def test_an_inconsistent_record_is_refused_and_nothing_is_written(tmp_path, case):
    extracted, structure = sample_document(DOC_A)
    bad_extracted, bad_structure = CASES[case](extracted, structure)
    with Store.open(tmp_path / "store.sqlite") as store:
        with pytest.raises(StorageIntegrityError):
            store.write_document(bad_extracted, bad_structure, created_at=CREATED)
        assert store.document_ids() == []


def test_a_page_record_with_a_wrong_page_number_is_refused(tmp_path):
    extracted, structure = sample_document(DOC_A)
    extra = make_page(3, "A page that is recorded as page three but sits in position two.")
    pages = [extracted.pages[0], extra]
    bad = extracted.model_copy(update={"pages": pages})
    with Store.open(tmp_path / "store.sqlite") as store:
        with pytest.raises(StorageIntegrityError, match="recorded as page 3"):
            store.write_document(bad, structure, created_at=CREATED)


def test_the_hashes_match_the_page_text_used_in_the_fixture():
    extracted, _ = sample_document(DOC_A)
    for page in extracted.pages:
        assert page.raw_text_sha256 == sha256_text(page.raw_text)

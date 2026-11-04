"""SQLite persistence and FTS5 index (ARCHITECTURE §6, §12)."""

from app.common.errors import StorageError, StorageIntegrityError
from app.storage.fts5 import ensure_fts5_available, fts5_available
from app.storage.store import DocumentRecord, Store

__all__ = [
    "DocumentRecord",
    "Store",
    "StorageError",
    "StorageIntegrityError",
    "ensure_fts5_available",
    "fts5_available",
]

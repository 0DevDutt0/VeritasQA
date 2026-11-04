"""Explicit exception hierarchy.

Every failure the engine reports is a ``VeritasQAError``, so callers can catch the family
without catching unrelated bugs. Phase-specific subclasses are added where they are first used.
"""

from __future__ import annotations


class VeritasQAError(Exception):
    """Base class for all errors raised by VeritasQA."""


class StorageError(VeritasQAError):
    """A persistence or SQLite capability problem, for example a build without FTS5."""


class StorageIntegrityError(StorageError):
    """A record handed to the store is inconsistent: its hashes, spans or references do not hold. Nothing is written."""


class QueryError(VeritasQAError):
    """A query cannot be built from the text given, for example a phrase with no letters or digits."""

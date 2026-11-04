"""Errors raised by evidence selection (ARCHITECTURE §14)."""

from __future__ import annotations

from app.common.errors import VeritasQAError


class SelectionError(VeritasQAError):
    """The inputs to selection do not line up: a missing retrieval result, a result for a different query, or a
    retrieved unit that was not loaded."""

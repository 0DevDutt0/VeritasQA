"""Errors of the conflict screen (ARCHITECTURE §16)."""

from __future__ import annotations

from app.common.errors import VeritasQAError


class ConflictConfigError(VeritasQAError):
    """``config/conflict.toml`` is missing, is not valid TOML, or does not match its schema."""

"""Errors of the retrieval configuration and rules (ARCHITECTURE §13)."""

from __future__ import annotations

from app.common.errors import VeritasQAError


class RetrievalConfigError(VeritasQAError):
    """A retrieval configuration file is missing, is not valid TOML, or fails validation."""


class RuleConfigError(RetrievalConfigError):
    """A synonym or stemming rule is invalid, or it fails one of its own examples."""

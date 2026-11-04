"""Errors raised by question analysis (ARCHITECTURE §14)."""

from __future__ import annotations

from app.common.errors import VeritasQAError


class QuestionError(VeritasQAError):
    """The question is not usable text: it is not a string, it is blank, or it has no letter or digit."""

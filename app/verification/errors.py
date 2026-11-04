"""Errors raised by the verification package (ARCHITECTURE §15)."""

from __future__ import annotations

from app.common.errors import VeritasQAError


class VerificationError(VeritasQAError):
    """The inputs do not line up: the component is missing, its question type differs from the candidate's, or the
    component is not searchable. A problem with the passage itself is a FAIL in the report, never an exception."""

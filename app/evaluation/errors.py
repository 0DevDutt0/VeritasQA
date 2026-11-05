"""Errors of the evaluation harness (ARCHITECTURE §17)."""

from __future__ import annotations

from app.common.errors import VeritasQAError


class EvaluationError(VeritasQAError):
    """The harness was given inputs that do not fit together: a split that is not allowed, a mixed run, an unknown
    document or a component that the response does not have. This is a caller error, not a measured result."""


class GoldError(EvaluationError):
    """A gold record is invalid: its shape, its internal consistency, or its quotations against the stored text
    (ARCHITECTURE §17.3 and §17.4). The message names the record and the reason."""

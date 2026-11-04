"""Errors of the decision step (ARCHITECTURE §16)."""

from __future__ import annotations

from app.common.errors import VeritasQAError


class DecisionError(VeritasQAError):
    """The decision step was given inputs that do not fit together. This is a programming error, not an abstention."""


class PolicyError(DecisionError):
    """``config/acceptance_policy.toml`` is missing, is not valid TOML, or does not match its schema."""

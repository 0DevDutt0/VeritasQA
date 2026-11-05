"""Errors of the command line (ARCHITECTURE §19.4)."""

from __future__ import annotations

from app.common.errors import VeritasQAError


class CliError(VeritasQAError):
    """A command cannot act on what it was given: a missing store or file, an unknown document, or a guard that refuses."""

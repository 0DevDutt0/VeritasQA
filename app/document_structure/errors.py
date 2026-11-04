"""Structure errors. Every failure raised by the structure package is a StructureError."""

from __future__ import annotations

from app.common.errors import VeritasQAError


class StructureError(VeritasQAError):
    """A structure build could not run, or its output broke a provenance invariant."""


class StructureConfigError(StructureError):
    """The structure configuration is missing, is not valid TOML, or fails validation."""

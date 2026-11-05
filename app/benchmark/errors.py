"""Errors of the benchmark and sweep package (ARCHITECTURE §18)."""

from __future__ import annotations

from app.common.errors import VeritasQAError


class BenchmarkError(VeritasQAError):
    """A sweep or baseline was given inputs that do not fit together: an id that is not a plain name, a file or a
    store row that already exists, an unknown document, or a missing optional library. This is a caller error, not a
    measured result. A sweep raises it before it writes anything, except where ARCHITECTURE §18.3 says otherwise."""

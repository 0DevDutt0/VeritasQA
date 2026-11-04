"""UTF-8 file helpers.

Every text file VeritasQA reads or writes goes through these helpers, so the encoding never
depends on the platform default (cp1252 on Windows). Files are written with LF newlines so
that generated artifacts are byte-identical across operating systems.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_text(path: Path | str) -> str:
    """Read a UTF-8 text file."""
    return Path(path).read_text(encoding="utf-8")


def write_text(path: Path | str, text: str) -> Path:
    """Write a UTF-8 text file, creating parent directories as needed."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")
    return target


def write_json(path: Path | str, payload: Any) -> Path:
    """Write JSON with Unicode characters kept as-is (not escaped)."""
    return write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def read_json(path: Path | str) -> Any:
    """Read a JSON file written by :func:`write_json`."""
    return json.loads(read_text(path))

"""Tesseract OCR adapter (P1). It runs only when a command is available, and it never uses a shell.

The output of tesseract is UTF-8 text. It is tagged ``ocr_tesseract`` and is unverified by
definition (ARCHITECTURE §10). This module does not decide whether a page is scanned. That is
the extractor's job.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Sequence

from app.ingestion.errors import OcrError

_FORM_FEED = "\x0c"  # tesseract ends each page with a form feed


def tesseract_available() -> bool:
    """True when the ``tesseract`` executable is on PATH."""
    return shutil.which("tesseract") is not None


def ocr_page(
    image_path: Path | str,
    *,
    language: str,
    timeout_seconds: float,
    command: Sequence[str] | None = None,
) -> str:
    """Run tesseract on one image and return its text.

    ``command`` replaces the default executable. It is used by the tests to run a stub, and it is
    a list of arguments, never a shell string. Raises OcrError on any failure.
    """
    if command is None:
        executable = shutil.which("tesseract")
        if executable is None:
            raise OcrError("tesseract is not on PATH")
        prefix = [executable]
    else:
        prefix = list(command)
        if not prefix:
            raise OcrError("the OCR command is empty")
    argv = [*prefix, str(image_path), "stdout", "-l", language]
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            check=False,
            shell=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise OcrError(f"tesseract did not finish within {timeout_seconds} seconds") from exc
    except OSError as exc:
        raise OcrError(f"tesseract could not be started: {exc.strerror or type(exc).__name__}") from exc
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()[:300]
        raise OcrError(f"tesseract exited with status {completed.returncode}: {stderr}")
    text = completed.stdout.decode("utf-8", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace(_FORM_FEED, "")
    return text.strip()

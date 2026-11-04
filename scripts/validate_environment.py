"""Validate the VeritasQA V1 baseline environment. Run it with the project interpreter:

    VeritasQA\\Scripts\\python.exe scripts\\validate_environment.py

Exit status: 0 when every baseline check passes, 1 when a baseline check fails, 2 when the
interpreter is not a virtual environment. Optional groups are not reported here: the baseline
does not depend on them (D17; P0-CLEAN).
"""

from __future__ import annotations

import io
import sys
from importlib import metadata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# Distribution names differ from import names for some pins in requirements.txt.
DISTRIBUTION_NAMES = {"pymupdf": "PyMuPDF"}


def _line(status: str, label: str, detail: str = "") -> None:
    print(f"[{status}] {label}" + (f": {detail}" if detail else ""))


def _pinned_baseline() -> dict[str, str]:
    pins: dict[str, str] = {}
    for raw in (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if "==" in line:
            name, version = line.split("==", 1)
            pins[name.strip().lower()] = version.strip()
    return pins


def check_interpreter() -> bool:
    in_venv = sys.prefix != sys.base_prefix
    _line("INFO", "interpreter", sys.executable)
    _line("INFO", "python version", sys.version.split()[0])
    _line("INFO", "sys.prefix", sys.prefix)
    _line("INFO", "sys.base_prefix", sys.base_prefix)
    _line("INFO", "pip", metadata.version("pip"))
    _line("PASS" if in_venv else "FAIL", "running inside a virtual environment", str(in_venv))
    return in_venv


def check_baseline_pins() -> bool:
    ok = True
    for name, pinned in _pinned_baseline().items():
        dist = DISTRIBUTION_NAMES.get(name, name)
        try:
            installed = metadata.version(dist)
        except metadata.PackageNotFoundError:
            installed = "not installed"
        matches = installed == pinned
        ok &= matches
        _line("PASS" if matches else "FAIL", f"baseline pin {name}", f"pinned {pinned}, installed {installed}")
    return ok


def check_baseline_imports() -> bool:
    ok = True
    for module in ("fitz", "pdfplumber", "pydantic", "pytest"):
        try:
            __import__(module)
            _line("PASS", f"import {module}")
        except ImportError as exc:
            ok = False
            _line("FAIL", f"import {module}", str(exc))
    return ok


def check_fts5() -> bool:
    import sqlite3

    from app.storage import fts5

    try:
        version = fts5.ensure_fts5_available()
    except Exception as exc:  # StorageError or sqlite failure: both fail the check
        _line("FAIL", "SQLite FTS5 probe", str(exc))
        return False
    _line("PASS", "SQLite FTS5 probe (phrase and bm25)", f"sqlite {version} (module {sqlite3.sqlite_version})")
    return True


def check_pdf_round_trip() -> bool:
    """Create a synthetic PDF in memory and read it back with PyMuPDF and pdfplumber."""
    import fitz
    import pdfplumber

    marker = "Synthetic clause: the warranty lasts 24 months."
    try:
        document = fitz.open()
        page = document.new_page()
        page.insert_text((72, 72), marker)
        data = document.tobytes()
        document.close()

        with fitz.open(stream=data, filetype="pdf") as reopened:
            pymupdf_text = reopened[0].get_text()
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            plumber_text = pdf.pages[0].extract_text() or ""
    except Exception as exc:
        _line("FAIL", "PDF round trip (synthetic document)", str(exc))
        return False
    ok = "24 months" in pymupdf_text and "24 months" in plumber_text
    _line(
        "PASS" if ok else "FAIL",
        "PDF round trip (synthetic document, PyMuPDF and pdfplumber)",
        f"fitz {fitz.VersionBind}, pdfplumber {metadata.version('pdfplumber')}",
    )
    return ok


def main() -> int:
    print("VeritasQA environment validation (V1 baseline)")
    print(f"repository: {REPO_ROOT}")
    if not check_interpreter():
        print("RESULT: not a virtual environment. Use the project venv (VeritasQA\\Scripts\\python.exe).")
        return 2
    results = [check_baseline_pins(), check_baseline_imports(), check_fts5(), check_pdf_round_trip()]
    ok = all(results)
    print("RESULT:", "baseline valid" if ok else "baseline has failures")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

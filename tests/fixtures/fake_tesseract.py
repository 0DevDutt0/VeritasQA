"""Stub standing in for the tesseract executable in the P1 tests.

It checks the argument list that app/ingestion/ocr.py must send (image, "stdout", "-l", language)
and then prints fixed text. The environment variable FAKE_TESSERACT_MODE selects a failure:
"fail" exits with status 3, and "empty" prints nothing.
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    argv = sys.argv
    if len(argv) != 5 or argv[2] != "stdout" or argv[3] != "-l" or not os.path.isfile(argv[1]):
        sys.stderr.write(f"unexpected arguments: {argv[1:]}\n")
        return 2
    mode = os.environ.get("FAKE_TESSERACT_MODE", "")
    if mode == "fail":
        sys.stderr.write("simulated tesseract failure\n")
        return 3
    if mode == "empty":
        return 0
    text = f"Stub OCR language {argv[4]}\nStub OCR line two\n\x0c"
    sys.stdout.buffer.write(text.encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

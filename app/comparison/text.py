"""Text normalization for the document comparison (P15, ARCHITECTURE §20.3).

The owner's rule: spaces and line breaks do not count, and a hyphen at a line end is joined to the next line. Nothing
else is changed, so case, digits and punctuation still count as changes. This is deliberately not the index
normalization in ``app.common.text``, which also folds quotes and dashes.
"""

from __future__ import annotations

import re

# A hyphen, a Unicode hyphen or a soft hyphen at a line end, with the line break and the indent of the next line.
_LINE_END_HYPHEN = re.compile("[-­‐][ \t]*\r?\n[ \t]*")


def normalize_page_text(raw: str) -> str:
    """Return the comparison text of one page: line-end hyphens joined, whitespace collapsed to single spaces, trimmed."""
    return " ".join(_LINE_END_HYPHEN.sub("", raw).split())

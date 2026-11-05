"""Synthetic document for the sweep tests (ARCHITECTURE §18, D97). Labelled synthetic; no PDF is read.

The query "quarterly" (the retrieval text of "What is quarterly?") matches two units:
- the body sentence GOLD_QUOTE, which is the gold passage, and
- a unit whose heading is "Quarterly review" (HEADING_UNIT_TEXT).

With heading weight 1.0 (or 1.5) the gold passage ranks first. With heading weight 2.0 (or 4.0) the heading unit ranks
first, and the gold passage ranks second. So the heading weight decides the rank of the gold passage, and at K = 1 the
heading weights 2.0 and 4.0 leave it out. A sweep that ignores the heading weight gives a different answer, so a
test on this document cannot pass by accident (D97).
"""

from __future__ import annotations

from app.document_structure.models import ContentType
from tests.fixtures.retrieval_docs import Item, filler

DOC = "doc-" + "5" * 16
GOLD_QUOTE = "Quarterly means once every three months."
HEADING_UNIT_TEXT = "Visits are logged each week by the team for the period under review, with notes."


def sweep_items() -> list[Item]:
    """One page: filler, the heading unit, the gold sentence, more filler, a running header that is not body text."""
    return [
        *filler(20, page=1),
        Item(page=1, text=HEADING_UNIT_TEXT, heading="Quarterly review", index=HEADING_UNIT_TEXT),
        Item(page=1, text=GOLD_QUOTE),
        *filler(20, page=1),
        Item(page=1, text="Running header threshold assessment", content_type=ContentType.HEADER, body=False),
        *filler(5, page=1),
    ]

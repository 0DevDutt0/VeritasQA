"""The readable text report of one comparison (P15, ARCHITECTURE §20.5 and §20.6). Pure: it returns the text only."""

from __future__ import annotations

from app.comparison.documents import DocumentComparison
from app.comparison.pages import (
    ADDED,
    CHANGED,
    MOVED,
    NOT_COMPARABLE,
    REMOVED,
    UNCHANGED,
    PageDifference,
)

_LABELS = {
    UNCHANGED: "unchanged",
    CHANGED: "changed",
    MOVED: "moved",
    ADDED: "added",
    REMOVED: "removed",
    NOT_COMPARABLE: "not comparable",
}

_LIMITS = (
    "Limits: the comparison is text only, so a change to an image or a chart shows only if the text changes. "
    "It shows where the text changed, not whether the change matters. "
    "A printed page number that changes after an inserted page shows as a changed word on that page. "
    "A page that moved and also changed is shown as removed and added. "
    "Only a hyphen at a line end is joined, so a word that is hyphenated in one version and printed whole in the other "
    "shows as changed. A page with no readable text is not comparable until OCR is installed."
)


def render_report(comparison: DocumentComparison) -> str:
    """Return the report as plain text, with a line break at the end."""
    earlier, new = comparison.earlier, comparison.new
    lines = [
        "VeritasQA document comparison",
        "",
        f"Earlier version: {earlier.source_name} ({earlier.document_id}), {earlier.page_count} pages",
        f"New version:     {new.source_name} ({new.document_id}), {new.page_count} pages",
        "",
    ]
    lines.extend(f"Note: {notice}" for notice in comparison.notices)
    if comparison.notices:
        lines.append("")
    if comparison.status == "identical":
        lines.append("The two files are identical (same SHA-256). Nothing was compared page by page.")
    else:
        lines.append(
            "Result: the readable text of every page is the same."
            if comparison.text_identical
            else "Result: the readable text differs, or some pages could not be compared."
        )
        counts = comparison.counts
        lines.append("Pages: " + ", ".join(f"{counts[kind]} {_LABELS[kind]}" for kind in _LABELS))
        lines.extend(["", "Differences (earlier page -> new page)", "-" * 36])
        if not comparison.differences:
            lines.append("No differences in the readable text.")
        for difference in comparison.differences:
            lines.extend(_difference_lines(difference))
    lines.extend(["", _LIMITS])
    return "\n".join(lines) + "\n"


def _difference_lines(difference: PageDifference) -> list[str]:
    if difference.old_page is not None and difference.new_page is not None:
        where = f"earlier page {difference.old_page} -> new page {difference.new_page}"
    elif difference.old_page is not None:
        where = f"earlier page {difference.old_page}"
    else:
        where = f"new page {difference.new_page}"
    lines = [f"{where}: {_LABELS[difference.kind]}"]
    if difference.reason:
        lines.append(f"    {difference.reason}")
    if difference.old_warnings:
        lines.append(f"    warnings, earlier page: {', '.join(difference.old_warnings)}")
    if difference.new_warnings:
        lines.append(f"    warnings, new page: {', '.join(difference.new_warnings)}")
    for change in difference.changes:
        before = f'after "{change.context_before}", ' if change.context_before else ""
        lines.append(
            f'    {before}removed "{change.removed or "(nothing)"}", added "{change.added or "(nothing)"}"'
        )
    return lines

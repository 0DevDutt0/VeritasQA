"""Document-level comparison: the choice of the earlier version and the result for one pair (P15, ARCHITECTURE §20.1, §20.5)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.comparison.pages import (
    ADDED,
    CHANGED,
    MOVED,
    NOT_COMPARABLE,
    REMOVED,
    PageDifference,
    PageRecord,
    compare_pages,
)


@dataclass(frozen=True)
class DocumentInfo:
    """The stored facts of one document that the comparison needs."""

    document_id: str
    source_name: str
    sha256: str
    page_count: int
    extractor_version: str
    extraction_config_sha256: str


@dataclass(frozen=True)
class Selection:
    """The outcome of choosing the earlier version. ``status`` is ``compared``, ``identical`` or ``not_run``."""

    status: str
    reason: str
    earlier: DocumentInfo | None = None
    candidates: tuple[str, ...] = ()


@dataclass(frozen=True)
class DocumentComparison:
    """The result for one pair. ``status`` is ``identical`` (same SHA-256, nothing compared) or ``compared``."""

    status: str
    new: DocumentInfo
    earlier: DocumentInfo
    text_identical: bool
    counts: dict[str, int]
    differences: tuple[PageDifference, ...]
    notices: tuple[str, ...]


def select_earlier(
    new: DocumentInfo,
    stored: Sequence[DocumentInfo],
    *,
    against: str | None = None,
    same_file_before: DocumentInfo | None = None,
) -> Selection:
    """Choose the earlier version of ``new`` among ``stored``. ``new`` itself is never a candidate.

    ``same_file_before`` is the stored record that had the same document id before this ingest. It is set only by
    ``ingest``, and an equal SHA-256 there means the same file was already stored.
    """
    others = [document for document in stored if document.document_id != new.document_id]
    if against is not None:
        for document in others:
            if document.document_id == against:
                return Selection("compared", f"compared with {document.document_id}", earlier=document)
        return Selection("not_run", f"{against} is not an earlier version in the store")
    if same_file_before is not None and same_file_before.sha256 == new.sha256:
        return Selection(
            "identical",
            "the same file is already in the store (same SHA-256), so the two versions are identical and nothing was compared",
            earlier=same_file_before,
        )
    name = new.source_name.casefold()
    candidates = [document for document in others if document.source_name.casefold() == name]
    if not candidates:
        return Selection("not_run", f"no earlier version named '{new.source_name}' is in the store")
    if len(candidates) > 1:
        return Selection(
            "not_run",
            f"{len(candidates)} earlier versions named '{new.source_name}' are in the store; "
            "name the one to compare with --against <document_id>",
            candidates=tuple(document.document_id for document in candidates),
        )
    return Selection("compared", f"compared with {candidates[0].document_id}", earlier=candidates[0])


def compare_documents(
    *,
    new: DocumentInfo,
    earlier: DocumentInfo,
    new_pages: Sequence[PageRecord],
    earlier_pages: Sequence[PageRecord],
) -> DocumentComparison:
    """Compare two stored versions. Equal SHA-256 means identical files, and the page comparison is not run."""
    if earlier.sha256 == new.sha256:
        return DocumentComparison("identical", new, earlier, True, {}, (), ())
    notices: list[str] = []
    if (earlier.extractor_version, earlier.extraction_config_sha256) != (new.extractor_version, new.extraction_config_sha256):
        notices.append(
            "The two versions were extracted with different settings "
            f"(extractor {earlier.extractor_version} and {new.extractor_version}), "
            "so some differences may come from the extraction, not from the document."
        )
    page = compare_pages(earlier_pages, new_pages)
    text_identical = not any(page.counts[kind] for kind in (CHANGED, MOVED, ADDED, REMOVED, NOT_COMPARABLE))
    return DocumentComparison(
        status="compared",
        new=new,
        earlier=earlier,
        text_identical=text_identical,
        counts=page.counts,
        differences=page.differences,
        notices=tuple(notices),
    )

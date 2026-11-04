"""Synthetic documents for the P4 retrieval tests, built as records (labelled synthetic; no PDF is read).

The documents are larger than the P3 sample on purpose. FTS5 clamps the IDF of a term that occurs in more
than half of a document's units to 1e-6, so on a tiny document the scores tie and the ranking tests would
check nothing (ARCHITECTURE §13). Each query term used by the tests occurs in fewer than half the units,
and ``assert_idf_is_informative`` checks that before a test relies on a ranking.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.document_structure.models import ContentType, DocumentStructure, EvidenceUnit, Section
from app.ingestion.models import ExtractedDocument, QualityStatus
from tests.fixtures.store_records import link_units, make_extracted, make_page, make_unit

DOC_LARGE = "doc-" + "1" * 16
DOC_LARGE_TWIN = "doc-" + "2" * 16

FILLER_SUBJECTS = [
    "the committee", "the archive", "the office", "the team", "the board", "the unit", "the panel", "the desk",
]
FILLER_VERBS = [
    "recorded the routine minutes",
    "closed the ordinary accounts",
    "filed the standard forms",
    "reviewed the usual schedule",
    "noted the expected dates",
    "confirmed the normal staffing",
]


@dataclass(frozen=True)
class Item:
    """One unit to build. ``page`` is 1-based and the units of a page keep their order."""

    page: int
    text: str
    content_type: ContentType = ContentType.PARAGRAPH
    section: str = "s1"
    heading: str | None = None
    index: str | None = None
    body: bool = True
    derived: bool = False
    quality: QualityStatus = QualityStatus.VERIFIED


@dataclass(frozen=True)
class SectionSpec:
    key: str
    title: str
    parent: str | None = None


def filler(count: int, *, page: int, section: str = "s1") -> list[Item]:
    """Ordinary sentences with no query term used by the tests (threshold, assessment, quarterly, limit)."""
    items: list[Item] = []
    for number in range(count):
        subject = FILLER_SUBJECTS[number % len(FILLER_SUBJECTS)]
        verb = FILLER_VERBS[(number // len(FILLER_SUBJECTS)) % len(FILLER_VERBS)]
        items.append(Item(page=page, text=f"Note {number + 1}: {subject} {verb} for the period.", section=section))
    return items


def _section_heading(spec: SectionSpec, page: int) -> Item:
    return Item(page=page, text=spec.title, content_type=ContentType.HEADING, section=spec.key, heading=spec.title)


def build(
    document_id: str,
    items: list[Item],
    sections: list[SectionSpec] | None = None,
) -> tuple[ExtractedDocument, DocumentStructure]:
    """Build a document from ``items``. A heading unit is added for every section that has none."""
    sections = sections or [SectionSpec("s1", "Section One")]
    titles = {spec.key: spec for spec in sections}
    has_heading = {item.section for item in items if item.content_type == ContentType.HEADING}
    first_page = min(item.page for item in items)
    ordered = [_section_heading(spec, first_page) for spec in sections if spec.key not in has_heading] + items
    pages = sorted({item.page for item in ordered})
    if pages != list(range(1, len(pages) + 1)):
        raise ValueError("the synthetic pages must be numbered 1, 2, 3 and so on without gaps")

    page_text: dict[int, str] = {}
    spans: dict[int, list[tuple[int, int]]] = {page: [] for page in pages}
    for page in pages:
        text = ""
        for item in ordered:
            if item.page != page:
                continue
            if text:
                text += "\n\n"
            start = len(text)
            text += item.text
            spans[page].append((start, len(text)))
        page_text[page] = text

    extracted = make_extracted(document_id, [make_page(page, page_text[page]) for page in pages])
    units: list[EvidenceUnit] = []
    ordinals: dict[int, int] = {page: 0 for page in pages}
    section_ids = {spec.key: f"{document_id}:s{index:04d}" for index, spec in enumerate(sections, start=1)}
    cursor: dict[int, int] = {page: 0 for page in pages}
    for item in ordered:
        ordinals[item.page] += 1
        ordinal = ordinals[item.page]
        start, end = spans[item.page][cursor[item.page]]
        cursor[item.page] += 1
        section_key = item.section if item.body else None
        unit = make_unit(
            document_id,
            item.page,
            ordinal,
            item.content_type,
            page_text[item.page],
            [(start, end)],
            index_text=item.index,
            heading_text=item.heading if item.heading is not None else titles[item.section].title,
            section_id=section_ids[section_key] if section_key is not None else None,
            body_retrieval=item.body,
            derived=item.derived,
        )
        unit.extraction_quality = item.quality
        units.append(unit)
    link_units(units)

    structure_sections = []
    for spec in sections:
        heading = next(
            unit for unit in units if unit.section_id == section_ids[spec.key] and unit.content_type == ContentType.HEADING
        )
        structure_sections.append(
            Section(
                section_id=section_ids[spec.key],
                document_id=document_id,
                level=1 if spec.parent is None else 2,
                title=spec.title,
                parent_section_id=section_ids[spec.parent] if spec.parent else None,
                start_pdf_page=min(unit.pdf_page for unit in units if unit.section_id == section_ids[spec.key]),
                heading_id=heading.evidence_id,
            )
        )
    structure = DocumentStructure(
        document_id=document_id,
        config_sha256="e" * 64,
        sections=structure_sections,
        units=units,
        table_cells=[],
        issues=[],
    )
    return extracted, structure


def ranking_items(*, page_offset: int = 0) -> list[Item]:
    """Units for the ranking tests. Query terms: threshold, assessment, quarterly.

    The filler (45 units) keeps every query term in at most three units, so each term's IDF is positive.
    """
    p = 1 + page_offset
    items = filler(20, page=p)
    items += [
        Item(page=p, text="The threshold used in the assessment is fixed."),
        Item(page=p, text="The threshold is recorded for the next review."),
        # The word "quarterly" is only in the heading. The body is longer, so that with equal column
        # weights this unit ranks below the body match, and a heading weight above one lifts it.
        Item(
            page=p,
            text="Visits are logged each week by the team for the period under review, with notes.",
            heading="Quarterly review",
            index="Visits are logged each week by the team for the period under review, with notes.",
        ),
        Item(page=p, text="The assessment covers quarterly reports."),
    ]
    items += filler(20, page=p)
    items += [Item(page=p, text="Running header threshold assessment", content_type=ContentType.HEADER, body=False)]
    items += filler(5, page=p)
    return items


def large_document(document_id: str = DOC_LARGE) -> tuple[ExtractedDocument, DocumentStructure]:
    return build(document_id, ranking_items())


def assert_idf_is_informative(structure: DocumentStructure, terms: tuple[str, ...]) -> None:
    """Fail loudly when a query term occurs in half or more of the body units (the clamped-IDF case)."""
    body = [unit for unit in structure.units if unit.body_retrieval]
    for term in terms:
        occurrences = sum(term in (unit.index_text + " " + unit.heading_text).lower() for unit in body)
        if 2 * occurrences >= len(body):
            raise AssertionError(f"{term!r} occurs in {occurrences} of {len(body)} body units; the IDF is clamped")


__all__ = [
    "DOC_LARGE",
    "DOC_LARGE_TWIN",
    "Item",
    "SectionSpec",
    "assert_idf_is_informative",
    "build",
    "filler",
    "large_document",
    "ranking_items",
]

"""Registered fixture documents and the reader of the known-failure list (ARCHITECTURE §17.13; D86).

A known failure names its document in one of two ways: inline items, or the id of a fixture registered here. Every
fixture is labelled synthetic (tests/fixtures/verification_docs.py). No entry here is a result about the owner's document.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.common.files import read_text
from app.decision import DecisionStatus, answer, load_policy
from app.document_structure.models import ContentType
from tests.fixtures.retrieval_docs import Item
from tests.fixtures.verification_docs import clean_items, main_items, stored_document

CASE_DOCUMENT_ID = "doc-" + "f" * 16
FIXTURES: dict[str, Callable[[], list[Item]]] = {
    "loans-main": main_items,
    "loans-clean": clean_items,
}
ITEM_KEYS = frozenset({"page", "text", "content_type"})


def items_from(document: dict[str, Any]) -> list[Item]:
    """The items of an inline document. Raises ``ValueError`` for an item that does not fit."""
    raw = document["items"]
    if not raw:
        raise ValueError("an inline document needs at least one item")
    items = []
    for entry in raw:
        if not isinstance(entry, dict) or not {"page", "text"} <= set(entry) or set(entry) - ITEM_KEYS:
            raise ValueError("each item needs 'page' and 'text', and may have 'content_type' only")
        page = entry["page"]
        if not isinstance(page, int) or isinstance(page, bool) or page < 1:
            raise ValueError("an item's page is a whole number from 1")
        if not str(entry["text"]).strip():
            raise ValueError("an item's text may not be blank")
        items.append(
            Item(
                page=page,
                text=str(entry["text"]),
                content_type=ContentType(entry.get("content_type", ContentType.PARAGRAPH.value)),
            )
        )
    return items


class KnownFailure(BaseModel):
    """One open failure. ``document`` is ``{"items": [...]}`` or ``{"fixture": "<registered id>"}``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,62}$")
    phase: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    question: str = Field(min_length=1)
    expected_status: DecisionStatus
    document: dict[str, Any]
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def _document_resolves(self) -> Self:
        keys = set(self.document)
        if keys == {"fixture"}:
            if self.document["fixture"] not in FIXTURES:
                raise ValueError(f"unknown fixture id {self.document['fixture']!r}")
        elif keys == {"items"}:
            items_from(self.document)
        else:
            raise ValueError("document must be {'items': [...]} or {'fixture': <registered id>}")
        return self


def load_known_failures(path: Path | str) -> tuple[KnownFailure, ...]:
    """Read the known-failure file. Each line is one entry. Blank lines, bad entries and repeated ids are refused."""
    target = Path(path)
    cases: list[KnownFailure] = []
    seen: set[str] = set()
    for number, line in enumerate(read_text(target).splitlines(), start=1):
        if not line.strip():
            raise ValueError(f"{target.name}: line {number} is blank")
        try:
            case = KnownFailure.model_validate(json.loads(line))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(f"{target.name}: line {number}: {exc}") from exc
        if case.id in seen:
            raise ValueError(f"{target.name}: line {number} repeats the id {case.id!r}")
        seen.add(case.id)
        cases.append(case)
    return tuple(cases)


def observed_status(case: KnownFailure) -> str:
    """The status the engine gives for the entry's question on its document."""
    items = FIXTURES[case.document["fixture"]]() if "fixture" in case.document else items_from(case.document)
    store = stored_document(CASE_DOCUMENT_ID, items)
    try:
        return answer(store, CASE_DOCUMENT_ID, case.question, load_policy()).status.value
    finally:
        store.close()


def fixed_entries(cases: Sequence[KnownFailure]) -> list[str]:
    """The ids of open entries whose expected status the engine now gives. Each one must leave the list."""
    return [case.id for case in cases if observed_status(case) == case.expected_status.value]

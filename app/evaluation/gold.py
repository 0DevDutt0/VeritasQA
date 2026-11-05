"""Gold records and their validation (ARCHITECTURE §17.2 to §17.5; D75, D76, D77, D84).

Layer 1, :class:`GoldRecord`, checks the shape and the internal consistency of one record without any document.
Layer 2, :func:`check_against_store`, checks the record against the stored document: the page exists, the quotation
occurs verbatim on it, and the component indexes fit the question. Only layer 2 can refuse an inexact quotation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.common.files import read_text
from app.decision.response import DecisionStatus
from app.evaluation.errors import EvaluationError, GoldError
from app.evaluation.text import contains, normalize
from app.question_processing.analysis import analyze
from app.question_processing.errors import QuestionError
from app.storage import Store

RECORD_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{0,62}$"
ANSWERABLE_STATUSES = frozenset({DecisionStatus.ANSWERED, DecisionStatus.PARTIAL})


class Category(StrEnum):
    """The question categories of SPEC §11."""

    DIRECT_FACT = "direct_fact"
    NUMERIC_DATE = "numeric_date"
    TABLE = "table"
    PARAPHRASE = "paraphrase"
    NEGATION_EXCEPTION = "negation_exception"
    MULTI_PASSAGE = "multi_passage"
    COMPOUND = "compound"
    UNANSWERABLE = "unanswerable"
    AMBIGUOUS = "ambiguous"
    CONFLICTING = "conflicting"
    OCR_EXTRACTION_EDGE = "ocr_extraction_edge"


class Source(StrEnum):
    """Where the gold text comes from. Synthetic and public stand-in results are never reported as results about the
    owner's document (ARCHITECTURE §17.15, D101)."""

    SYNTHETIC = "synthetic"
    OWNER_DOCUMENT = "owner_document"
    PUBLIC_DOCUMENT = "public_document"


class Split(StrEnum):
    """Development records are used for tuning. Held-out records are used once, for the final run (SPEC §11)."""

    DEV = "dev"
    HELDOUT = "heldout"


def _not_blank(value: str) -> str:
    if not normalize(value):
        raise ValueError("the text may not be blank")
    return value


class GoldEvidence(BaseModel):
    """One passage that supports the answer. ``quote`` must be verbatim on ``pdf_page`` (layer 2)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    component: int = Field(ge=1)
    pdf_page: int = Field(ge=1)
    quote: str

    @field_validator("quote")
    @classmethod
    def _quote_not_blank(cls, value: str) -> str:
        return _not_blank(value)


class GoldAnswer(BaseModel):
    """The exact text of an answer span. It must occur in the evidence quote of the same component."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    component: int = Field(ge=1)
    text: str

    @field_validator("text")
    @classmethod
    def _text_not_blank(cls, value: str) -> str:
        return _not_blank(value)


class GoldRecord(BaseModel):
    """One gold question with its expected outcome (ARCHITECTURE §17.2)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str = Field(pattern=RECORD_ID_PATTERN)
    question: str
    category: Category
    source: Source
    split: Split
    annotator: str
    expected_status: DecisionStatus
    evidence: tuple[GoldEvidence, ...] = ()
    answers: tuple[GoldAnswer, ...] = ()

    @field_validator("question", "annotator")
    @classmethod
    def _text_not_blank(cls, value: str) -> str:
        return _not_blank(value)

    @property
    def answerable(self) -> bool:
        """True when the expected status is ANSWERED or PARTIAL."""
        return self.expected_status in ANSWERABLE_STATUSES

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.answerable and not self.evidence:
            raise ValueError("an answerable record needs gold evidence")
        if not self.answerable and self.answers:
            raise ValueError("an unanswerable record may not give answer spans")
        for answer in self.answers:
            supported = any(
                evidence.component == answer.component and contains(evidence.quote, answer.text)
                for evidence in self.evidence
            )
            if not supported:
                raise ValueError(
                    f"the answer {answer.text!r} is not inside the evidence of component {answer.component}"
                )
        return self


@dataclass(frozen=True)
class GoldDataset:
    """The parsed records of one file, with the SHA-256 of the file's bytes (ARCHITECTURE §17.5)."""

    file_name: str
    sha256: str
    records: tuple[GoldRecord, ...]


def _describe(error: ValidationError) -> str:
    return "; ".join(f"{'.'.join(str(part) for part in item['loc']) or 'record'}: {item['msg']}" for item in error.errors())


def load_gold(path: Path | str) -> GoldDataset:
    """Read a gold JSONL file. Each line is one record. Blank lines, invalid JSON and duplicate ids are refused."""
    target = Path(path)
    sha256 = hashlib.sha256(target.read_bytes()).hexdigest()
    text = read_text(target)
    if not text.strip():
        raise GoldError(f"{target.name} holds no records")
    records: list[GoldRecord] = []
    seen: set[str] = set()
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            raise GoldError(f"{target.name}: line {number} is blank")
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise GoldError(f"{target.name}: line {number} is not valid JSON ({exc.msg})") from exc
        try:
            record = GoldRecord.model_validate(payload)
        except ValidationError as exc:
            raise GoldError(f"{target.name}: line {number}: {_describe(exc)}") from exc
        if record.record_id in seen:
            raise GoldError(f"{target.name}: line {number} repeats the record id {record.record_id!r}")
        seen.add(record.record_id)
        records.append(record)
    return GoldDataset(file_name=target.name, sha256=sha256, records=tuple(records))


def select_split(dataset: GoldDataset, split: str | Split, *, final_run: bool) -> tuple[GoldRecord, ...]:
    """The records of one split, checked before any answer is computed (ARCHITECTURE §17.5, D84).

    Held-out records need ``final_run=True``, and development records refuse it. Only one split and one source
    can be selected, so a run never mixes them.
    """
    try:
        wanted = Split(split)
    except ValueError:
        raise EvaluationError(f"unknown split {split!r}; use 'dev' or 'heldout'") from None
    if wanted is Split.HELDOUT and not final_run:
        raise EvaluationError("held-out records need final_run=True, which is the one final run")
    if wanted is Split.DEV and final_run:
        raise EvaluationError("final_run=True applies only to held-out records")
    chosen = tuple(record for record in dataset.records if record.split is wanted)
    if not chosen:
        raise EvaluationError(f"{dataset.file_name} has no {wanted.value} records")
    if len({record.source for record in chosen}) > 1:
        raise EvaluationError("one run may not mix synthetic and owner-document records")
    return chosen


def check_against_store(record: GoldRecord, store: Store, document_id: str) -> None:
    """Layer 2: check one record against the stored document (ARCHITECTURE §17.4). Raises :class:`GoldError`."""
    try:
        component_count = len(analyze(record.question).components)
    except QuestionError as exc:
        raise GoldError(f"{record.record_id}: the question is not usable: {exc}") from exc
    for evidence in record.evidence:
        if evidence.component > component_count:
            raise GoldError(
                f"{record.record_id}: evidence names component {evidence.component}, "
                f"but the question has {component_count}"
            )
    pages = store.page_texts(document_id, sorted({evidence.pdf_page for evidence in record.evidence}))
    for evidence in record.evidence:
        page_text = pages.get(evidence.pdf_page)
        if page_text is None:
            raise GoldError(f"{record.record_id}: page {evidence.pdf_page} is not in the stored document")
        if not contains(page_text, evidence.quote):
            raise GoldError(
                f"{record.record_id}: the quote {evidence.quote!r} is not verbatim on page {evidence.pdf_page}"
            )
    covered = {evidence.component for evidence in record.evidence}
    every = set(range(1, component_count + 1))
    if record.expected_status is DecisionStatus.ANSWERED and not every <= covered:
        raise GoldError(
            f"{record.record_id}: ANSWERED needs evidence for every component; "
            f"missing {sorted(every - covered)}"
        )
    if record.expected_status is DecisionStatus.PARTIAL and (not covered & every or every <= covered):
        raise GoldError(
            f"{record.record_id}: PARTIAL needs one component with evidence and one without"
        )

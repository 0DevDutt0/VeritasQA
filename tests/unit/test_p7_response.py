"""The response model (SPEC §10; ARCHITECTURE §16.7): every invariant is refused when it is broken."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.decision.response import (
    AnswerSpan,
    ComponentOutcome,
    EvidenceItem,
    PolicySummary,
    QAResponse,
)

QUOTE = "The limit for loans is 30 days after approval."
EVIDENCE_ID = "doc-" + "a" * 16 + ":p0001:u0001"
PAGE_START = 100


def _item(**changes) -> EvidenceItem:
    values = {
        "evidence_id": EVIDENCE_ID,
        "pdf_page": 1,
        "printed_page": None,
        "section": "Loans",
        "quote": QUOTE,
        "source_start": PAGE_START,
        "source_end": PAGE_START + len(QUOTE),
        "quality_status": "verified",
        "extraction_method": "native_text",
        "roles": ("answer",),
        "component_ids": ("c1",),
    }
    values.update(changes)
    return EvidenceItem(**values)


def _span(text: str = "30 days", **changes) -> AnswerSpan:
    offset = QUOTE.index("30 days") if text == "30 days" else QUOTE.index(text)
    values = {
        "text": text,
        "evidence_id": EVIDENCE_ID,
        "component_id": "c1",
        "pdf_page": 1,
        "start": PAGE_START + offset,
        "end": PAGE_START + offset + len(text),
    }
    values.update(changes)
    return AnswerSpan(**values)


def _component(status: str = "ANSWERED", **changes) -> ComponentOutcome:
    values = {
        "component_id": "c1",
        "text": "How many days is the limit for loans?",
        "question_type": "how_many",
        "status": status,
        "reason_codes": ("answer_verified",) if status == "ANSWERED" else ("no_candidates",),
        "reasons": ("synthetic",),
        "evidence_ids": (EVIDENCE_ID,),
    }
    values.update(changes)
    return ComponentOutcome(**values)


def _response(**changes) -> QAResponse:
    values = {
        "status": "ANSWERED",
        "question": "How many days is the limit for loans?",
        "answer_spans": (_span(),),
        "evidence": (_item(),),
        "warnings": (),
        "reason_codes": ("answer_verified",),
        "components": (_component(),),
        "retrieval": (),
        "verification": (),
        "conflicts": (),
        "screening": (),
        "policy": PolicySummary(version="policy.v1", calibrated=False, sha256="0" * 64, gates={"require_value_validation": True}),
    }
    values.update(changes)
    return QAResponse(**values)


def test_a_consistent_answered_response_is_accepted_and_round_trips():
    response = _response()
    assert response.engine_version == "decision.v1"
    again = QAResponse.model_validate(response.model_dump(mode="json"))
    assert again == response


def test_answered_needs_a_span():
    with pytest.raises(ValidationError, match="ANSWERED needs at least one answer span"):
        _response(answer_spans=())


def test_a_span_is_refused_for_a_status_that_does_not_allow_an_answer():
    with pytest.raises(ValidationError, match="must not carry an answer span"):
        _response(status="INSUFFICIENT_EVIDENCE", components=(_component("INSUFFICIENT_EVIDENCE"),))


def test_the_status_must_be_the_aggregate_of_the_components():
    with pytest.raises(ValidationError, match="not the aggregate"):
        _response(status="PARTIAL", components=(_component("INSUFFICIENT_EVIDENCE"),))


def test_partial_needs_a_mix_of_answered_and_unanswered_components():
    both_answered = (_component(component_id="c1"), _component(component_id="c2", evidence_ids=(EVIDENCE_ID,)))
    with pytest.raises(ValidationError, match="not the aggregate"):
        _response(status="PARTIAL", components=both_answered)


def test_partial_with_a_mix_is_accepted():
    mixed = (
        _component(component_id="c1"),
        _component("INSUFFICIENT_EVIDENCE", component_id="c2"),
    )
    response = _response(status="PARTIAL", components=mixed)
    assert response.status == "PARTIAL"


def test_a_span_must_match_its_quote_at_its_offsets():
    wrong = _span(start=PAGE_START + QUOTE.index("30 days") + 1, end=PAGE_START + QUOTE.index("30 days") + 8)
    with pytest.raises(ValidationError, match="not a verbatim slice"):
        _response(answer_spans=(wrong,))


def test_a_span_outside_its_quote_is_refused():
    outside = AnswerSpan(
        text="30 days",
        evidence_id=EVIDENCE_ID,
        component_id="c1",
        pdf_page=1,
        start=PAGE_START + len(QUOTE),
        end=PAGE_START + len(QUOTE) + 7,
    )
    with pytest.raises(ValidationError, match="not a verbatim slice"):
        _response(answer_spans=(outside,))


def test_a_span_that_starts_before_its_quote_is_refused_even_when_its_text_matches_the_quote_end():
    # A negative offset would index the quote from its end, so the text can match by coincidence. The span must be refused
    # because it starts before the quote, not because its text happens to differ.
    early = AnswerSpan(
        text=QUOTE[-5:-2],
        evidence_id=EVIDENCE_ID,
        component_id="c1",
        pdf_page=1,
        start=PAGE_START - 5,
        end=PAGE_START - 2,
    )
    with pytest.raises(ValidationError, match="not a verbatim slice"):
        _response(answer_spans=(early,))


def test_a_span_must_name_an_evidence_item_that_is_quoted():
    unquoted = _item(quote=None, source_start=None, source_end=None)
    with pytest.raises(ValidationError, match="not a verbatim slice"):
        _response(evidence=(unquoted,))


def test_a_span_must_end_after_it_starts():
    with pytest.raises(ValidationError, match="must end after it starts"):
        _span(start=PAGE_START + 5, end=PAGE_START + 5)


def test_the_offsets_of_a_quote_must_match_its_length():
    with pytest.raises(ValidationError, match="do not match the length"):
        _item(source_end=PAGE_START + len(QUOTE) + 1)


def test_a_quote_needs_offsets_and_an_unquotable_passage_has_none():
    with pytest.raises(ValidationError, match="needs its source offsets"):
        _item(source_start=None)
    with pytest.raises(ValidationError, match="no source offsets"):
        _item(quote=None)


def test_a_component_may_only_name_evidence_the_response_carries():
    with pytest.raises(ValidationError, match="names evidence not in the response"):
        _response(components=(_component(evidence_ids=(EVIDENCE_ID, "doc-" + "a" * 16 + ":p0009:u0001")),))


def test_unknown_fields_and_unknown_statuses_are_refused():
    with pytest.raises(ValidationError):
        _response(confidence=0.9)
    with pytest.raises(ValidationError):
        _response(status="MAYBE")
    with pytest.raises(ValidationError):
        _response(reason_codes=("trust_me",))


def test_the_response_is_frozen():
    response = _response()
    with pytest.raises(ValidationError):
        response.status = "CONFLICT"  # type: ignore[misc]

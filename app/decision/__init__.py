"""The decision step: one validated answer per question (SPEC §9, §10; ARCHITECTURE §16)."""

from app.decision.engine import answer
from app.decision.errors import DecisionError, PolicyError
from app.decision.policy import AcceptancePolicy, accepts, load_policy
from app.decision.response import (
    ENGINE_VERSION,
    AnswerSpan,
    DecisionStatus,
    EvidenceItem,
    QAResponse,
    ReasonCode,
    aggregate_status,
)

__all__ = [
    "ENGINE_VERSION",
    "AcceptancePolicy",
    "AnswerSpan",
    "DecisionError",
    "DecisionStatus",
    "EvidenceItem",
    "PolicyError",
    "QAResponse",
    "ReasonCode",
    "accepts",
    "aggregate_status",
    "answer",
    "load_policy",
]

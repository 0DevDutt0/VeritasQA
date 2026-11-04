"""Evidence selection: candidate passages and their values, markers and sentences (SPEC §6; ARCHITECTURE §14)."""

from app.evidence.errors import SelectionError
from app.evidence.markers import Marker, find_markers
from app.evidence.segment import sentence_spans
from app.evidence.selection import (
    AnswerCandidate,
    ComponentSelection,
    ComponentStatus,
    DroppedCandidate,
    SelectionResult,
    select_candidates,
)
from app.evidence.values import Value, ValueKind, find_values

__all__ = [
    "AnswerCandidate",
    "ComponentSelection",
    "ComponentStatus",
    "DroppedCandidate",
    "Marker",
    "SelectionError",
    "SelectionResult",
    "Value",
    "ValueKind",
    "find_markers",
    "find_values",
    "select_candidates",
    "sentence_spans",
]

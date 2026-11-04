"""The verification report: one verdict per candidate, with every check and its reason (ARCHITECTURE §15, D61).

The verdict is candidate-level. It is not a final answer: conflict screening (check ``conflict``) is pending in the
decision step (D66), and the decision step applies the acceptance policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.question_processing.analysis import QuestionType


class CheckStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNRESOLVED = "UNRESOLVED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PENDING = "PENDING"  # decided by a later step, not by this verdict (D66)


class Verdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNRESOLVED = "UNRESOLVED"


class CheckName(StrEnum):
    """The SPEC §7 checks, in order, and the P5 flag check (``candidate_flags``)."""

    QUOTATION = "quotation"
    LOCATION = "location"
    ANSWER_SPAN = "answer_span"
    ENTITY = "entity"
    ATTRIBUTE = "attribute"
    VALUE = "value"
    CONTEXT = "context"
    NEGATION = "negation"
    CONDITION = "condition"
    CONFLICT = "conflict"
    SOURCE_QUALITY = "source_quality"
    CANDIDATE_FLAGS = "candidate_flags"


@dataclass(frozen=True)
class CheckResult:
    name: CheckName
    rule_id: str
    status: CheckStatus
    reason: str


@dataclass(frozen=True)
class VerificationReport:
    verifier_version: str
    document_id: str
    evidence_id: str
    component_id: str
    question_type: QuestionType
    verdict: Verdict
    checks: tuple[CheckResult, ...]
    pending: tuple[CheckName, ...]
    reasons: tuple[str, ...]

    def check(self, name: CheckName) -> CheckResult:
        """The result of one check. Every report holds every check, so a missing name is a programming error."""
        for result in self.checks:
            if result.name == name:
                return result
        raise KeyError(name)

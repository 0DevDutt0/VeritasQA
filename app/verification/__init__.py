"""Evidence verification (SPEC §7; ARCHITECTURE §15).

``verify`` gives one verdict per P5 candidate, with every check and its reason. The verdict is candidate-level: the
decision step (P7) still runs conflict screening and applies the acceptance policy.
"""

from app.verification.errors import VerificationError
from app.verification.report import CheckName, CheckResult, CheckStatus, Verdict, VerificationReport
from app.verification.verifier import ORDER, REQUIRED, REQUIRED_BY_TYPE, verify
from app.verification.vocabulary import VERIFIER_VERSION

__all__ = [
    "ORDER",
    "REQUIRED",
    "REQUIRED_BY_TYPE",
    "VERIFIER_VERSION",
    "CheckName",
    "CheckResult",
    "CheckStatus",
    "Verdict",
    "VerificationError",
    "VerificationReport",
    "verify",
]

"""The acceptance policy: which unresolved verifier checks may be accepted (ARCHITECTURE §16.1, D69).

The policy file (``config/acceptance_policy.toml``) holds one switch for each check that the verifier can leave
UNRESOLVED. A switch set to false lets that UNRESOLVED outcome through. It never lets a FAIL through, and the checks
that are not in the file always block. The default policy has every switch on, so :func:`accepts` is exactly the
verifier's PASS rule.
"""

from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.decision.errors import PolicyError
from app.verification.report import CheckName, CheckStatus, VerificationReport
from app.verification.verifier import NOT_APPLICABLE_ALLOWED, REQUIRED

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY_PATH = REPO_ROOT / "config" / "acceptance_policy.toml"
_SECTIONS = frozenset({"version", "calibrated", "gates"})

# The only checks a policy may relax, and the switch that relaxes each one (ARCHITECTURE §16.1).
GATE_OF_CHECK: dict[CheckName, str] = {
    CheckName.ATTRIBUTE: "require_attribute_validation",
    CheckName.VALUE: "require_value_validation",
    CheckName.ENTITY: "require_entity_validation",
    CheckName.CONTEXT: "require_context_validation",
    CheckName.NEGATION: "require_negation_validation",
    CheckName.CONDITION: "require_condition_validation",
}
GATES: tuple[str, ...] = tuple(GATE_OF_CHECK.values())


class AcceptancePolicy(BaseModel):
    """The validated policy. ``sha256`` identifies the exact file that was used, and every response records it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str = Field(min_length=1)
    calibrated: bool
    gates: dict[str, bool]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _gates_complete_and_uncalibrated(self) -> AcceptancePolicy:
        if set(self.gates) != set(GATES):
            missing = sorted(set(GATES) - set(self.gates))
            unknown = sorted(set(self.gates) - set(GATES))
            raise ValueError(f"the gates must be exactly {sorted(GATES)} (missing {missing}, unknown {unknown})")
        if self.calibrated:
            raise ValueError("calibrated must be false: no policy can be calibrated before measured data exists (B3)")
        return self

    def gate_on(self, gate: str) -> bool:
        return self.gates[gate]


def load_policy(path: Path | str | None = None) -> AcceptancePolicy:
    """Read and validate the acceptance policy. Raises :class:`PolicyError`."""
    target = Path(path) if path is not None else DEFAULT_POLICY_PATH
    try:
        raw = target.read_bytes()
    except FileNotFoundError as exc:
        raise PolicyError(f"policy file not found: {target.name}") from exc
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise PolicyError(f"policy file is not valid UTF-8 TOML: {target.name}: {exc}") from exc
    unexpected = set(data) - _SECTIONS
    if unexpected:
        raise PolicyError(f"{target.name} has unknown keys: {sorted(unexpected)}")
    gates = data.get("gates")
    if not isinstance(gates, dict):
        raise PolicyError(f"{target.name} needs a [gates] section")
    try:
        return AcceptancePolicy.model_validate(
            {
                "version": data.get("version"),
                "calibrated": data.get("calibrated"),
                "gates": gates,
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    except ValidationError as exc:
        raise PolicyError(f"invalid policy in {target.name}: {exc}") from exc


def accepts(report: VerificationReport, policy: AcceptancePolicy) -> bool:
    """True when the candidate may support an answer under ``policy`` (ARCHITECTURE §16.1).

    Every required check must be PASS, or NOT_APPLICABLE on ``attribute`` or ``value``, or UNRESOLVED on a check whose
    switch is off. A FAIL is never accepted. The conflict check is pending in the verifier and is not part of this rule.
    """
    for name in REQUIRED:
        status = report.check(name).status
        if status == CheckStatus.PASS:
            continue
        if status == CheckStatus.NOT_APPLICABLE and name in NOT_APPLICABLE_ALLOWED:
            continue
        if status == CheckStatus.UNRESOLVED and name in GATE_OF_CHECK and not policy.gate_on(GATE_OF_CHECK[name]):
            continue
        return False
    return True


def relaxed_checks(report: VerificationReport, policy: AcceptancePolicy) -> tuple[CheckName, ...]:
    """The UNRESOLVED checks that ``policy`` lets through for this candidate. Empty for the default policy."""
    return tuple(
        name
        for name in REQUIRED
        if report.check(name).status == CheckStatus.UNRESOLVED
        and name in GATE_OF_CHECK
        and not policy.gate_on(GATE_OF_CHECK[name])
    )

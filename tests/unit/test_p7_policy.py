"""The acceptance policy (ARCHITECTURE §16.1, D69): the file, the switches, and what each switch may and may not change."""

from __future__ import annotations

import hashlib

import pytest

from app.decision.errors import PolicyError
from app.decision.policy import GATE_OF_CHECK, GATES, AcceptancePolicy, accepts, load_policy, relaxed_checks
from app.question_processing.analysis import QuestionType
from app.verification.report import CheckName, CheckResult, CheckStatus, Verdict, VerificationReport
from app.verification.verifier import NOT_APPLICABLE_ALLOWED, ORDER, REQUIRED

HARD = (
    CheckName.QUOTATION,
    CheckName.LOCATION,
    CheckName.ANSWER_SPAN,
    CheckName.SOURCE_QUALITY,
    CheckName.CANDIDATE_FLAGS,
)
RELAXABLE = tuple(GATE_OF_CHECK)
BASE = """
version = "policy.test"
calibrated = false

[gates]
require_attribute_validation = true
require_value_validation = true
require_entity_validation = true
require_context_validation = true
require_negation_validation = true
require_condition_validation = true
"""


def policy_with(gates: dict[str, bool]) -> AcceptancePolicy:
    full = {gate: True for gate in GATES} | gates
    return AcceptancePolicy(version="policy.test", calibrated=False, gates=full, sha256="0" * 64)


def make_report(overrides: dict[CheckName, CheckStatus] | None = None) -> VerificationReport:
    overrides = overrides or {}
    checks = []
    for name in ORDER:
        status = CheckStatus.PENDING if name == CheckName.CONFLICT else overrides.get(name, CheckStatus.PASS)
        checks.append(CheckResult(name=name, rule_id=f"verify.{name.value}.v1", status=status, reason="synthetic"))
    return VerificationReport(
        verifier_version="verify.v1",
        document_id="doc-test",
        evidence_id="doc-test:p0001:u0001",
        component_id="c1",
        question_type=QuestionType.HOW_MANY,
        verdict=Verdict.PASS if not overrides else Verdict.UNRESOLVED,
        checks=tuple(checks),
        pending=(CheckName.CONFLICT,),
        reasons=(),
    )


def write(tmp_path, text: str):
    path = tmp_path / "policy.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_default_policy_is_conservative_uncalibrated_and_identified():
    policy = load_policy()
    assert policy.calibrated is False
    assert policy.version == "policy.v1"
    assert set(policy.gates) == set(GATES)
    assert all(policy.gates.values())
    assert len(policy.sha256) == 64


def test_with_every_switch_on_a_candidate_is_accepted_only_when_every_check_passes():
    policy = load_policy()
    assert accepts(make_report(), policy) is True
    assert accepts(make_report({CheckName.ATTRIBUTE: CheckStatus.NOT_APPLICABLE, CheckName.VALUE: CheckStatus.NOT_APPLICABLE}), policy) is True
    for name in ORDER:
        if name in (CheckName.CONFLICT,):
            continue
        assert accepts(make_report({name: CheckStatus.UNRESOLVED}), policy) is False, name


@pytest.mark.parametrize("name", RELAXABLE)
def test_each_switch_changes_exactly_its_own_unresolved_case(name):
    gate = GATE_OF_CHECK[name]
    report = make_report({name: CheckStatus.UNRESOLVED})
    assert accepts(report, load_policy()) is False
    assert accepts(report, policy_with({gate: False})) is True
    assert relaxed_checks(report, policy_with({gate: False})) == (name,)
    other = next(other_gate for other_gate in GATES if other_gate != gate)
    assert accepts(report, policy_with({other: False})) is False


@pytest.mark.parametrize("name", RELAXABLE)
def test_a_switch_never_accepts_a_fail(name):
    gates = {gate: False for gate in GATES}
    assert accepts(make_report({name: CheckStatus.FAIL}), policy_with(gates)) is False


@pytest.mark.parametrize("name", HARD)
def test_the_hard_checks_block_even_when_every_switch_is_off(name):
    gates = {gate: False for gate in GATES}
    assert accepts(make_report({name: CheckStatus.UNRESOLVED}), policy_with(gates)) is False
    assert accepts(make_report({name: CheckStatus.FAIL}), policy_with(gates)) is False
    assert relaxed_checks(make_report({name: CheckStatus.UNRESOLVED}), policy_with(gates)) == ()


def test_a_relaxed_policy_still_requires_every_other_check():
    gates = {gate: False for gate in GATES}
    report = make_report({CheckName.CONTEXT: CheckStatus.UNRESOLVED, CheckName.NEGATION: CheckStatus.FAIL})
    assert accepts(report, policy_with(gates)) is False


@pytest.mark.parametrize("name", [name for name in REQUIRED if name not in NOT_APPLICABLE_ALLOWED])
def test_not_applicable_is_accepted_only_on_attribute_and_value(name):
    # A check that is NOT_APPLICABLE on a question without the item it checks is accepted only for attribute and value.
    # Any other check that is NOT_APPLICABLE must block, under the default policy and with every switch off.
    report = make_report({name: CheckStatus.NOT_APPLICABLE})
    assert accepts(report, load_policy()) is False
    assert accepts(report, policy_with({gate: False for gate in GATES})) is False


def test_the_policy_file_is_read_and_its_hash_names_the_exact_bytes(tmp_path):
    path = write(tmp_path, BASE)
    policy = load_policy(path)
    assert set(policy.gates) == set(GATES) and all(policy.gates.values())
    assert policy.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "text, message",
    [
        (BASE + "\n[extra]\nx = 1\n", "unknown keys"),
        (BASE.replace("require_value_validation = true\n", ""), "missing"),
        (BASE + "require_quotation = true\n", "unknown"),
        (BASE.replace("calibrated = false", "calibrated = true"), "calibrated must be false"),
        (BASE.replace("require_value_validation = true", "require_value_validation = 2"), "invalid policy"),
        ('version = "x"\ncalibrated = false\n', "needs a"),
        (BASE.replace('version = "policy.test"', 'version = ""'), "invalid policy"),
    ],
)
def test_a_bad_policy_file_is_refused(tmp_path, text, message):
    with pytest.raises(PolicyError, match=message):
        load_policy(write(tmp_path, text))


def test_a_missing_policy_file_is_refused(tmp_path):
    with pytest.raises(PolicyError, match="not found"):
        load_policy(tmp_path / "absent.toml")


def test_a_file_that_is_not_utf8_toml_is_refused(tmp_path):
    path = tmp_path / "policy.toml"
    path.write_bytes(b"\xff\xfe not toml")
    with pytest.raises(PolicyError, match="not valid UTF-8 TOML"):
        load_policy(path)

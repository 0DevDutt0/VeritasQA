"""Controlled synonym and stemming rules (ARCHITECTURE §13; D38, D43). Recall only.

A rule adds candidates for a query. It never counts as support: the owner decided this on 2026-11-04
(PROGRESS.md, D38). ``config/retrieval_rules.toml`` holds no approved rule in V1.

Matching is one-way and works on whole words, with the folding of the index, so a rule for ``fee``
does not match ``discharge``. Each rule is checked against its own examples when it loads.
"""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.common.errors import QueryError
from app.retrieval.errors import RuleConfigError
from app.retrieval.phrase import fold_case, span_matches
from app.retrieval.query import build_phrase_query

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RULES_PATH = REPO_ROOT / "config" / "retrieval_rules.toml"
RULES_FILE_VERSION = 1
_RULE_ID = re.compile(r"[a-z][a-z0-9-]{2,63}")


def normalized_term(text: str) -> str:
    """The index form of a rule term or example query: normalized, with single spaces.

    Raises ``ValueError`` when the text is not text or has no letter or digit.
    """
    try:
        return build_phrase_query(text).normalized
    except QueryError as exc:
        raise ValueError(str(exc)) from exc


def folded_words(normalized: str) -> tuple[str, ...]:
    """The folded words of a normalized text, in order."""
    return tuple(fold_case(word) for word in normalized.split(" ") if word)


def contains_run(words: Sequence[str], run: Sequence[str]) -> bool:
    """True when ``run`` occurs as a contiguous run of ``words``."""
    size = len(run)
    if size == 0:
        return False
    target = tuple(run)
    return any(tuple(words[start : start + size]) == target for start in range(len(words) - size + 1))


class RuleExample(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(min_length=1)
    text: str = Field(min_length=1)


class Rule(BaseModel):
    """One reviewed rule. The terms are stored in their normalized form."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    version: int = Field(ge=1)
    query_terms: tuple[str, ...] = Field(min_length=1)
    alternatives: tuple[str, ...] = Field(min_length=1)
    positive_examples: tuple[RuleExample, ...] = Field(min_length=1)
    counter_examples: tuple[RuleExample, ...] = Field(min_length=1)
    reviewer_note: str = Field(min_length=1)

    @field_validator("id")
    @classmethod
    def _id_format(cls, value: str) -> str:
        if _RULE_ID.fullmatch(value) is None:
            raise ValueError(
                f"rule id {value!r} must be 3 to 64 characters: a lowercase letter first, then lowercase letters, digits or hyphens"
            )
        return value

    @field_validator("query_terms", "alternatives")
    @classmethod
    def _normalize_terms(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(normalized_term(value) for value in values)
        keys = [folded_words(term) for term in normalized]
        if len(set(keys)) != len(keys):
            raise ValueError("a term is listed twice")
        return normalized

    @model_validator(mode="after")
    def _check_examples(self) -> Rule:
        term_runs = {folded_words(term) for term in self.query_terms}
        alternative_runs = {folded_words(alternative) for alternative in self.alternatives}
        if term_runs & alternative_runs:
            raise ValueError("an alternative repeats a query term")
        alternative_queries = [build_phrase_query(alternative) for alternative in self.alternatives]
        for label, examples in (("positive", self.positive_examples), ("counter", self.counter_examples)):
            for example in examples:
                query_words = folded_words(normalized_term(example.query))
                if not any(contains_run(query_words, run) for run in term_runs):
                    raise ValueError(f"the query {example.query!r} of a {label} example contains no query term")
                hits = any(span_matches(example.text, query) for query in alternative_queries)
                if label == "positive" and not hits:
                    raise ValueError(f"the text {example.text!r} of a positive example contains no alternative")
                if label == "counter" and hits:
                    raise ValueError(f"the text {example.text!r} of a counter-example contains an alternative")
        return self


class RuleSet(BaseModel):
    """The rules of one file, in file order."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rules: tuple[Rule, ...] = ()

    @model_validator(mode="after")
    def _unique_ids(self) -> RuleSet:
        identifiers = [rule.id for rule in self.rules]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("two rules share an id")
        return self

    @property
    def fingerprint(self) -> str:
        """SHA-256 of the canonical rule list. The trace records it, so a run can name the rules it used."""
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AppliedRule:
    """One alternative that a query term added to the query, for the retrieval trace."""

    query_term: str
    rule_id: str
    rule_version: int
    alternative: str


def expand_words(words: Sequence[str], rules: RuleSet) -> tuple[AppliedRule, ...]:
    """Every alternative that the query's folded words add, in rule-file order.

    ``words`` are the folded query words in query order. A rule's query term matches only as a
    contiguous run of whole words, and an alternative never matches as a query term (one-way).
    """
    applied: list[AppliedRule] = []
    seen: set[tuple[str, str, str]] = set()
    for rule in rules.rules:
        for term in rule.query_terms:
            if not contains_run(words, folded_words(term)):
                continue
            for alternative in rule.alternatives:
                key = (rule.id, term, alternative)
                if key in seen:
                    continue
                seen.add(key)
                applied.append(
                    AppliedRule(query_term=term, rule_id=rule.id, rule_version=rule.version, alternative=alternative)
                )
    return tuple(applied)


def load_rules(path: Path | str | None = None) -> RuleSet:
    """Read and validate a rules file. Defaults to ``config/retrieval_rules.toml``."""
    target = Path(path) if path is not None else DEFAULT_RULES_PATH
    try:
        with target.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise RuleConfigError(f"rules file not found: {target.name}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise RuleConfigError(f"rules file is not valid TOML: {target.name}: {exc}") from exc
    if data.get("rules_version") != RULES_FILE_VERSION:
        raise RuleConfigError(f"{target.name} must set rules_version = {RULES_FILE_VERSION}")
    entries = data.get("rule", [])
    if not isinstance(entries, list):
        raise RuleConfigError(f"{target.name}: [[rule]] must be a list of tables")
    rules: list[Rule] = []
    for number, entry in enumerate(entries, start=1):
        try:
            rules.append(Rule.model_validate(entry))
        except ValidationError as exc:
            raise RuleConfigError(f"rule {number} in {target.name} is invalid: {exc}") from exc
    try:
        return RuleSet(rules=tuple(rules))
    except ValidationError as exc:
        raise RuleConfigError(f"invalid rules in {target.name}: {exc}") from exc

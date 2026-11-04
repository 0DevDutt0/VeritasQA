"""Deterministic question analysis (SPEC §5; ARCHITECTURE §14; D52, D53).

``analyze`` splits a question into components, types each component with a named rule, and works out its
target terms, attribute terms, value intent, negation and condition words. Nothing is guessed. A component
that cannot be searched keeps a plain-text ``reason`` and is reported as unsupported or ambiguous, and it is
never silently dropped.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from app.question_processing.errors import QuestionError
from app.question_processing.vocabulary import (
    ATTRIBUTE_PLURALS,
    ATTRIBUTE_WORDS,
    COMPARISON_MARKERS,
    CONDITION_QUESTION_WORDS,
    FUNCTION_WORDS,
    NEGATION_WORDS,
    PRONOUNS,
    QUESTION_OPENERS,
    QUESTION_WORDS,
)


class QuestionType(StrEnum):
    WHAT = "what"
    WHO = "who"
    WHEN = "when"
    WHERE = "where"
    HOW_MANY = "how_many"
    WHICH = "which"
    WHETHER = "whether"
    CONDITIONS = "conditions"
    COMPARISON = "comparison"
    UNSUPPORTED = "unsupported"


class ValueIntent(StrEnum):
    NONE = "none"
    NUMBER = "number"
    DATE_OR_PERIOD = "date_or_period"


@dataclass(frozen=True)
class QuestionComponent:
    """One part of a question that is searched and answered on its own (D45).

    ``reason`` is set when the component cannot be searched (unsupported or ambiguous). ``flags`` records how
    the component was read, for example ``target_inherited``.
    """

    component_id: str
    text: str
    question_type: QuestionType
    type_rule: str
    target_terms: tuple[str, ...]
    attribute_terms: tuple[str, ...]
    value_intent: ValueIntent
    negated: bool
    condition_terms: tuple[str, ...]
    reason: str | None
    flags: tuple[str, ...]

    @property
    def retrieval_query(self) -> str:
        """The text to pass to ``search()``: target terms, then attribute terms, without duplicates (D54).

        A component that cannot be searched has an empty query, so no caller can search for it by accident.
        """
        if not self.searchable:
            return ""
        return " ".join(dict.fromkeys(self.target_terms + self.attribute_terms))

    @property
    def searchable(self) -> bool:
        return self.reason is None


@dataclass(frozen=True)
class QuestionAnalysis:
    """The analysed question. ``components`` is never empty and is in question order."""

    question: str
    components: tuple[QuestionComponent, ...]

    @property
    def compound(self) -> bool:
        return len(self.components) > 1


# Words of a token. A token keeps its inner dots, hyphens and apostrophes, so 3.5, ABC-123 and isn't stay whole.
_TOKEN = re.compile(r"[A-Za-z0-9]+(?:[-'’.][A-Za-z0-9]+)*")

# The separators at which a compound question may split (D52). A split is made only when the words after the
# separator open a question and the words before it already form one.
_SEPARATOR = re.compile(r"\s*[;,]?\s+(?:and|or)\s+|\s*;\s*")
_QUESTION_END = re.compile(r"\?\s*(?=\S)")

# Each rule is tested against the lower-cased component text, in this order. The first match sets the type.
_TYPE_RULES: tuple[tuple[re.Pattern[str], QuestionType, str], ...] = (
    (
        re.compile(r"^(?:under|in|for|at)\s+what\s+(?:conditions?|circumstances?|cases?|situations?)\b"),
        QuestionType.CONDITIONS,
        "type.conditions.v1",
    ),
    (
        re.compile(r"\bwhat\s+(?:conditions?|circumstances?|exceptions?|qualifications?|situations?)\b"),
        QuestionType.CONDITIONS,
        "type.conditions.v1",
    ),
    (
        re.compile(
            r"^how\s+(?:many|much|long|often|far|old|large|big|high|frequently)\b"
            r"|^what\s+(?:percentage|percent|proportion|share|fraction|amount|number|quantity|total|sum|rate)\b"
        ),
        QuestionType.HOW_MANY,
        "type.how_many.v1",
    ),
    (
        re.compile(
            r"^(?:when|by\s+when|until\s+when|from\s+when)\b"
            r"|^what\s+(?:is|are|was|were|will\s+be)\s+the\s+(?:date|deadline|period|year|month|day)s?\b"
        ),
        QuestionType.WHEN,
        "type.when.v1",
    ),
    (
        re.compile(r"^where\b|^what\s+(?:is|are)\s+the\s+(?:location|place|address|city|country)\b"),
        QuestionType.WHERE,
        "type.where.v1",
    ),
    (
        re.compile(r"^(?:who|whom|whose)\b|^what\s+(?:person|people|organi[sz]ation|team|company|role|entity)\b"),
        QuestionType.WHO,
        "type.who.v1",
    ),
    (
        re.compile(
            r"^(?:which|list|name)\b"
            r"|^what\s+(?:(?:is|are)\s+(?:the\s+)?)?(?:kinds?|types?|categories|forms?|examples?|items?|elements?|steps?"
            r"|requirements?|roles?"
            r"|parts?|components?|factors?|criteria|sections?|responsibilities)\b"
        ),
        QuestionType.WHICH,
        "type.which.v1",
    ),
    (re.compile(r"^whether\b"), QuestionType.WHETHER, "type.whether.v1"),
    (
        re.compile(r"^(?:is|are|was|were|does|do|did|can|could|may|might|must|shall|should|will|would|has|have|had)\b"),
        QuestionType.WHETHER,
        "type.whether.aux.v1",
    ),
    (re.compile(r"^what\b"), QuestionType.WHAT, "type.what.v1"),
)

# Subject patterns for a comparison (D52). Each one must name both subjects, or it does not match.
_COMPARISON_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bbetween\s+(?P<a>.+?)\s+and\s+(?P<b>.+)$", re.IGNORECASE),
    re.compile(
        r"^(?:(?:what|which)\s+(?:is|are)\s+(?:the\s+)?(?:difference|differences)\s+)?(?:(?:is|are|does|do)\s+)?"
        r"(?P<a>.+?)\s+(?:versus|vs\.?|compared\s+(?:to|with))\s+(?P<b>.+)$",
        re.IGNORECASE,
    ),
    re.compile(r"^(?:compare|comparison\s+of)\s+(?P<a>.+?)\s+(?:with|to|and|versus|vs\.?)\s+(?P<b>.+)$", re.IGNORECASE),
)

_COMPONENT_EDGE = " \t\r\n?.,;"


def _check_question(question: object) -> str:
    if not isinstance(question, str):
        raise QuestionError(f"a question must be text, not {type(question).__name__}")
    try:
        question.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise QuestionError(f"the question is not valid Unicode text ({exc.reason})") from exc
    if not question.strip():
        raise QuestionError("the question is blank")
    if any(unicodedata.category(character) == "Cc" and not character.isspace() for character in question):
        raise QuestionError("the question contains a control character")
    if not any(character.isalnum() for character in question):
        raise QuestionError("the question has no letter or digit to search for")
    return question


def _words(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN.findall(text)]


def _is_attribute(word: str) -> bool:
    if word in ATTRIBUTE_WORDS or word in ATTRIBUTE_PLURALS:
        return True
    if word.endswith("es") and word[:-2] in ATTRIBUTE_WORDS:
        return True
    return word.endswith("s") and word[:-1] in ATTRIBUTE_WORDS


def _is_negation(word: str) -> bool:
    return word in NEGATION_WORDS or word.endswith("n't")


def _unique(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _target_terms(words: list[str]) -> tuple[str, ...]:
    return _unique(
        [
            word
            for word in words
            if word not in FUNCTION_WORDS
            and word not in QUESTION_WORDS
            and word not in PRONOUNS
            and not _is_attribute(word)
            and not _is_negation(word)
        ]
    )


def _attribute_terms(words: list[str]) -> tuple[str, ...]:
    return _unique([word for word in words if _is_attribute(word)])


def _split_points(question: str) -> list[tuple[int, int]]:
    """The (start, end) slices of the question's components, before any comparison is expanded (D52)."""
    parts: list[tuple[int, int]] = []
    start = 0
    for end_match in _QUESTION_END.finditer(question):
        parts.append((start, end_match.start() + 1))
        start = end_match.end()
    parts.append((start, len(question)))

    slices: list[tuple[int, int]] = []
    for part_start, part_end in parts:
        current = part_start
        for separator in _SEPARATOR.finditer(question, part_start, part_end):
            following = re.match(r"\W*([A-Za-z]+)", question[separator.end() : part_end])
            leading = re.match(r"\W*([A-Za-z]+)", question[current:part_end])
            if not following or not leading:
                continue
            if following.group(1).lower() in QUESTION_OPENERS and leading.group(1).lower() in QUESTION_OPENERS:
                slices.append((current, separator.start()))
                current = separator.end()
        slices.append((current, part_end))
    return [(start, end) for start, end in slices if question[start:end].strip(_COMPONENT_EDGE)]


def _make(
    components: list[QuestionComponent],
    text: str,
    question_type: QuestionType,
    type_rule: str,
    targets: tuple[str, ...],
    attributes: tuple[str, ...],
    negated: bool,
    conditions: tuple[str, ...],
    reason: str | None,
    flags: tuple[str, ...],
) -> QuestionComponent:
    value_intent = {
        QuestionType.HOW_MANY: ValueIntent.NUMBER,
        QuestionType.WHEN: ValueIntent.DATE_OR_PERIOD,
    }.get(question_type, ValueIntent.NONE)
    return QuestionComponent(
        component_id=f"c{len(components) + 1}",
        text=text,
        question_type=question_type,
        type_rule=type_rule,
        target_terms=targets,
        attribute_terms=attributes,
        value_intent=value_intent,
        negated=negated,
        condition_terms=conditions,
        reason=reason,
        flags=flags,
    )


def _unsupported_reason(words: list[str]) -> str:
    if words and words[0] == "why":
        return "why questions are not supported"
    if words and words[0] == "how":
        return "how questions about a process are not supported"
    return "the question does not open with a supported question word"


def _comparison_components(
    components: list[QuestionComponent], text: str, words: list[str]
) -> list[QuestionComponent]:
    """One component per explicit subject (D52). Without explicit subjects the comparison is ambiguous."""
    attributes = _attribute_terms(words)
    negated = any(_is_negation(word) for word in words)
    conditions = _unique([word for word in words if word in CONDITION_QUESTION_WORDS])
    match = next((found for pattern in _COMPARISON_PATTERNS if (found := pattern.search(text))), None)
    if match is None:
        return [
            _make(
                components,
                text,
                QuestionType.COMPARISON,
                "type.comparison.v1",
                _target_terms(words),
                attributes,
                negated,
                conditions,
                "the subjects of this comparison are not explicit",
                ("subjects_unclear",),
            )
        ]
    made: list[QuestionComponent] = []
    for group in ("a", "b"):
        subject = match.group(group).strip(_COMPONENT_EDGE)
        subject_words = _words(subject)
        targets = _target_terms(subject_words)
        reason = None if targets else "a comparison subject names no subject to search for"
        flags = ("comparison_subject",) if targets else ("comparison_subject", "no_target_terms")
        made.append(
            _make(
                components + made,
                subject,
                QuestionType.COMPARISON,
                "type.comparison.v1",
                targets,
                attributes,
                negated,
                conditions,
                reason,
                flags,
            )
        )
    return made


def _component_for(components: list[QuestionComponent], raw: str) -> list[QuestionComponent]:
    text = raw.strip(_COMPONENT_EDGE)
    words = _words(text)
    if any(word in COMPARISON_MARKERS for word in words):
        return _comparison_components(components, text, words)

    lowered = text.lower()
    matched = next(((rule, kind, name) for rule, kind, name in _TYPE_RULES if rule.search(lowered)), None)
    attributes = _attribute_terms(words)
    negated = any(_is_negation(word) for word in words)
    conditions = _unique([word for word in words if word in CONDITION_QUESTION_WORDS])
    if matched is None:
        return [
            _make(
                components,
                text,
                QuestionType.UNSUPPORTED,
                "type.unsupported.v1",
                (),
                attributes,
                negated,
                conditions,
                _unsupported_reason(words),
                (),
            )
        ]

    _, question_type, rule_name = matched
    targets = _target_terms(words)
    flags: tuple[str, ...] = ()
    reason: str | None = None
    referential = bool(components) and any(word in PRONOUNS for word in words)
    if referential:
        # A later clause that uses a pronoun takes the subject of the clause before it (D52). Its own words are
        # predicates, such as `due` in `when is it due`, so they do not replace that subject.
        earlier = components[-1].target_terms
        if earlier:
            targets = earlier
            flags = ("target_inherited",)
        else:
            reason = "a pronoun refers to an earlier subject, but no earlier subject was named"
            flags = ("pronoun_without_subject",)
    elif not targets:
        reason = "the question names no subject to search for"
        flags = ("no_target_terms",)
    return [
        _make(components, text, question_type, rule_name, targets, attributes, negated, conditions, reason, flags)
    ]


def analyze(question: str) -> QuestionAnalysis:
    """Analyse one question into components. Raises :class:`QuestionError` when it is not usable text."""
    checked = _check_question(question)
    components: list[QuestionComponent] = []
    for start, end in _split_points(checked):
        components.extend(_component_for(components, checked[start:end]))
    return QuestionAnalysis(question=checked, components=tuple(components))

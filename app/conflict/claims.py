"""Claims: the comparable values that one piece of text states (ARCHITECTURE §16.2, D70).

A claim is one value of a kind that a question asks about: a date or period (``when``), a quantity with its unit or a
bare number (``how_many``), or the polarity of a permission marker (``whether``). ``compare`` returns True when two
claims are equal, False when they differ, and None when the screen cannot compare them. A None is recorded as no
relation, so it is never a conclusion that the values agree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.common.text import normalize_text
from app.conflict.config import ConflictConfig, family_of, normalize_unit
from app.evidence.markers import Marker
from app.evidence.values import Value, ValueKind
from app.question_processing.analysis import QuestionType

KIND_DATE = "date"
KIND_QUANTITY = "quantity"
KIND_BARE = "bare"
KIND_POLARITY = "polarity"

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


@dataclass(frozen=True)
class Claim:
    """One value stated by a piece of text.

    ``family`` is the measure family of a quantity (``None`` when its unit is not in the configuration, which
    makes it comparable with every quantity), the kind of a date (``date`` or ``period``), or ``polarity``.
    ``number`` is set only for a quantity without a range and for a bare number; it is ``None`` otherwise.
    ``text`` is the value as written, for the reasons.
    """

    kind: str
    family: str | None
    value: str
    unit: str
    number: str | None
    text: str


def normalize_number(text: str, negative: bool = False) -> str | None:
    """The first number of ``text`` in plain decimal form (``1,000.50`` -> ``1000.5``), or None when there is none."""
    match = _NUMBER.search(text.replace(",", ""))
    if match is None:
        return None
    try:
        rendered = format(Decimal(match.group(0)).normalize(), "f")
    except InvalidOperation:
        return None
    if negative and rendered != "0":
        return "-" + rendered
    return rendered


def normalize_date(text: str) -> str:
    """A date or period in lookup form: NFKC, case folded, whitespace collapsed, and the closing punctuation removed."""
    return " ".join(normalize_text(text).casefold().strip(" .,;").split())


_WORDS = re.compile(r"[^\W\d_]+")


def _quantity(value: Value, config: ConflictConfig) -> Claim:
    """A quantity claim. The key keeps the number and any magnitude word (``$5 million`` is not ``$5``); the unit label
    itself, in singular or plural form, is left out because the unit is compared on its own."""
    unit = normalize_unit(value.unit) if value.unit else ""
    family = family_of(config, unit) if unit else None
    folded = normalize_text(value.text).casefold()
    if value.range:
        return Claim(KIND_QUANTITY, family, " ".join(folded.split()), unit, None, value.text)
    number = normalize_number(value.text, value.negative)
    if number is None:
        return Claim(KIND_QUANTITY, family, " ".join(folded.split()), unit, None, value.text)
    qualifier = [word for word in _WORDS.findall(folded) if normalize_unit(word) != unit]
    key = f"{number}|{' '.join(qualifier)}" if qualifier else number
    return Claim(KIND_QUANTITY, family, key, unit, number, value.text)


def claims_of(
    question_type: QuestionType,
    values: tuple[Value, ...],
    markers: tuple[Marker, ...],
    config: ConflictConfig,
) -> tuple[Claim, ...]:
    """The claims of one piece. Only the kinds that the question asks about are claims (ARCHITECTURE §16.2)."""
    claims: list[Claim] = []
    if question_type == QuestionType.WHEN:
        for value in values:
            if value.kind in (ValueKind.DATE, ValueKind.PERIOD):
                claims.append(Claim(KIND_DATE, value.kind.value, normalize_date(value.text), "", None, value.text))
    elif question_type == QuestionType.HOW_MANY:
        for value in values:
            if value.kind in (ValueKind.DATE, ValueKind.PERIOD):
                continue
            if value.kind in (ValueKind.PERCENT, ValueKind.CURRENCY) or value.unit is not None:
                claims.append(_quantity(value, config))
                continue
            number = normalize_number(value.text, value.negative)
            if number is not None:
                claims.append(Claim(KIND_BARE, KIND_BARE, number, "", number, value.text))
    elif question_type == QuestionType.WHETHER:
        for marker in markers:
            polarity = "negative" if marker.negative else "positive"
            claims.append(Claim(KIND_POLARITY, KIND_POLARITY, polarity, "", None, marker.text))
    return tuple(claims)


def compare(first: Claim, second: Claim) -> bool | None:
    """True when the claims are equal, False when they differ, None when they cannot be compared.

    A bare number is compared with any quantity by its number, so a unit-less ``45`` is compared with ``30 days``. Two
    quantities with listed units from different families are not compared (``30 days`` and ``5 USD``). Two quantities
    are equal only when the number and the unit label are both equal: there is no unit conversion, so ``30 days`` and
    ``1 month`` differ, and a conflict between them is then screened as a difference.
    """
    if KIND_BARE in (first.kind, second.kind):
        if first.number is None or second.number is None:
            return None
        return first.number == second.number
    if first.kind != second.kind:
        return None
    if first.kind == KIND_QUANTITY:
        if first.family is not None and second.family is not None and first.family != second.family:
            return None
        return first.value == second.value and first.unit == second.unit
    return first.value == second.value

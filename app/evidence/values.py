"""Numbers, percentages, currency, dates and periods in source text, with exact offsets (ARCHITECTURE §14, D51).

``find_values`` reads one piece of text and returns its values. It never reads these as values (D51): a token
with more than one separator (``3.5.2``, ``1,2,3``), a hyphen-glued identifier (``ABC-123``, ``800-53``), a
footnote mark glued after a letter or after punctuation (``FISMA,1``, ``agencies.2``), a fraction, a time of
day, or an ordinal (``3rd``). A number and its unit may be separated by a line break, because PDF line wraps
put one there. The quote stays the raw slice.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class ValueKind(StrEnum):
    NUMBER = "number"
    PERCENT = "percent"
    CURRENCY = "currency"
    DATE = "date"
    PERIOD = "period"


@dataclass(frozen=True)
class Value:
    """One value in a text. ``start`` and ``end`` are half-open offsets into that text.

    ``unit`` is a lower-case label (``day``, ``%``, ``usd``, a count noun from the question) or ``None`` for a
    bare number. ``range`` is true for a range such as ``3 to 5 days``. ``negative`` is true when a minus sign
    directly precedes the number (the sign is part of the span).
    """

    kind: ValueKind
    text: str
    start: int
    end: int
    unit: str | None = None
    range: bool = False
    negative: bool = False


_YEAR = r"(?:1[89]|2[01])\d{2}"
_MONTH = (
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December"
    r"|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)\.?"
)
_DAY = r"\d{1,2}(?:st|nd|rd|th)?"
_ISO = r"\d{4}-\d{2}-\d{2}"
_DATE = rf"(?:{_ISO}|{_DAY}\s+{_MONTH}\s+{_YEAR}|{_MONTH}\s+{_DAY},?\s+{_YEAR}|{_MONTH}\s+{_YEAR})"
_DATE_OR_YEAR = rf"(?:{_DATE}|{_YEAR})"
# A number with thousands grouping, or a plain number with an optional decimal part.
_NUMBER = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_CURRENCY_CODES = "USD|EUR|GBP|INR|JPY|CAD|AUD|CHF|CNY"
_WORD_UNITS = (
    r"(?i:seconds?|minutes?|hours?|days?|weeks?|months?|years?|fortnights?|quarters?|kilograms?|grams?"
    r"|milligrams?|tonnes?|tons?|kilometres?|kilometers?|metres?|meters?|centimetres?|centimeters?"
    r"|millimetres?|millimeters?|miles?|feet|litres?|liters?|millilitres?|milliliters?|bytes?|kilobytes?"
    r"|megabytes?|gigabytes?|terabytes?)"
)
_ABBREVIATED_UNITS = r"(?-i:kg|mg|g|km|cm|mm|m|ml|lbs?|ft|KB|MB|GB|TB)"
_UNIT = rf"(?:{_WORD_UNITS}|{_ABBREVIATED_UNITS})"

_DATE_RE = re.compile(rf"(?<![\w./-]){_DATE}(?![\w/]|[.,-]\d)")
_PERIOD_RE = re.compile(
    rf"(?<![\w./-])(?:(?i:from|between)\s+)?(?P<a>{_DATE_OR_YEAR})"
    rf"\s*(?:[–—-]|\s+(?i:to|through)\s+)\s*(?P<b>{_DATE_OR_YEAR})(?![\w/]|[.,-]\d)"
)
_BETWEEN_PERIOD_RE = re.compile(
    rf"(?<![\w./-])(?i:between)\s+(?P<a>{_DATE_OR_YEAR})\s+(?i:and)\s+(?P<b>{_DATE_OR_YEAR})(?![\w/]|[.,-]\d)"
)
_RANGE_RE = re.compile(
    rf"(?<![\w./,-])(?P<n1>{_NUMBER})\s*(?:[–—-]|\s+(?i:to)\s+)\s*(?P<n2>{_NUMBER})"
    rf"(?P<gap>[ \t \r\n]*-?)(?P<unit>{_UNIT})(?![A-Za-z0-9_²³])"
)
_BETWEEN_RANGE_RE = re.compile(
    rf"(?<![\w./,-])(?i:between)\s+(?P<n1>{_NUMBER})\s+(?i:and)\s+(?P<n2>{_NUMBER})"
    rf"(?P<gap>[ \t \r\n]*-?)(?P<unit>{_UNIT})(?![A-Za-z0-9_²³])"
)
_PERCENT_RE = re.compile(
    rf"(?<![\w./,-])(?P<num>{_NUMBER})[ \t ]?(?:%|(?i:per\s?cent|percent))(?![A-Za-z0-9_²³])"
)
_SYMBOL_CURRENCY_RE = re.compile(
    rf"(?<![\w./,-])(?P<sym>[$€£¥])[ \t ]?(?P<num>{_NUMBER})"
    rf"(?:[ \t ]?(?:(?i:million|billion|thousand)|(?-i:bn|m|k))(?![A-Za-z]))?"
)
_PREFIX_CODE_RE = re.compile(rf"(?<![\w./,-])(?P<code>{_CURRENCY_CODES})[ \t ]?(?P<num>{_NUMBER})")
_SUFFIX_CODE_RE = re.compile(rf"(?<![\w./,-])(?P<num>{_NUMBER})[ \t ]?(?P<code>{_CURRENCY_CODES})(?![A-Za-z])")
_WORD_CURRENCY_RE = re.compile(
    rf"(?<![\w./,-])(?P<num>{_NUMBER})[ \t \r\n]*(?P<cur>(?i:dollars?|euros?|pounds?|rupees?|cents?))(?![A-Za-z])"
)
_NUMBER_RE = re.compile(_NUMBER)
_UNIT_AFTER_RE = re.compile(rf"(?P<sep>[ \t \r\n]+|-)(?P<unit>{_UNIT})(?![A-Za-z0-9_²³])")
_WORD_AFTER_RE = re.compile(r"(?P<sep>[ \t \r\n]+|-)(?P<word>[A-Za-z]+)(?![A-Za-z0-9_²³])")


def _is_one_of(character: str, choices: str) -> bool:
    """True when ``character`` is one of ``choices``. The empty string at a text edge is never one of them."""
    return character != "" and character in choices


def _bounds_ok(text: str, start: int, end: int) -> bool:
    """False for a number that is part of an identifier, a dotted token, a list or a footnote (D51)."""
    before = text[start - 1] if start > 0 else ""
    before_two = text[start - 2] if start > 1 else ""
    after = text[end] if end < len(text) else ""
    after_two = text[end + 1] if end + 1 < len(text) else ""
    if before.isalnum() or before == "_" or _is_one_of(before, "/:"):
        return False
    if _is_one_of(before, ".,") and (before_two.isalpha() or before_two.isdigit()):
        return False
    if _is_one_of(before, "-−") and before_two.isalnum():
        return False
    if after.isalnum() or after == "_" or _is_one_of(after, "/:²³"):
        return False
    if _is_one_of(after, ".,") and after_two.isdigit():
        return False
    if after == "-" and after_two.isdigit():
        return False
    return True


def _overlaps(taken: list[tuple[int, int]], start: int, end: int) -> bool:
    return any(start < other_end and other_start < end for other_start, other_end in taken)


def _count_noun_forms(nouns: Iterable[str]) -> dict[str, str]:
    """Map each count noun and its plural forms to the noun as the question wrote it (lower case)."""
    forms: dict[str, str] = {}
    for noun in nouns:
        canonical = noun.lower()
        if not canonical or not canonical.isalpha():
            continue
        for form in (canonical, canonical + "s", canonical + "es"):
            forms.setdefault(form, canonical)
        if canonical.endswith("s"):
            forms.setdefault(canonical[:-1], canonical)
    return forms


def find_values(text: str, *, count_nouns: Iterable[str] = ()) -> tuple[Value, ...]:
    """The values of ``text``, in order of position, each with its exact span.

    ``count_nouns`` are words from the question. A number directly followed by one of them is a value with
    that word as its unit (``9 members`` for ``How many members``).
    """
    taken: list[tuple[int, int]] = []
    found: list[Value] = []

    def take(value: Value) -> None:
        taken.append((value.start, value.end))
        found.append(value)

    for match in _PERIOD_RE.finditer(text):
        if not _overlaps(taken, match.start(), match.end()):
            take(Value(ValueKind.PERIOD, match.group(0), match.start(), match.end()))
    for match in _BETWEEN_PERIOD_RE.finditer(text):
        if not _overlaps(taken, match.start(), match.end()):
            take(Value(ValueKind.PERIOD, match.group(0), match.start(), match.end()))
    for match in _DATE_RE.finditer(text):
        if not _overlaps(taken, match.start(), match.end()):
            take(Value(ValueKind.DATE, match.group(0), match.start(), match.end()))

    for regex in (_RANGE_RE, _BETWEEN_RANGE_RE):
        for match in regex.finditer(text):
            if not _overlaps(taken, match.start(), match.end()):
                unit = match.group("unit").lower()
                take(Value(ValueKind.NUMBER, match.group(0), match.start(), match.end(), unit, range=True))

    for match in _PERCENT_RE.finditer(text):
        if not _overlaps(taken, match.start(), match.end()):
            take(Value(ValueKind.PERCENT, match.group(0), match.start(), match.end(), "%"))

    for match in _SYMBOL_CURRENCY_RE.finditer(text):
        if not _overlaps(taken, match.start(), match.end()):
            take(Value(ValueKind.CURRENCY, match.group(0), match.start(), match.end(), match.group("sym")))
    for match in _PREFIX_CODE_RE.finditer(text):
        if not _overlaps(taken, match.start(), match.end()):
            take(Value(ValueKind.CURRENCY, match.group(0), match.start(), match.end(), match.group("code").lower()))
    for match in _SUFFIX_CODE_RE.finditer(text):
        if not _overlaps(taken, match.start(), match.end()):
            take(Value(ValueKind.CURRENCY, match.group(0), match.start(), match.end(), match.group("code").lower()))
    for match in _WORD_CURRENCY_RE.finditer(text):
        if not _overlaps(taken, match.start(), match.end()):
            take(Value(ValueKind.CURRENCY, match.group(0), match.start(), match.end(), match.group("cur").lower()))

    forms = _count_noun_forms(count_nouns)
    for match in _NUMBER_RE.finditer(text):
        start, end = match.span()
        if _overlaps(taken, start, end) or not _bounds_ok(text, start, end):
            continue
        negative = start > 0 and text[start - 1] in "-−" and not (start > 1 and text[start - 2].isalnum())
        value_start = start - 1 if negative else start
        unit: str | None = None
        value_end = end
        unit_match = _UNIT_AFTER_RE.match(text, end)
        if unit_match is not None:
            unit = unit_match.group("unit").lower()
            value_end = unit_match.end()
        else:
            word_match = _WORD_AFTER_RE.match(text, end)
            if word_match is not None and word_match.group("word").lower() in forms:
                unit = forms[word_match.group("word").lower()]
                value_end = word_match.end()
        if _overlaps(taken, value_start, value_end):
            continue
        take(Value(ValueKind.NUMBER, text[value_start:value_end], value_start, value_end, unit, negative=negative))

    return tuple(sorted(found, key=lambda value: (value.start, value.end)))

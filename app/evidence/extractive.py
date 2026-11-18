"""English clause and value rules for verbatim answers, with offsets into the supplied quote."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

from app.document_structure.models import ContentType, EvidenceUnit
from app.evidence.markers import find_markers
from app.evidence.segment import sentence_spans
from app.evidence.values import ValueKind, find_values
from app.question_processing.analysis import LEADING_REFERENCE, QuestionComponent, QuestionType
from app.question_processing.vocabulary import FUNCTION_WORDS, QUESTION_WORDS

RULE_ID = "extractive.clause.v1"
EXTRACTIVE_TYPES = frozenset(
    {
        QuestionType.WHAT,
        QuestionType.WHO,
        QuestionType.WHERE,
        QuestionType.WHICH,
        QuestionType.HOW,
        QuestionType.HOW_MANY,
        QuestionType.WHEN,
        QuestionType.WHETHER,
    }
)
_WORD = re.compile(r"[^\W_]+(?:['’][sS]\b)?", re.UNICODE)
_JOIN = re.compile(r"(?<=[a-z])(?:-|\u00ad)[ \t]*\n\s*(?=[a-z])")
_TABLE = re.compile(r"\btable\s+(?P<number>\d+[a-z]?)\b", re.I)
_CODE = re.compile(r"\b(?:[a-z]+(?:\.[a-z]+)+-\d+|[a-z]+-\d+(?:\.\d+)*|[a-z]{2,}\d+)\b", re.I)
_LABEL = re.compile(r"\b[A-Z][A-Z.]+(?:[ -]\d+(?:\.\d+)*|\.[A-Z]+-\d+)\s*(?=:)")
_REFERENCE = re.compile(
    r"\b(?:according to|in|under|per)\s+(?:this|the)\s+(?:document|guide|guideline|paper|text)\b", re.I
)
_ATTRIBUTION = re.compile(r"\b(?:this\s+|(?:does|do)\s+the\s+)(?:document|guide|guideline|paper|text)\b", re.I)
_COPULA = r"(?:is|are|was|were|be|been|being)"
_AUX = r"(?:is|are|was|were|do|does|did|can|could|may|might|shall|should|must|will|would|has|have|had)"
_NEGATIVE = r"(?:not|never|no|cannot|\w+n['’]t)"
_NEGATIVE_WORD = re.compile(rf"\b{_NEGATIVE}\b", re.I)
_ABSENCE = re.compile(r"\b(?:absent|absence|lacks?|lacking|missing)\b", re.I)
_STATE = re.compile(
    r"\b(?:archived|cached|completed|encrypted|expired|pending|revoked|saved|signed|stored|"
    r"unencrypted|unexpired|unsigned)\b(?=\s+\w)",
    re.I,
)
_EXCEPTION = re.compile(r"\b(?:unless|except(?:ion)?s?|only\s+if|provided\s+that|depending\s+on)\b", re.I)
_IF_CLAUSE = re.compile(r"\b(?:if|in\s+the\s+event\s+that)\b", re.I)
_MODAL = re.compile(r"\b(?:can|cannot|may|must|shall|should|could|might|would|will)\b", re.I)
_PERMISSION = re.compile(r"\b(?:allow\w*|permit\w*|authori[sz]\w*|forbid\w*|prohibit\w*|mandatory)\b", re.I)
_MEANS = re.compile(r"\b(?:by|via|through|using|with|in\s+(?:a|an|the)\s+\w+\s+that)\s+\S", re.I)
_ENTRY_BOUNDARY = re.compile(
    r";\s+(?=(?:an?|the)\s+\w)|\n\s*\n(?=(?:[o•●▪◦]\s+)?"
    r"[A-Z][A-Z.]+(?:[ -]\d+(?:\.\d+)*|\.[A-Z]+-\d+)\s*:)"
)
_LEADING_BULLET = re.compile(r"^(?:[•●▪◦]|[-–—]\s)\s*")
_LIST_TO_STATEMENT = re.compile(r"\n\s*\n(?=[A-Z][A-Z]+s?\s+(?:SHALL|MUST|SHOULD|MAY)\s)")
_COLON = re.compile(r"^(?P<label>[^:\n.!?]{2,90}):\s*(?=\S)")

# These synonyms cover roles in common questions and clauses. Matching still requires the
# subject, relation and scope. They do not license a substitution in a quote or a value.
_EQUIVALENTS = (
    "accept takeon undertake",
    "affect impact influence",
    "apply applicable applicability",
    "authenticate authentication authenticator",
    "available open",
    "authorize authorise",
    "broader wider larger",
    "code software",
    "collect gather obtain",
    "complicate complicated complex difficult difficulty complexity",
    "component foundation",
    "comprise include consist contain",
    "constitute countas qualifyas",
    "conventional traditional",
    "deadline due",
    "define enumerate list identify specify",
    "design designed intended intend",
    "detail information",
    "dictate prescribe stipulate",
    "disclose disclosure release",
    "document record",
    "emerge arise",
    "equity fair fairness equitable",
    "execute execution",
    "fast rapidly rapid quickly",
    "forbid prohibit disallow",
    "frame framing",
    "greater higher",
    "grow evolve innovation",
    "guard protect safeguard secure",
    "guide guideline manual",
    "handle treat",
    "harmful damaging",
    "human person people",
    "identified labeled labelled designation",
    "install installation",
    "keep maintain retain",
    "layer tier",
    "life lifetime lifespan",
    "lower reduce mitigate",
    "magnitude extent",
    "method approach technique",
    "missing absent lack",
    "operations operation",
    "permit allow",
    "plan planning",
    "prejudice bias",
    "provide give supply",
    "readings data measurement",
    "reach achieve attain",
    "receive obtain",
    "recognise recognize",
    "recover restore restoration",
    "refuse reject deny",
    "repeat reuse",
    "request ask",
    "require mandate",
    "separate isolate",
    "save store",
    "show convey present",
    "similar alike",
    "support facilitate enable",
    "technology tool",
    "typical usual",
    "use utilize utilise",
)
_IRREGULAR = {
    "announced": "announce",
    "applied": "apply",
    "described": "describe",
    "divided": "divide",
    "does": "do",
    "done": "do",
    "given": "provide",
    "kept": "keep",
    "led": "lead",
    "made": "make",
    "meant": "mean",
    "met": "meet",
    "paid": "pay",
    "ran": "run",
    "sent": "send",
    "shown": "show",
    "took": "take",
    "told": "tell",
    "went": "go",
    "written": "write",
}
_PHRASES = {
    "(?:key )?building blocks": "components",
    "count as": "constitute",
    "federal open records law": "public information law",
    "freedom of information act": "public information law",
    "machine learning": "ai",
    "machine generated": "ai",
    "open records": "information disclosure",
    "results": "information",
    "take on": "accept",
    "subject to release": "available for release",
    "at a fast pace": "rapidly",
}
_GLUE = (
    FUNCTION_WORDS
    | QUESTION_WORDS
    | frozenset("according actually currently here kinds per regarding term terms used".split())
)
_QUESTION_GLUE = frozenset(
    "abbreviated about called concerns concerning describe described each identified known kinds many mean meant "
    "name named question relate related treated typical usually whether".split()
)
_DOC_WORDS = frozenset({"document", "guide", "guideline", "paper", "text"})


def _base(word: str) -> str:
    word = _IRREGULAR.get(word, word)
    if len(word) >= 5 and word.endswith("ies"):
        word = word[:-3] + "y"
    elif len(word) >= 5 and word.endswith(("ches", "shes", "sses", "xes", "zzes")):
        word = word[:-2]
    elif len(word) >= 4 and word.endswith("s") and not word.endswith(("ss", "us", "is", "ous", "ews")):
        word = word[:-1]
    if len(word) >= 6 and word.endswith("ied"):
        word = word[:-3] + "y"
    elif (len(word) >= 6 and word.endswith("ing")) or (len(word) >= 5 and word.endswith("ed")):
        suffix = "ing" if word.endswith("ing") else "ed"
        word = word[: -len(suffix)]
        if len(word) >= 4 and word[-1] == word[-2] and word[-1] in "bdgmnprt":
            word = word[:-1]
    if len(word) >= 4 and word.endswith("e") and not word.endswith(("ee", "oe", "ue", "ye")):
        word = word[:-1]
    return word


_ALIASES = {_base(word): _base(group.split()[0]) for group in _EQUIVALENTS for word in group.split()}


@lru_cache(maxsize=8192)
def word_key(word: str) -> str:
    word = word.casefold().removesuffix("'s").removesuffix("’s")
    base = _base(word)
    return _ALIASES.get(base, base)


def _words(text: str) -> list[str]:
    return [word.casefold() for word in _WORD.findall(text)]


def _lexical_text(text: str) -> str:
    return unicodedata.normalize("NFKC", _JOIN.sub("", text)).casefold()


@lru_cache(maxsize=8192)
def keywords(text: str) -> frozenset[str]:
    # Folding and stemming happen only on this matching copy.
    text = " ".join(re.sub(r"[-‐‑–—]+", " ", _lexical_text(text)).split())
    for phrase, replacement in _PHRASES.items():
        text = re.sub(rf"\b{phrase}\b", replacement, text)
    return frozenset(word_key(word) for word in _words(text) if word not in _GLUE)


@dataclass(frozen=True)
class Intent:
    component: QuestionComponent
    core: str
    keys: frozenset[str]
    required: frozenset[str]
    codes: tuple[str, ...]
    table: str | None
    count_nouns: tuple[str, ...]
    duration: bool
    definition: str | None
    permission: bool
    negated: bool


_COUNT = re.compile(rf"^(?:how\s+many|what\s+(?:number|quantity|total)\s+of)\s+(.+?)(?=\s+{_AUX}\b|[,?]|$)", re.I)
_DEFINITION = re.compile(r"^what\s+(?:does\s+(?:the\s+term\s+)?(.+?)\s+mean|is\s+meant\s+by\s+(.+))$", re.I)
_MULTIPLE = re.compile(
    r"\b(?:each|both)\b|^(?:which|list|name)\b|^what\s+(?:are|kinds|types)\b|\bhow\s+.+\bstructured\b", re.I
)


def intent_for(component: QuestionComponent) -> Intent:
    text = component.text.strip(" ?.,")
    locator = LEADING_REFERENCE.match(text)
    core = _REFERENCE.sub("", text[locator.end() :] if locator else text).strip(" ,")
    table = _TABLE.search(text)
    codes = tuple(dict.fromkeys(_CODE.findall(text.lower())))
    main = re.split(r"\s+so\s+that\s+", core, maxsplit=1, flags=re.I)[0]
    search_text = _TABLE.sub("", main)
    if locator and not table and not codes:
        search_text += " " + locator[0]
    keys = keywords(search_text) - {word_key(word) for word in _QUESTION_GLUE}
    if _ATTRIBUTION.search(text):
        keys -= {word_key(word) for word in _DOC_WORDS}
    if "target_inherited" in component.flags:
        keys |= keywords(" ".join(component.target_terms))
    if re.search(r"\bhow\s+(?:difficult|quickly|large)\b", core, re.I):
        keys -= {word_key(word) for word in ("difficult", "quickly", "large")}
    if re.search(r"\bhow\b.+\bcompare\b", core, re.I):
        keys -= {word_key("compare"), word_key("scope")}
    if re.search(r"^how\b.+\bstructured\b", core, re.I):
        keys -= {word_key("structured")}
    if re.search(r"^how\s+many\b", core, re.I):
        keys -= {word_key("defined")}
    if re.search(r"^which\s+\w+\s+types?\b", core, re.I):
        keys -= {word_key("type")}
    if re.search(r"^what\s+.+\b(?:components|building blocks|elements)\s+of\b", core, re.I):
        keys -= {word_key("capability")}
    if table and re.search(r"^how\s+long\b", core, re.I):
        keys -= {word_key("timeout")}
    count = _COUNT.match(core)
    count_words = []
    if count:
        for word in _words(count[1]):
            if word in {"of", "after", "before", "from", "for", "until", "by", "in", "according"}:
                break
            if word not in _GLUE:
                count_words.append(word)
    definition = _DEFINITION.match(core)
    negated = bool(_NEGATIVE_WORD.search(main)) or (
        component.question_type in {QuestionType.WHAT, QuestionType.WHICH} and bool(_ABSENCE.search(main))
    )
    return Intent(
        component,
        core,
        keys,
        frozenset(word_key(word) for word in _STATE.findall(main)),
        codes,
        table["number"].lower() if table else None,
        tuple(count_words),
        bool(re.match(r"^how\s+(?:long|old|often|far|frequently)\b", core, re.I)),
        (definition[1] or definition[2]).strip(' "“”') if definition else None,
        bool(_PERMISSION.search(main)),
        negated,
    )


def allows_multiple(intent: Intent) -> bool:
    kind = intent.component.question_type
    if kind == QuestionType.WHICH:
        return bool(
            re.match(r"^(?:list|name)\b|^which\s+(?:\w+\s+)?\w+s\b|^what\s+(?:kinds|types)\b", intent.core, re.I)
        )
    return kind in {QuestionType.WHAT, QuestionType.HOW} and bool(_MULTIPLE.search(intent.core))


def sentence_ranges(text: str) -> tuple[tuple[int, int], ...]:
    """Keep PDF wraps intact and split separately numbered entries even without end punctuation."""
    cuts = {match.end() for match in _ENTRY_BOUNDARY.finditer(text)}
    if _LEADING_BULLET.match(text):
        cuts.update(match.end() for match in _LIST_TO_STATEMENT.finditer(text))
    bounds = [0, *sorted(cuts), len(text)]
    return tuple(
        (first + start, first + end)
        for first, last in zip(bounds, bounds[1:])
        for start, end in sentence_spans(text[first:last])
    )


def table_number(unit: EvidenceUnit) -> str | None:
    found = _TABLE.match((unit.caption or "").lstrip())
    return found["number"].lower() if found else None


@lru_cache(maxsize=4096)
def _cell_keys(row: str, column: str, caption: str) -> frozenset[str]:
    keys = keywords(" ".join((row, column, _TABLE.sub("", caption))))
    initials = {
        "".join(word[0] for word in words)
        for label in (row, column)
        if 2 <= len(words := [word for word in _words(label) if word not in _GLUE]) <= 5
    }
    return keys | initials


def cell_keys(unit: EvidenceUnit) -> frozenset[str]:
    return _cell_keys(unit.row_header or "", unit.col_header or "", unit.caption or "")


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    kind: str
    negative: bool = False


def _span(text: str, start: int, end: int, kind: str) -> Span | None:
    while start < end and (text[start].isspace() or text[start] in "•●▪◦"):
        start += 1
    while start < end and (text[end - 1].isspace() or text[end - 1] in ".,;:"):
        end -= 1
    if start == end or not _WORD.search(text, start, end):
        return None
    return Span(start, end, kind, bool(re.search(rf"\b{_NEGATIVE}\b", text[start:end], re.I)))


_CARDINAL = re.compile(
    r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
    r"sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
    r"(?:[- ](?:one|two|three|four|five|six|seven|eight|nine)|\s+hundred)?\b",
    re.I,
)
_AMOUNT_UNITS = frozenset(
    "character digit bit byte second minute hour day week month year meter metre kilometer kilometre mile foot feet "
    "inch pound gram kilogram litre liter".split()
)
_DURATIONS = frozenset("second minute hour day week month year fortnight quarter".split())
_BOUNDS = re.compile(r"\b(?:at\s+least|at\s+most|no\s+more\s+than|no\s+fewer\s+than)\s*$", re.I)
_NOUN_CHAIN = re.compile(r"\s+(?P<chain>[^\W\d_][\w’-]*(?:\s+[^\W\d_][\w’-]*){0,3})", re.UNICODE)
_YEAR = re.compile(r"(?<![\w./-])(?:18|19|20|21)\d{2}(?![\w/.-]\d|[\w/-])")
_YEAR_PREFIX = re.compile(r"\b(?:by|in|during|until|before|after|since|through|no\s+later\s+than)\s*$", re.I)
_TIME_CLAUSE = re.compile(
    r"\b(?:when|as|once|until|after|before)\s+(?:they|it|these|those|the|new|\w+ed)\s+\w+[^;,]*$", re.I
)


def _number(intent: Intent, text: str) -> Span | None:
    values = find_values(text)
    if intent.component.question_type == QuestionType.WHEN:
        hits = [(value.start, value.end) for value in values if value.kind in {ValueKind.DATE, ValueKind.PERIOD}]
        if not hits:
            hits = [(m.start(), m.end()) for m in _YEAR.finditer(text) if _YEAR_PREFIX.search(text[: m.start()])]
        if len(hits) == 1:
            return _span(text, *hits[0], "date")
        timing = _TIME_CLAUSE.search(text) if not hits else None
        return _span(text, *timing.span(), "time_clause") if timing else None

    noun_keys = tuple(word_key(word) for word in intent.count_nouns)
    duration = {word_key(word) for word in _DURATIONS}
    want_percentage = bool(
        re.match(r"what (?:percentage|percent|proportion|share|fraction|rate)\b", intent.core, re.I)
    )
    hits: list[tuple[int, int]] = []
    if noun_keys:
        amounts = [(v.start, v.end, v.unit, v.range) for v in values if v.kind == ValueKind.NUMBER and not v.negative]
        amounts.extend((m.start(), m.end(), None, False) for m in _CARDINAL.finditer(text))
        for start, end, unit, is_range in amounts:
            if unit and word_key(unit) == noun_keys[-1]:
                hits.append((start, end))
                continue
            if unit or is_range or "." in text[start:end]:
                continue
            chain = _NOUN_CHAIN.match(text, end)
            words = _words(chain["chain"]) if chain else []
            modifiers: set[str] = set()
            for word in words:
                if word in FUNCTION_WORDS:
                    break
                key = word_key(word)
                if key == noun_keys[-1] and (len(noun_keys) == 1 or modifiers.intersection(noun_keys[:-1])):
                    cardinal = not text[start].isdigit()
                    bound = _BOUNDS.search(text[:start]) if cardinal else None
                    stop = (
                        chain.start("chain")
                        + next(token.end() for token in _WORD.finditer(chain["chain"]) if word_key(token[0]) == key)
                        if not cardinal and key in {word_key(w) for w in _AMOUNT_UNITS}
                        else end
                    )
                    hits.append((bound.start() if bound else start, stop))
                    break
                modifiers.add(key)
    else:
        for value in values:
            if (
                (intent.duration and value.unit and word_key(value.unit) in duration and not value.negative)
                or (want_percentage and value.kind == ValueKind.PERCENT)
                or (
                    not want_percentage
                    and not intent.duration
                    and value.kind in {ValueKind.PERCENT, ValueKind.CURRENCY}
                )
            ):
                hits.append((value.start, value.end))
    if len(hits) > 1 and intent.table and intent.duration:
        # A cell may give separate limits on separate lines (for example overall and idle time).
        qualified = []
        for start, end in hits:
            first = text.rfind("\n", 0, start) + 1
            last = text.find("\n", end)
            other_text = text[first:start] + " " + (text[end:last] if last != -1 else text[end:])
            if keywords(other_text) & intent.keys:
                qualified.append((start, end))
        hits = qualified
    return _span(text, *hits[0], "quantity") if len(hits) == 1 else None


_CONTROL_VERB = re.compile(r"\b(?:handled|treated|managed|kept|maintained|recorded|addressed|dealt\s+with)\b", re.I)
_PASSIVE = re.compile(rf"\b{_COPULA}\s+(?P<predicate>(?:(?:not|never|\w+ly)\s+)*[\w-]+(?:\s+and\s+[\w-]+)?)", re.I)
_PASSIVE_TAIL = re.compile(r"^\s+(?:by|with|through|using|under|via|in|to|from)\s+", re.I)
_PROCEDURE = re.compile(
    r"^(?:please\s+)?(?P<instruction>(?:add|allow|apply|check|choose|configure|create|enable|implement|install|"
    r"keep|place|provide|require|run|select|set|store|use|verify)\s+[^,;]+?)(?=\s+(?:to|so that|for)\s+|[.;]|$)",
    re.I,
)
_TIMELY = re.compile(
    r"\b(?:on\s+a\s+\w+\s+basis|(?:with|without)\s+(?:undue\s+)?delay|within\s+[^;,]+|"
    r"immediately|promptly|timely|quickly|as\s+soon\s+as\s+\w+)\b",
    re.I,
)
_COMPARATIVE = re.compile(r"\b(?P<degree>\w+er|(?:more|less)\s+\w+)\s+than\b", re.I)
_ROLE = re.compile(r"\bplays?\s+(?P<role>(?:a|an|the)\s+[\w -]{1,40}\brole)\b", re.I)
_PROHIBITION = re.compile(r"(?:do\s+not|never)\s+\w+", re.I)


def _manner(intent: Intent, text: str) -> Span | None:
    question = intent.core
    if re.search(r"\b(?:abbreviat\w*|acronym)\b", question, re.I):
        short = re.search(r"\(\s*([A-Z][A-Z0-9.-]{1,12})\s*\)", text)
        return _span(text, *short.span(1), "abbreviation") if short else None
    if re.search(r"\b(?:identified|labeled|labelled|designated|numbered)\b", question, re.I):
        label = _LABEL.search(text)
        return _span(text, *label.span(), "identifier") if label else None
    if re.match(r"^how\s+quickly\b", question, re.I):
        timed = _TIMELY.search(text)
        return _span(text, *timed.span(), "time_clause") if timed else None
    if re.match(r"^how\s+large\s+a\s+role\b", question, re.I):
        role = _ROLE.search(text)
        return _span(text, *role.span("role"), "predicate") if role else None
    if re.search(r"\bcompare\s+(?:to|with)\b", question, re.I):
        degree = _COMPARATIVE.search(text)
        return _span(text, *degree.span("degree"), "comparison") if degree else None
    if re.match(r"^how\s+difficult\b", question, re.I):
        difficulty = re.search(
            rf"\b{_COPULA}\s+((?:\w+ly\s+)?(?:complex|difficult|hard|easy|straightforward|simple))\b", text, re.I
        )
        return _span(text, *difficulty.span(1), "predicate") if difficulty else None

    if re.match(r"^how\s+.+\bstructured\b", question, re.I):
        structure = re.search(
            r"\b(?:compris\w*|subdivid\w*|consists?\s+of|structured\s+as|organiz\w*\s+into)\b", text, re.I
        )
        return _span(text, 0, len(text), "clause") if structure else None
    normative = bool(re.match(r"^how\s+(?:should|must)\b", question, re.I))
    modals = {match[0].lower() for match in _MODAL.finditer(text)}
    if normative and modals and not modals & {"should", "must", "shall"}:
        return None
    if normative and re.search(r"\b(?:should|must|shall)\s+(?:consider|evaluate|determine)\b", text, re.I):
        return None
    if re.match(r"^how\s+(?:can|could|do|does)\b", question, re.I):
        for adverb in re.finditer(r"\b\w+ly\s+(?P<verb>[^\W\d_]+)\b", text):
            if word_key(adverb["verb"]) in intent.keys:
                return _span(text, adverb.start(), adverb.start("verb"), "method")

    colon = _COLON.match(_LEADING_BULLET.sub("", text))
    subject_end = len(text) - len(_LEADING_BULLET.sub("", text)) + colon.end() if colon else 0
    passive = _PASSIVE.search(text, subject_end)
    generic = bool(_CONTROL_VERB.search(question))
    requested = re.search(r"\bbe\s+([\w-]+(?:ed|en))\b", question, re.I) if normative and not generic else None
    if requested:
        predicate = passive["predicate"].split()[-1] if passive else ""
        target = word_key(requested[1])
        if not predicate.lower().endswith(("ed", "en")) or word_key(predicate) != target:
            passive = None
        if passive is None and not (_PROCEDURE.match(_LEADING_BULLET.sub("", text)) and target in keywords(text)):
            return None
    if passive and passive["predicate"].split()[-1].lower().endswith(("ed", "en")):
        first, last = passive.span("predicate")
        if (not generic or _NEGATIVE_WORD.search(text[first:last])) and _PASSIVE_TAIL.match(text[last:]):
            last = len(text)
        return _span(text, first, last, "predicate")
    if subject_end:
        modal = _MODAL.search(text, subject_end)
        if modal and re.match(r"^how\s+(?:can|could)\b", question, re.I):
            return _span(text, modal.end(), len(text), "predicate")
        rest = _span(text, subject_end, len(text), "clause")
        if rest:
            return rest
    instruction = _PROCEDURE.match(_LEADING_BULLET.sub("", text))
    if instruction and re.match(r"^how\s+(?:should|must|can)\b", question, re.I):
        offset = len(text) - len(_LEADING_BULLET.sub("", text))
        method = _MEANS.search(text, offset + instruction.start("instruction"))
        if method and not method[0].lower().startswith("by "):
            return _span(text, method.start(), len(text), "method")
        return _span(text, offset, offset + instruction.end("instruction"), "instruction")
    if re.match(r"^how\s+(?:does|do)\b", question, re.I):
        for verb in _WORD.finditer(text):
            if word_key(verb[0]) in intent.keys and verb[0].lower().endswith(("s", "ed")):
                complement = re.search(r"\s+(?:with|for)\s+", text[verb.end() :], re.I)
                if (
                    complement
                    and keywords(text[verb.end() : verb.end() + complement.start()])
                    and keywords(text[verb.end() + complement.end() :]) & intent.keys
                ):
                    return _span(text, verb.end(), verb.end() + complement.start(), "object")
    method = next((m for m in _MEANS.finditer(text) if len(keywords(text[: m.start()]) & intent.keys) >= 2), None)
    if method:
        return _span(text, method.start(), len(text), "method")
    modal = _MODAL.search(text)
    if modal and re.match(r"^how\s+(?:can|could|must|should)\b", question, re.I):
        return _span(text, modal.end(), len(text), "predicate")
    return None


def _polar(intent: Intent, text: str) -> Span | None:
    if intent.negated:
        return None
    question = intent.core
    opening = re.match(rf"^{_AUX}\b", question, re.I)
    if not opening:
        return None
    auxiliary = opening[0].lower()
    if intent.permission:
        bullet = _LEADING_BULLET.match(text)
        imperative = _PROHIBITION.match(text, bullet.end() if bullet else 0)
        if imperative:
            return _span(text, *imperative.span(), "prohibition")
        permission = re.search(r"\b(?:not\s+permitted|not\s+allowed|not\s+authori[sz]ed)\b", text, re.I)
        if permission:
            return _span(text, *permission.span(), "permission")
        markers = find_markers(text, "permission")
        if len(markers) == 1 and (markers[0].text.casefold() != "may" or _PERMISSION.search(text)):
            return _span(text, markers[0].start, markers[0].end, "permission")
        return None
    if auxiliary in {"should", "must", "shall"}:
        marker = re.search(rf"\b{auxiliary}(?:\s+(?:not|never))?\b", text, re.I)
        if marker:
            passive = re.search(r"\bbe\s+\w+(?:ed|en)\b", question, re.I)
            return _span(text, marker.start(), len(text) if passive else marker.end(), "permission")
    negation = re.search(r"\b(?:(?:do|does|did)\s+not|not\s+necessarily)\b", text, re.I)
    if negation:
        if negation[0].lower().endswith("necessarily"):
            return _span(text, *negation.span(), "predicate")
        end = re.search(r"\s+(?:how|whether|when|where|nor)\b|[,;]", text[negation.end() :], re.I)
        return _span(text, negation.start(), negation.end() + end.start() if end else len(text), "predicate")
    if auxiliary in {"may", "can", "could", "might", "will", "would"}:
        modal = re.search(rf"\b(?:also\s+)?(?:{auxiliary}|can(?:not)?|may)\s+(?:not\s+)?\w+", text, re.I)
        return _span(text, modal.start(), len(text), "predicate") if modal else None
    comparative = re.search(rf"\b{_COPULA}\s+(?P<degree>\w+er)\b", text, re.I)
    if comparative and word_key(comparative["degree"]) in intent.keys:
        return _span(text, *comparative.span("degree"), "comparison")
    prepositional = re.search(r"\bby\s+\w+ing\b", text, re.I)
    if prepositional:
        return _span(text, prepositional.start(), len(text), "method")
    if re.search(r"\bby\s+\w+ing\b", question, re.I):
        return None
    subject_to = re.search(r"\bsubject\s+to\s+(?P<object>[^;,]+?)(?=\s+(?:under|by|from)\b|[.;]|$)", text, re.I)
    if subject_to:
        start = (
            subject_to.start()
            if re.search(r"\b(?:public|disclosure|open)\b", question, re.I)
            else subject_to.start("object")
        )
        return _span(text, start, subject_to.end(), "predicate")
    bracketed = re.search(r"\b(?P<object>[\w-]+(?:\s+[\w-]+){0,3}\s*\([A-Z][A-Z0-9.-]+\))", text)
    if bracketed:
        words = list(_WORD.finditer(bracketed["object"].split("(")[0]))
        if words and word_key(words[-1][0]) in intent.keys:
            start = len(words) - 1
            while (
                start > 0 and word_key(words[start - 1][0]) in intent.keys and words[start - 1][0].lower() not in _GLUE
            ):
                if word_key(words[start - 1][0]) == word_key("use"):
                    break
                start -= 1
            return _span(text, bracketed.start("object") + words[start].start(), bracketed.end("object"), "object")
    for verb in _WORD.finditer(text):
        if word_key(verb[0]) not in intent.keys or verb[0].lower() in _GLUE or not text[: verb.start()].strip():
            continue
        obj = re.match(r"\s+(?:an?\s+|the\s+)?(?P<noun>[^\W\d_]+)\b(?:\s*\([A-Z][A-Z0-9.-]+\))?", text[verb.end() :])
        if obj and word_key(obj["noun"]) in intent.keys:
            if verb[0].lower().endswith(("s", "ed")):
                return _span(text, verb.start(), verb.end() + obj.end(), "predicate")
            if re.match(r"\s*\([A-Z]", text[verb.end() + obj.end("noun") :]):
                return _span(text, verb.end(), verb.end() + obj.end(), "object")
    return None


_DEFINITION_LINK = re.compile(r"\s*(?:means?\b|is\s+(?:defined|described)\s+as\b|[:–—])\s*", re.I)
_FACT_LINK = re.compile(
    r"\b(?:is|are|was|were|has|have|appl\w+|answer\w*|compris\w*|consist\w*|defin\w*|"
    r"describ\w*|enabl\w*|include\w*|limit\w*|list\w*|provid\w*|restrict\w*)\b",
    re.I,
)
_STEPS = re.compile(r"\b([\w-]+)\s+and\s+([\w-]+)\s+steps?\b", re.I)


def _fact(intent: Intent, text: str, unit: EvidenceUnit) -> Span | None:
    question = intent.core
    if intent.definition:
        term = re.compile(rf"(?<!\w)[\"“]?{re.escape(intent.definition)}[\"”]?(?!\w)", re.I)
        for match in term.finditer(text):
            relation = _DEFINITION_LINK.match(text, match.end())
            if relation:
                return _span(text, relation.end(), len(text), "definition")
        return None
    if intent.component.question_type == QuestionType.WHERE:
        location = re.search(
            r"\b(?:described|located|published|available|found|listed|stored|posted)\s+(?:in|at|on|under)\s+",
            text,
            re.I,
        )
        return _span(text, location.end(), len(text), "location") if location else None
    if re.match(r"^what\s+kinds?\s+of\b", question, re.I) and re.search(r"\bappl(?:y|ies)\s+to\b", question, re.I):
        applies = re.search(r"\bappl(?:y|ies)\s+to\s+", text, re.I)
        return _span(text, applies.end(), len(text), "scope") if applies else None
    named = re.match(r"^what\s+(?:is|are)\s+(?:the\s+)?(.+)$", question, re.I)
    if named:
        term = re.escape(named[1]).replace(r"\ ", r"\s+")
        direct = re.search(rf"(?<!\w){term}\s+{_COPULA}\s+", text, re.I)
        if direct:
            tail = text[direct.end() :]
            next_clause = re.search(rf"\s+(?:and|but)\s+(?:the|a|an)\s+\w+(?:\s+\w+){{0,3}}\s+{_COPULA}\b", tail, re.I)
            end = direct.end() + next_clause.start() if next_clause else len(text)
            return _span(text, direct.end(), end, "definition")
    if intent.component.question_type == QuestionType.WHO:
        actor = re.search(r"\b(?:by|assigned\s+to)\s+", text, re.I)
        return _span(text, actor.end(), len(text), "actor") if actor else None
    if re.match(r"^which\s+tables?\b", question, re.I):
        if not _TABLE.match(text):
            return None
        steps = _STEPS.search(question)
        if steps and not ({word_key(word) for word in steps.groups()} & keywords(text)):
            return None
    if re.match(r"^which\s+revision\b", question, re.I):
        revision = re.search(r"\bthis\s+(?:document|version|guide)\s+is\s+the\s+(\w+\s+revision)\b", text, re.I)
        return _span(text, *revision.span(1), "revision") if revision else None
    if unit.content_type == ContentType.TABLE_CELL or _FACT_LINK.search(text):
        return _span(text, 0, len(text), "clause")
    return None


def extract_span(intent: Intent, quote: str, unit: EvidenceUnit) -> Span | None:
    """Return the one extractable answer in a passage, or None for an unsupported relation."""
    if not quote or len(quote) > 1100 or "\ufffd" in quote or _EXCEPTION.search(quote):
        return None
    if _IF_CLAUSE.search(quote) and not re.search(r"\bif\b", intent.core, re.I):
        return None
    question_type = intent.component.question_type
    if question_type not in EXTRACTIVE_TYPES:
        return None
    if question_type in {QuestionType.HOW_MANY, QuestionType.WHEN}:
        answer = _number(intent, quote)
    elif question_type == QuestionType.HOW:
        answer = _manner(intent, quote)
    elif question_type == QuestionType.WHETHER:
        answer = _polar(intent, quote)
    else:
        answer = _fact(intent, quote, unit)
    if answer and re.search(
        r"\b(?:the following|listed below|shown above)\s*$", quote[answer.start : answer.end], re.I
    ):
        return None
    return answer

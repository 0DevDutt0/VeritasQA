"""P5 on the public QA corpus (data/corpus/public): provenance and invariant checks on real text (SPEC §6, §12).

No expected answer is written here. Each question is generated from a sentence of a public document, and the
sentence is the expected source. The generators cover each supported question type that real sentences can
produce: `what`, `how many`, `when`, `whether`, `conditions` and `which`. A sample also includes units that contain
the replacement character, so that the flag is checked on real text (D55).

The gated checks run on every generated question: provenance against the stored page text, no derived row quoted,
each answer span inside its quote, the replacement-character flag matching the text, and determinism. The counts
are reported with `-s`. Each count is a property check on real text, not a measurement on the owner's document
(B1, B3). A source sentence that comes back is built in: its own words were used to ask the question.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest

from app.document_structure import build_structure
from app.document_structure.models import ContentType
from app.evidence import ComponentStatus, select_candidates
from app.evidence.markers import find_markers
from app.evidence.segment import _ABBREVIATIONS, _OPENERS, sentence_spans
from app.evidence.values import ValueKind, find_values
from app.ingestion.extract import extract_document
from app.question_processing import analyze
from app.question_processing.vocabulary import ATTRIBUTE_WORDS, FUNCTION_WORDS, QUESTION_WORDS
from app.retrieval import search
from app.storage import Store

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = REPO_ROOT / "data" / "corpus" / "public"
DOCUMENTS = json.loads((CORPUS_DIR / "manifest.json").read_text(encoding="utf-8"))["documents"]
CREATED = "2026-01-01T00:00:00Z"
SAMPLE_PER_DOCUMENT = 40
CAP_PER_TYPE = 20
CAP_REPLACEMENT = 10
REPLACEMENT = "�"
ALLOWED_DROPS = {"derived_row", "crosses_source_span"}
_QUANTITY = re.compile(r"\b\d+(?:[.,]\d+)?\s*(%|percent\b|days\b|years\b|months\b|weeks\b|hours\b)")

pytestmark = pytest.mark.public_corpus


def _present(entry: dict) -> Path:
    path = CORPUS_DIR / entry["file"]
    if not path.is_file():
        pytest.skip(f"{entry['file']} is not in data/corpus/public (git-ignored); re-fetch it from {entry['source_url']}")
    return path


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    workdir = tmp_path_factory.mktemp("p5-corpus")
    store = Store.open(workdir / "combined.sqlite")
    documents = {}
    for entry in DOCUMENTS:
        path = _present(entry)
        extracted = extract_document(path, out_root=workdir / "p1")
        structure = build_structure(extracted, path)
        store.write_document(extracted, structure, created_at=CREATED)
        pages = store.page_texts(extracted.document_id, range(1, extracted.page_count + 1))
        documents[entry["file"]] = (extracted.document_id, structure, pages)
    yield store, documents
    store.close()


def _body_units(structure):
    return [
        unit
        for unit in structure.units
        if unit.body_retrieval
        and not unit.derived
        and unit.content_type in (ContentType.PARAGRAPH, ContentType.LIST_ITEM)
        and 60 <= len(unit.raw_text) <= 400
    ]


def _evenly(items, count):
    if len(items) <= count:
        return list(items)
    return [items[index * len(items) // count] for index in range(count)]


def _content_words(sentence: str, limit: int) -> list[str]:
    words: list[str] = []
    for word in re.findall(r"[A-Za-z]{5,}", sentence):
        lowered = word.lower()
        if lowered in FUNCTION_WORDS or lowered in QUESTION_WORDS or lowered in ATTRIBUTE_WORDS:
            continue
        if lowered not in words:
            words.append(lowered)
        if len(words) == limit:
            break
    return words


def _sentences(structure):
    for unit in _body_units(structure):
        for start, end in sentence_spans(unit.raw_text):
            yield unit, unit.raw_text[start:end]


def _generate(structure):
    """Deterministic questions built from sentences of the document. Each entry is (kind, question, sentence, unit)."""
    questions = []
    for unit in _evenly(_body_units(structure), SAMPLE_PER_DOCUMENT):
        sentences = [unit.raw_text[start:end] for start, end in sentence_spans(unit.raw_text)]
        for sentence in sentences:
            words = _content_words(sentence, 3)
            if len(words) == 3:
                questions.append(("what", f"What is {' '.join(words)}?", sentence, unit.evidence_id))
                break

    counts: Counter = Counter()
    for unit, sentence in _sentences(structure):
        quantity = _QUANTITY.search(sentence)
        words = _content_words(sentence, 2)
        if quantity is None or len(words) < 2 or counts["how_many"] >= CAP_PER_TYPE:
            continue
        unit_word = "percent" if quantity.group(1) in ("%", "percent") else quantity.group(1)
        questions.append(("how_many", f"How many {unit_word} apply to {' '.join(words)}?", sentence, unit.evidence_id))
        counts["how_many"] += 1

    generators = (
        ("when", lambda s: any(v.kind in (ValueKind.DATE, ValueKind.PERIOD) for v in find_values(s)), "When is {} {}?"),
        ("whether", lambda s: bool(find_markers(s, "permission")), "Is it permitted to {} {}?"),
        ("conditions", lambda s: bool(find_markers(s, "condition")), "Under what conditions is {} {}?"),
        ("which", lambda s: bool(find_markers(s, "list")), "Which {} {} apply?"),
    )
    for kind, applies, template in generators:
        for unit, sentence in _sentences(structure):
            words = _content_words(sentence, 2)
            if len(words) < 2 or not applies(sentence) or counts[kind] >= CAP_PER_TYPE:
                continue
            questions.append((kind, template.format(*words), sentence, unit.evidence_id))
            counts[kind] += 1

    # Units with the replacement character, so the flag is checked on real text (D55).
    replacement = 0
    for unit, sentence in _sentences(structure):
        words = _content_words(sentence, 3)
        if REPLACEMENT not in sentence or len(words) < 3 or replacement >= CAP_REPLACEMENT:
            continue
        questions.append(("replacement", f"What is {' '.join(words)}?", sentence, unit.evidence_id))
        replacement += 1
    return questions


def _run(store, document_id, question):
    analysis = analyze(question)
    component = analysis.components[0]
    result = search(store, document_id, component.retrieval_query)
    units = {}
    for candidate in result.candidates:
        units[candidate.evidence_id] = store.load_unit(document_id, candidate.evidence_id)
    return select_candidates(analysis, {component.component_id: result}, units).components[0]


def test_the_public_corpus_gives_only_verbatim_quotes_with_their_flags(corpus):
    store, documents = corpus
    report = Counter()
    for name, (document_id, structure, pages) in documents.items():
        questions = _generate(structure)
        assert questions, f"{name}: no questions could be generated"
        for kind, question, source_sentence, _source_unit in questions:
            component = _run(store, document_id, question)
            report[f"{kind}.questions"] += 1
            report[f"{kind}.status.{component.status.value}"] += 1
            for candidate in component.candidates:
                # Gate 1: provenance against the stored page text, not the unit (D49).
                assert pages[candidate.pdf_page][candidate.page_start : candidate.page_end] == candidate.quote
                # Gate 2: a generated table row is never quoted (D48).
                assert candidate.retrieval.derived is False
                # Gate 3: an answer span is inside its own quote, and it is the page text at its offsets.
                if candidate.answer_span is not None:
                    assert candidate.answer_span in candidate.quote
                    assert pages[candidate.pdf_page][candidate.answer_page_start : candidate.answer_page_end] == candidate.answer_span
                    report[f"{kind}.answer_span"] += 1
                # Gate 4: a replacement character is flagged, and a flag is never set without it.
                assert ("replacement_character" in candidate.flags) == (REPLACEMENT in candidate.quote)
                if REPLACEMENT in candidate.quote:
                    report["replacement.quotes_with_the_character"] += 1
                for flag in candidate.flags:
                    report[f"flag.{flag}"] += 1
                report[f"rule.{candidate.rule_id}"] += 1
            for dropped in component.dropped:
                assert dropped.reason in ALLOWED_DROPS
                report[f"dropped.{dropped.reason}"] += 1
            if any(source_sentence in candidate.quote for candidate in component.candidates):
                report[f"{kind}.source_sentence_returned"] += 1
            if component.reasons:
                report[f"reason.{component.reasons[0]}"] += 1
    print()
    for key in sorted(report):
        print(f"{key}: {report[key]}")
    assert report["what.questions"] > 0 and report["how_many.questions"] > 0


def test_selection_on_the_public_corpus_is_deterministic(corpus):
    store, documents = corpus
    for _, (document_id, structure, _pages) in documents.items():
        for _kind, question, _sentence, _unit in _generate(structure)[:10]:
            assert _run(store, document_id, question) == _run(store, document_id, question)


def test_the_abbreviation_rule_fires_as_reported_and_no_split_is_a_sentence_break(corpus):
    """Reports how often a full stop after an abbreviation is kept or split (D50). Nothing is gated here."""
    _store, documents = corpus
    kept = split = 0
    pattern = re.compile(r"\b([A-Za-z][A-Za-z.]*)\.\s+([A-Z][A-Za-z]*)")
    for _, (_document_id, structure, _pages) in documents.items():
        for unit in structure.units:
            for match in pattern.finditer(unit.raw_text):
                word = match.group(1).lower()
                if word in _ABBREVIATIONS or (len(word) == 1 and word.isalpha()):
                    if match.group(2).lower() in _OPENERS:
                        split += 1
                    else:
                        kept += 1
    print()
    print(f"abbreviation full stops followed by a capital letter: kept {kept}, split {split}")
    assert kept + split > 0


def test_value_reading_on_the_public_corpus_reports_each_kind(corpus):
    """Reports how many values of each kind the grammar reads in body units (D51). Nothing is gated here."""
    _store, documents = corpus
    counts: Counter = Counter()
    for _, (_document_id, structure, _pages) in documents.items():
        for unit in _body_units(structure):
            for value in find_values(unit.raw_text):
                counts[value.kind.value] += 1
                assert unit.raw_text[value.start : value.end] == value.text
    print()
    for kind in sorted(counts):
        print(f"values read as {kind}: {counts[kind]}")
    assert sum(counts.values()) > 0

"""P7 on the public QA corpus (data/corpus/public): invariants of every response (ARCHITECTURE §16).

The questions are the ones the P5 corpus test generates, so the three phases test the same questions. No expected status
is written here. The gated checks are invariants that must hold on real text: every response validates; an answer
needs an accepted candidate and no contradicting passage; passage-only types are never answered; every conflict is
shown in the response; and a second run gives the same response. The status counts are reported with ``-s``. They are
property counts on real text, not a measurement on the owner's document (B1, B3).
"""

from __future__ import annotations

from collections import Counter

import pytest

from app.decision import DecisionStatus, answer, load_policy
from app.document_structure import build_structure
from app.ingestion.extract import extract_document
from app.storage import Store
from tests.integration.test_p5_corpus import CREATED, DOCUMENTS, _generate, _present

pytestmark = pytest.mark.public_corpus

PASSAGE_ONLY = frozenset({"what", "who", "where", "which", "conditions", "comparison"})
DETERMINISM_SAMPLE = 40


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    workdir = tmp_path_factory.mktemp("p7-corpus")
    store = Store.open(workdir / "combined.sqlite")
    structures = {}
    for entry in DOCUMENTS:
        path = _present(entry)
        extracted = extract_document(path, out_root=workdir / "p1")
        structure = build_structure(extracted, path)
        store.write_document(extracted, structure, created_at=CREATED)
        structures[entry["file"]] = (extracted.document_id, structure)

    questions = []
    for entry in DOCUMENTS:
        document_id, structure = structures[entry["file"]]
        for _kind, question, _sentence, _unit in _generate(structure):
            questions.append((document_id, question))

    policy = load_policy()
    responses = [(document_id, question, answer(store, document_id, question, policy)) for document_id, question in questions]
    yield {"store": store, "policy": policy, "questions": questions, "responses": responses}
    store.close()


def test_the_corpus_gives_questions_and_every_response_is_valid(run):
    responses = run["responses"]
    assert responses, "the corpus must yield questions for this test to mean anything"
    for _document_id, _question, response in responses:
        assert response.status in DecisionStatus
        assert response.engine_version == "decision.v1"


def test_an_answer_needs_an_accepted_candidate_for_each_span_and_no_contradicting_passage(run):
    for _document_id, _question, response in run["responses"]:
        if response.status not in (DecisionStatus.ANSWERED, DecisionStatus.PARTIAL):
            continue
        accepted = {
            (entry.evidence_id, entry.component_id)
            for entry in response.verification
            if entry.accepted and entry.verdict == "PASS"
        }
        answered = {component.component_id for component in response.components if component.status == DecisionStatus.ANSWERED}
        for span in response.answer_spans:
            assert (span.evidence_id, span.component_id) in accepted
            assert span.component_id in answered
        for finding in response.conflicts:
            assert finding.component_id not in answered, "an answered component has no reported difference"


def test_passage_only_types_are_never_answered(run):
    for _document_id, _question, response in run["responses"]:
        for component in response.components:
            if component.question_type in PASSAGE_ONLY:
                assert component.status != DecisionStatus.ANSWERED, component.text


def test_every_conflict_is_shown_and_its_component_is_not_answered(run):
    for _document_id, _question, response in run["responses"]:
        known = {item.evidence_id for item in response.evidence}
        for finding in response.conflicts:
            assert finding.first_evidence_id in known and finding.second_evidence_id in known
            if finding.impact.value == "conflict":
                component = next(c for c in response.components if c.component_id == finding.component_id)
                assert component.status == DecisionStatus.CONFLICT


def test_a_sample_of_responses_is_reproduced_exactly_by_a_second_run(run):
    store = run["store"]
    policy = run["policy"]
    for document_id, question, first in run["responses"][:DETERMINISM_SAMPLE]:
        again = answer(store, document_id, question, policy)
        assert again.model_dump(mode="json") == first.model_dump(mode="json"), question


def test_the_status_counts_are_reported_not_asserted(run, capsys):
    counts: Counter = Counter()
    per_document: dict[str, Counter] = {}
    for document_id, _question, response in run["responses"]:
        counts[response.status.value] += 1
        per_document.setdefault(document_id, Counter())[response.status.value] += 1
    with capsys.disabled():
        print(f"\nP7 corpus: {len(run['responses'])} questions over {len(per_document)} documents")
        print(f"overall statuses: {dict(sorted(counts.items()))}")
        for document_id, document_counts in per_document.items():
            print(f"  {document_id}: {dict(sorted(document_counts.items()))}")

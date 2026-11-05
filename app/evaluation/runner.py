"""The evaluation run: answer each selected gold record, score it, and write the run record (ARCHITECTURE §17.12; D85).

The run reads the store and calls :func:`app.decision.answer` once per selected record. It never changes the store
except for one ``evaluations`` row. The run JSON goes to ``output_dir``, which the caller always supplies, so tests write
to ``tmp_path`` and the owner's ``data/evaluations/runs/`` is only written by the command-line interface (P10).
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.common.files import write_json
from app.conflict.config import ConflictConfig, load_conflict_config
from app.decision import ENGINE_VERSION, answer, load_policy
from app.decision.policy import AcceptancePolicy
from app.decision.response import DecisionStatus, QAResponse
from app.evaluation.errors import EvaluationError
from app.evaluation.gold import GoldDataset, Source, Split, check_against_store, select_split
from app.evaluation.metrics import Z_95
from app.evaluation.scoring import (
    RETRIEVAL_KS,
    ObservedComponent,
    ObservedEvidence,
    ObservedResponse,
    ObservedRetrieval,
    ObservedSpan,
    RecordScore,
    UnitView,
    build_metrics,
    score_record,
)
from app.retrieval.config import RetrievalConfig, load_retrieval_config
from app.retrieval.rules import RuleSet, load_rules
from app.storage import Store

CONFIDENCE_LEVEL = 0.95
RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}")
SYNTHETIC_BANNER = "Synthetic test set. This is not a measurement of the owner's document."
LIMITATIONS = (
    "A rate with a small n has a wide interval. Read n next to every rate.",
    "Means (MRR, nDCG and token F1) carry n and no interval in this phase.",
    "The extraction measures of SPEC §11 are not computed here (ARCHITECTURE §17.14).",
    "The risk-coverage ordering uses retrieval rank only. It is an ordering, not a probability (SPEC §9).",
    "Passage-only question types abstain by design (PROGRESS.md decisions D65 and D73). Read the breakdown by type.",
)


@dataclass(frozen=True)
class EvaluationRun:
    """The result of one run. ``config`` and ``metrics`` are the two JSON texts stored in the ``evaluations`` row."""

    run_id: str
    created_at: str
    split: str
    final_run: bool
    source: str
    dataset_sha256: str
    record_count: int
    config: dict[str, Any]
    metrics: dict[str, Any]
    records: tuple[dict[str, Any], ...]
    output_path: Path


def _canonical(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _observe(
    response: QAResponse,
    store: Store,
    document_id: str,
    retrieval_k: int,
    units: dict[str, UnitView],
) -> ObservedResponse:
    """Copy the fields the harness reads from the engine's response. Units are read from the store, once per ID."""
    index_of = {component.component_id: index for index, component in enumerate(response.components, start=1)}
    components = tuple(
        ObservedComponent(
            index=index,
            accepted=component.status is DecisionStatus.ANSWERED,
            evidence_ids=tuple(component.evidence_ids),
            verified_ids=frozenset(
                verification.evidence_id
                for verification in response.verification
                if verification.component_id == component.component_id and verification.accepted
            ),
        )
        for index, component in enumerate(response.components, start=1)
    )
    spans = tuple(
        ObservedSpan(
            text=span.text,
            evidence_id=span.evidence_id,
            component=index_of[span.component_id],
            pdf_page=span.pdf_page,
            start=span.start,
            end=span.end,
        )
        for span in response.answer_spans
    )
    evidence = tuple(
        ObservedEvidence(
            evidence_id=item.evidence_id,
            pdf_page=item.pdf_page,
            quote=item.quote,
            source_start=item.source_start,
            source_end=item.source_end,
            components=frozenset(index_of[component_id] for component_id in item.component_ids),
        )
        for item in response.evidence
    )
    summaries = {summary.component_id: summary for summary in response.retrieval}
    retrieval = []
    for index, component in enumerate(response.components, start=1):
        summary = summaries.get(component.component_id)
        if summary is None:
            # A component that was not searched returned no candidates, at the configured depth.
            retrieval.append(ObservedRetrieval(component=index, k_cut=retrieval_k, entries=()))
        else:
            entries = tuple((entry.rank, entry.evidence_id) for entry in summary.entries)
            retrieval.append(ObservedRetrieval(component=index, k_cut=summary.k, entries=entries))
    needed = (
        {evidence_id for item in retrieval for _, evidence_id in item.entries}
        | {item.evidence_id for item in evidence}
        | {span.evidence_id for span in spans}
    )
    for evidence_id in sorted(needed):
        if evidence_id not in units:
            unit = store.load_unit(document_id, evidence_id)
            if unit is None:
                raise EvaluationError(f"unit {evidence_id} is not in the stored document")
            units[evidence_id] = (unit.pdf_page, unit.raw_text)
    question_type = response.components[0].question_type if len(response.components) == 1 else "compound"
    return ObservedResponse(
        status=response.status.value,
        question_type=question_type,
        components=components,
        spans=spans,
        evidence=evidence,
        retrieval=tuple(retrieval),
    )


def _row(score: RecordScore) -> dict[str, Any]:
    """One record of the run JSON. It repeats no text of the source, only identifiers and the checks."""
    return {
        "record_id": score.record_id,
        "category": score.category,
        "question_type": score.question_type,
        "expected_status": score.expected_status,
        "status": score.status,
        "outcome": score.outcome,
        "accepted": score.accepted,
        "best_rank": score.best_rank,
        "components": [
            {
                "index": component.index,
                "expected_answerable": component.expected_answerable,
                "accepted": component.accepted,
                "correct": component.correct,
                "supported": component.supported,
                "cites_gold_page": component.cites_gold_page,
                "unsupported": component.unsupported,
                "best_rank": component.best_rank,
            }
            for component in score.components
        ],
        "exact_match": [item.exact for item in score.answer_items],
    }


def run_evaluation(
    store: Store,
    document_id: str,
    dataset: GoldDataset,
    split: str | Split,
    *,
    final_run: bool = False,
    output_dir: Path | str,
    run_id: str | None = None,
    created_at: str | None = None,
    policy: AcceptancePolicy | None = None,
    retrieval_config: RetrievalConfig | None = None,
    rules: RuleSet | None = None,
    conflict_config: ConflictConfig | None = None,
) -> EvaluationRun:
    """Run one split of a gold dataset against one stored document (ARCHITECTURE §17.12).

    Every selected record is checked against the store before the first answer is computed, so a bad quotation stops
    the run before any answer is made. The configuration is loaded once and passed to every call. ``run_id`` and
    ``created_at`` default to a random id and the current UTC time. Both can be given, so a test can compare two runs.
    """
    if run_id is not None and not RUN_ID_PATTERN.fullmatch(run_id):
        raise EvaluationError(
            f"run id {run_id!r} must be 1 to 80 letters, digits, dots, dashes or underscores, "
            "starting with a letter or digit, because it becomes a file name"
        )
    if not store.has_document(document_id):
        raise EvaluationError(f"document {document_id} is not in the store")
    records = select_split(dataset, split, final_run=final_run)
    for record in records:
        check_against_store(record, store, document_id)

    policy = policy if policy is not None else load_policy()
    retrieval_config = retrieval_config if retrieval_config is not None else load_retrieval_config()
    rules = rules if rules is not None else load_rules()
    conflict_config = conflict_config if conflict_config is not None else load_conflict_config()
    run_id = run_id if run_id is not None else uuid.uuid4().hex
    created_at = created_at if created_at is not None else datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    target = Path(output_dir) / f"{run_id}.json"
    if target.exists() or store.read_evaluation(run_id) is not None:
        raise EvaluationError(f"evaluation run {run_id} is already recorded; choose another run_id")

    units: dict[str, UnitView] = {}
    scores: list[RecordScore] = []
    rows: list[dict[str, Any]] = []
    for record in records:
        response = answer(
            store,
            document_id,
            record.question,
            policy,
            retrieval_config=retrieval_config,
            rules=rules,
            conflict_config=conflict_config,
        )
        if response.policy.sha256 != policy.sha256:
            raise EvaluationError("a response was made with a different policy file than the one measured")
        observed = _observe(response, store, document_id, retrieval_config.k, units)
        pages_needed = {item.pdf_page for item in observed.evidence} | {span.pdf_page for span in observed.spans}
        pages = store.page_texts(document_id, sorted(pages_needed)) if pages_needed else {}
        missing = sorted(pages_needed - set(pages))
        if missing:
            raise EvaluationError(f"pages {missing} named by a response are not in the stored document")
        score = score_record(record, observed, units, pages)
        scores.append(score)
        rows.append(_row(score))

    metrics = build_metrics(scores)
    source = records[0].source
    split_value = Split(split).value
    config: dict[str, Any] = {
        "engine_version": ENGINE_VERSION,
        "split": split_value,
        "final_run": final_run,
        "source": source.value,
        "dataset_sha256": dataset.sha256,
        "policy_version": policy.version,
        "policy_calibrated": policy.calibrated,
        "policy_sha256": policy.sha256,
        "retrieval_k": retrieval_config.k,
        "retrieval_expansion_k": retrieval_config.expansion_k,
        "context_window": retrieval_config.context_window,
        "retrieval_config_sha256": _digest(retrieval_config.model_dump(mode="json")),
        "rules_fingerprint": rules.fingerprint,
        "conflict_config_sha256": _digest(conflict_config.model_dump(mode="json")),
        "cut_depths": list(RETRIEVAL_KS),
        "confidence_level": CONFIDENCE_LEVEL,
        "z": Z_95,
    }
    synthetic = source is Source.SYNTHETIC
    payload = {
        "run_id": run_id,
        "created_at": created_at,
        "engine_version": ENGINE_VERSION,
        "split": split_value,
        "final_run": final_run,
        "source": source.value,
        "synthetic": synthetic,
        "banner": SYNTHETIC_BANNER if synthetic else None,
        "dataset": {"file": dataset.file_name, "sha256": dataset.sha256, "record_count": len(records)},
        "config": config,
        "metrics": metrics,
        "records": rows,
        "limitations": list(LIMITATIONS),
    }
    output_path = write_json(target, payload)
    store.record_evaluation(
        run_id=run_id,
        created_at=created_at,
        split=split_value,
        config_json=_canonical(config),
        metrics_json=_canonical(metrics),
        dataset_sha256=dataset.sha256,
    )
    return EvaluationRun(
        run_id=run_id,
        created_at=created_at,
        split=split_value,
        final_run=final_run,
        source=source.value,
        dataset_sha256=dataset.sha256,
        record_count=len(records),
        config=config,
        metrics=metrics,
        records=tuple(rows),
        output_path=output_path,
    )

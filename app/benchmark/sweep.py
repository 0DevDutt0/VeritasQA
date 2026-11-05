"""The sweep runner (ARCHITECTURE §18; D90 to D94).

For every grid point the sweep calls ``run_evaluation`` on the development split, and then writes one summary file that
lists every point. It ranks no point, names no best point and writes no configuration file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.benchmark.baselines import measure_baselines
from app.benchmark.errors import BenchmarkError
from app.benchmark.grid import SweepGrid, SweepPoint
from app.common.files import write_json
from app.conflict.config import ConflictConfig, load_conflict_config
from app.decision import ENGINE_VERSION, load_policy
from app.decision.policy import AcceptancePolicy
from app.evaluation.gold import GoldDataset, Source, select_split
from app.evaluation.runner import RUN_ID_PATTERN, SYNTHETIC_BANNER, EvaluationRun, run_evaluation
from app.retrieval.config import RetrievalConfig, load_retrieval_config
from app.retrieval.rules import RuleSet, load_rules
from app.storage import Store

SPLIT = "dev"
SWEEP_ID_MAX_LENGTH = 60
SUMMARY_SUFFIX = "-summary.json"
RETRIEVAL_KEYS = ("mrr", "recall_at_1", "recall_at_5", "recall_at_10", "recall_at_50")
LIMITATIONS = (
    "The points are not ranked, and no point is calibrated. config/ is not written, and the policy keeps "
    "calibrated = false until P9b decides.",
    "A depth that a point did not search is None, never 0 (ARCHITECTURE §17.7).",
    "The intervals are Wilson intervals. With a few records most points tie, and the tie groups show which points "
    "cannot be told apart.",
    "The baselines measure retrieval only. TF-IDF and RRF are outside the answer path (ARCHITECTURE §18.5).",
    "If a point fails during the run, the finished points keep their rows and no summary is written "
    "(ARCHITECTURE §18.3).",
)


@dataclass(frozen=True)
class SweepResult:
    """What a sweep wrote: its id, the summary file, the summary itself and the run of each point, in grid order."""

    sweep_id: str
    summary_path: Path
    summary: dict[str, Any]
    runs: tuple[EvaluationRun, ...]


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _check_sweep_id(sweep_id: str) -> None:
    if not isinstance(sweep_id, str) or len(sweep_id) > SWEEP_ID_MAX_LENGTH or not RUN_ID_PATTERN.fullmatch(sweep_id):
        raise BenchmarkError(
            f"sweep id {sweep_id!r} must be 1 to {SWEEP_ID_MAX_LENGTH} letters, digits, dots, dashes or underscores, "
            "starting with a letter or digit, because it becomes a file name"
        )


def _run_id(sweep_id: str, point: SweepPoint) -> str:
    return f"{sweep_id}-{point.index:02d}"


def _check_before_writing(
    store: Store,
    directory: Path,
    plan: list[tuple[SweepPoint, str, RetrievalConfig]],
    summary_path: Path,
) -> None:
    """Refuse the whole sweep when any id, file or store row is already taken (ARCHITECTURE §18.3)."""
    if summary_path.exists():
        raise BenchmarkError(f"the summary {summary_path.name} already exists; choose another sweep id")
    for _, run_id, _ in plan:
        if not RUN_ID_PATTERN.fullmatch(run_id):
            raise BenchmarkError(f"run id {run_id!r} is not a plain name")
        if (directory / f"{run_id}.json").exists():
            raise BenchmarkError(f"run file {run_id}.json already exists; choose another sweep id")
        if store.read_evaluation(run_id) is not None:
            raise BenchmarkError(f"evaluation run {run_id} is already recorded; choose another sweep id")


def _point_entry(point: SweepPoint, run: EvaluationRun) -> dict[str, Any]:
    outcomes = run.metrics["outcomes"]
    retrieval = run.metrics["retrieval"]
    return {
        "index": point.index,
        "run_id": run.run_id,
        "k": point.k,
        "context_window": point.context_window,
        "heading_weight": point.heading_weight,
        "counts": outcomes["counts"],
        "rates": outcomes["rates"],
        "retrieval": {key: retrieval[key] for key in RETRIEVAL_KEYS},
    }


def _tie_groups(entries: list[dict[str, Any]]) -> list[list[int]]:
    """Points whose full results are equal, in order of first appearance (ARCHITECTURE §18.4)."""
    groups: dict[str, list[int]] = {}
    for entry in entries:
        signature = json.dumps(
            {"counts": entry["counts"], "rates": entry["rates"], "retrieval": entry["retrieval"]}, sort_keys=True
        )
        groups.setdefault(signature, []).append(entry["index"])
    return list(groups.values())


def run_sweep(
    store: Store,
    document_id: str,
    dataset: GoldDataset,
    *,
    output_dir: Path | str,
    sweep_id: str,
    grid: SweepGrid | None = None,
    created_at: str | None = None,
    policy: AcceptancePolicy | None = None,
    base_config: RetrievalConfig | None = None,
    rules: RuleSet | None = None,
    conflict_config: ConflictConfig | None = None,
) -> SweepResult:
    """Run every point of ``grid`` on the development split and write the summary (ARCHITECTURE §18).

    The checks and the baselines run before the first write. Each point is run with ``run_evaluation``, which checks the
    gold file and the store again, so a point that fails stops the sweep with its error and no summary.
    """
    _check_sweep_id(sweep_id)
    if not store.has_document(document_id):
        raise BenchmarkError(f"document {document_id} is not in the store")
    grid = grid if grid is not None else SweepGrid()
    base = base_config if base_config is not None else load_retrieval_config()
    policy = policy if policy is not None else load_policy()
    rules = rules if rules is not None else load_rules()
    conflict_config = conflict_config if conflict_config is not None else load_conflict_config()
    records = select_split(dataset, SPLIT, final_run=False)
    if not records:
        raise BenchmarkError(f"the {SPLIT} split holds no records")
    directory = Path(output_dir)
    summary_path = directory / f"{sweep_id}{SUMMARY_SUFFIX}"
    plan = [(point, _run_id(sweep_id, point), point.config(base)) for point in grid.points()]
    _check_before_writing(store, directory, plan, summary_path)
    baselines = measure_baselines(store, document_id, records, base=base)
    directory.mkdir(parents=True, exist_ok=True)
    created = created_at if created_at is not None else _now()

    runs: list[EvaluationRun] = []
    for _, run_id, config in plan:
        runs.append(
            run_evaluation(
                store,
                document_id,
                dataset,
                SPLIT,
                final_run=False,
                output_dir=directory,
                run_id=run_id,
                created_at=created,
                policy=policy,
                retrieval_config=config,
                rules=rules,
                conflict_config=conflict_config,
            )
        )

    entries = [_point_entry(point, run) for (point, _, _), run in zip(plan, runs, strict=True)]
    groups = _tie_groups(entries)
    source = records[0].source
    synthetic = source is Source.SYNTHETIC
    summary: dict[str, Any] = {
        "sweep_id": sweep_id,
        "created_at": created,
        "engine_version": ENGINE_VERSION,
        "split": SPLIT,
        "source": source.value,
        "synthetic": synthetic,
        "banner": SYNTHETIC_BANNER if synthetic else None,
        "dataset": {
            "file": dataset.file_name,
            "sha256": dataset.sha256,
            "total_records": len(dataset.records),
            "dev_records": len(records),
        },
        "grid": {
            "k_values": list(grid.k_values),
            "context_windows": list(grid.context_windows),
            "heading_weights": list(grid.heading_weights),
        },
        "points": entries,
        "distinct_results": len(groups),
        "tie_groups": groups,
        "baselines": baselines,
        "limitations": list(LIMITATIONS),
    }
    write_json(summary_path, summary)
    return SweepResult(sweep_id=sweep_id, summary_path=summary_path, summary=summary, runs=tuple(runs))

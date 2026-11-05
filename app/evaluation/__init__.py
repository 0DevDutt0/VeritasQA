"""Evaluation harness: gold records, metrics and the run record (SPEC §11, §12; ARCHITECTURE §17).

Scores the decision step's responses against hand-checked gold records. Every number it reports carries its count,
and no rate is reported over an empty set (ARCHITECTURE §17.9).
"""

from app.evaluation.errors import EvaluationError, GoldError
from app.evaluation.gold import (
    Category,
    GoldAnswer,
    GoldDataset,
    GoldEvidence,
    GoldRecord,
    Source,
    Split,
    check_against_store,
    load_gold,
    select_split,
)
from app.evaluation.runner import EvaluationRun, run_evaluation

__all__ = [
    "Category",
    "EvaluationError",
    "EvaluationRun",
    "GoldAnswer",
    "GoldDataset",
    "GoldError",
    "GoldEvidence",
    "GoldRecord",
    "Source",
    "Split",
    "check_against_store",
    "load_gold",
    "run_evaluation",
    "select_split",
]

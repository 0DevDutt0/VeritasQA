"""Benchmark and sweep harness (ARCHITECTURE §18). Benchmark-only: no module on the answer path imports this package.

The sweep runs the harness of ``app.evaluation`` once per grid point on the development split. The baselines (BM25 as
the engine ranks it, TF-IDF and Reciprocal Rank Fusion) are retrieval measures only.
"""

from app.benchmark.baselines import ARMS, BASELINE_DEPTH, RRF_CONSTANT, measure_baselines
from app.benchmark.errors import BenchmarkError
from app.benchmark.grid import SweepGrid, SweepPoint
from app.benchmark.sweep import SweepResult, run_sweep

__all__ = [
    "ARMS",
    "BASELINE_DEPTH",
    "RRF_CONSTANT",
    "BenchmarkError",
    "SweepGrid",
    "SweepPoint",
    "SweepResult",
    "measure_baselines",
    "run_sweep",
]

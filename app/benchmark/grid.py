"""The sweep grid and its points (ARCHITECTURE §18.2, D91).

The grid names the three swept values of the P9a phase: K, the context window and the heading weight. None of its
values is calibrated. A sweep reports every point, and nothing here chooses one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.retrieval.config import RetrievalConfig

DEFAULT_K_VALUES: tuple[int, ...] = (1, 5, 10, 50)
DEFAULT_CONTEXT_WINDOWS: tuple[int, ...] = (0, 1, 2)
DEFAULT_HEADING_WEIGHTS: tuple[float, ...] = (1.0, 2.0, 4.0)
# A run id holds a two-digit point number (ARCHITECTURE §18.3), so a grid can hold at most 99 points.
MAX_POINTS = 99

KValue = Annotated[int, Field(ge=1)]
WindowValue = Annotated[int, Field(ge=0)]
WeightValue = Annotated[float, Field(gt=0)]


@dataclass(frozen=True)
class SweepPoint:
    """One grid point. ``index`` is 1-based and names the point's run (ARCHITECTURE §18.3)."""

    index: int
    k: int
    context_window: int
    heading_weight: float

    def config(self, base: RetrievalConfig) -> RetrievalConfig:
        """The retrieval configuration of this point: the three swept values, with the rest taken from ``base``.

        The configuration is constructed, so every value is validated. ``model_copy`` is not used (ARCHITECTURE §18.2).
        """
        return RetrievalConfig(
            k=self.k,
            expansion_k=base.expansion_k,
            weight_index=base.weight_index,
            weight_heading=self.heading_weight,
            context_window=self.context_window,
        )


class SweepGrid(BaseModel):
    """The three swept values. Each is a tuple of distinct values, and the grid holds at most ``MAX_POINTS`` points."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    k_values: tuple[KValue, ...] = DEFAULT_K_VALUES
    context_windows: tuple[WindowValue, ...] = DEFAULT_CONTEXT_WINDOWS
    heading_weights: tuple[WeightValue, ...] = DEFAULT_HEADING_WEIGHTS

    @model_validator(mode="after")
    def _distinct_and_bounded(self) -> SweepGrid:
        for name in ("k_values", "context_windows", "heading_weights"):
            values = getattr(self, name)
            if not values:
                raise ValueError(f"{name} must hold at least one value")
            if len(set(values)) != len(values):
                raise ValueError(f"{name} must not repeat a value")
        size = len(self.k_values) * len(self.context_windows) * len(self.heading_weights)
        if size > MAX_POINTS:
            raise ValueError(f"the grid has {size} points; at most {MAX_POINTS} are allowed")
        return self

    def points(self) -> tuple[SweepPoint, ...]:
        """All points, numbered from 1 in the order K, then context window, then heading weight."""
        combinations = [
            (k, window, weight)
            for k in self.k_values
            for window in self.context_windows
            for weight in self.heading_weights
        ]
        return tuple(
            SweepPoint(index=index, k=k, context_window=window, heading_weight=weight)
            for index, (k, window, weight) in enumerate(combinations, start=1)
        )

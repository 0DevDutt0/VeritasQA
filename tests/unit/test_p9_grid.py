"""P9a grid: the 36 default points, their order, their configurations and the refusals (ARCHITECTURE §18.2, D91)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.benchmark import SweepGrid
from app.benchmark.grid import MAX_POINTS, SweepPoint
from app.retrieval.config import RetrievalConfig, load_retrieval_config


def test_the_default_grid_has_36_points_in_k_window_heading_order():
    points = SweepGrid().points()
    assert len(points) == 36
    assert [point.index for point in points] == list(range(1, 37))
    assert (points[0].k, points[0].context_window, points[0].heading_weight) == (1, 0, 1.0)
    assert (points[1].k, points[1].context_window, points[1].heading_weight) == (1, 0, 2.0)
    assert (points[3].k, points[3].context_window, points[3].heading_weight) == (1, 1, 1.0)
    assert (points[-1].k, points[-1].context_window, points[-1].heading_weight) == (50, 2, 4.0)


def test_the_defaults_include_the_configured_values():
    base = load_retrieval_config()
    grid = SweepGrid()
    assert base.k in grid.k_values
    assert base.context_window in grid.context_windows
    assert base.weight_heading in grid.heading_weights


def test_each_point_builds_a_validated_configuration_from_the_base():
    base = load_retrieval_config()
    config = SweepPoint(index=5, k=10, context_window=2, heading_weight=4.0).config(base)
    assert isinstance(config, RetrievalConfig)
    assert (config.k, config.context_window, config.weight_heading) == (10, 2, 4.0)
    assert config.expansion_k == base.expansion_k
    assert config.weight_index == base.weight_index


def test_a_grid_of_exactly_the_largest_allowed_size_is_accepted():
    heading_weights = tuple(float(number) for number in range(1, MAX_POINTS + 1))
    grid = SweepGrid(k_values=(1,), context_windows=(0,), heading_weights=heading_weights)
    assert len(grid.points()) == MAX_POINTS


@pytest.mark.parametrize(
    "kwargs",
    [
        {"k_values": ()},
        {"k_values": (5, 5)},
        {"k_values": (0,)},
        {"context_windows": (-1,)},
        {"context_windows": (1, 1)},
        {"heading_weights": (0.0,)},
        {"heading_weights": (2.0, 2.0)},
        {"unknown": 1},
    ],
)
def test_the_grid_refuses_invalid_values(kwargs):
    with pytest.raises(ValidationError):
        SweepGrid(**kwargs)


def test_the_grid_refuses_more_points_than_a_two_digit_run_number_allows():
    with pytest.raises(ValidationError):
        SweepGrid(
            k_values=tuple(range(1, 11)),
            context_windows=(0, 1, 2),
            heading_weights=(1.0, 2.0, 4.0, 8.0),
        )

"""Conflict screening (SPEC §8; ARCHITECTURE §16.2-§16.3).

``screen_component`` reports every difference between the claims of one question component across the document. It
never resolves a difference: the decision step (``app.decision``) turns the impacts into a status.
"""

from app.conflict.config import ConflictConfig, load_conflict_config
from app.conflict.detector import (
    ConflictRelation,
    ConflictScreen,
    Impact,
    Piece,
    Relation,
    ScreenCounts,
    screen_component,
)
from app.conflict.errors import ConflictConfigError

__all__ = [
    "ConflictConfig",
    "ConflictConfigError",
    "ConflictRelation",
    "ConflictScreen",
    "Impact",
    "Piece",
    "Relation",
    "ScreenCounts",
    "load_conflict_config",
    "screen_component",
]

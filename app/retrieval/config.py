"""Retrieval configuration: the [retrieval] section of config/retrieval.toml, validated with Pydantic.

Nothing is read at import time. The file is read only when a caller asks for it, and a caller can pass
any value per call instead (ARCHITECTURE §13).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.retrieval.errors import RetrievalConfigError

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "retrieval.toml"


class RetrievalConfig(BaseModel):
    """Defaults for the search. Every field is required in the TOML file. Each value is uncalibrated (P9a)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    k: int = Field(ge=1)
    expansion_k: int = Field(ge=0)
    weight_index: float = Field(gt=0)
    weight_heading: float = Field(gt=0)
    context_window: int = Field(ge=0)


def load_retrieval_config(path: Path | str | None = None) -> RetrievalConfig:
    """Read and validate the [retrieval] section. Defaults to ``config/retrieval.toml``."""
    target = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    try:
        with target.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise RetrievalConfigError(f"configuration file not found: {target.name}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise RetrievalConfigError(f"configuration file is not valid TOML: {target.name}: {exc}") from exc
    section = data.get("retrieval")
    if not isinstance(section, dict):
        raise RetrievalConfigError(f"{target.name} has no [retrieval] section")
    try:
        return RetrievalConfig.model_validate(section)
    except ValidationError as exc:
        raise RetrievalConfigError(f"invalid [retrieval] configuration in {target.name}: {exc}") from exc

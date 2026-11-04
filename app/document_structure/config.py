"""Structure configuration: the [structure] section of config/structure.toml, validated with Pydantic.

Nothing is read at import time. The file is read only when a caller asks for it.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.document_structure.errors import StructureConfigError

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "structure.toml"


class StructureConfig(BaseModel):
    """Thresholds for structure segmentation. Every field is required in the TOML file."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    line_size_quantum: float = Field(gt=0)
    body_stat_min_chars: int = Field(ge=1)
    heading_size_delta: float = Field(gt=0)
    heading_max_chars: int = Field(ge=1)
    heading_level_min_count: int = Field(ge=1)
    paragraph_gap_factor: float = Field(ge=0)
    short_line_fraction: float = Field(gt=0, le=1)
    footnote_size_delta: float = Field(gt=0)
    footnote_band_fraction: float = Field(gt=0, lt=1)
    furniture_band_fraction: float = Field(gt=0, lt=0.5)
    table_cell_tolerance: float = Field(ge=0)
    table_min_claim_share: float = Field(ge=0, le=1)


def load_structure_config(path: Path | str | None = None) -> StructureConfig:
    """Read and validate the [structure] section. Defaults to ``config/structure.toml``."""
    target = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    try:
        with target.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise StructureConfigError(f"configuration file not found: {target.name}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise StructureConfigError(f"configuration file is not valid TOML: {target.name}: {exc}") from exc
    section = data.get("structure")
    if not isinstance(section, dict):
        raise StructureConfigError(f"{target.name} has no [structure] section")
    try:
        return StructureConfig.model_validate(section)
    except ValidationError as exc:
        raise StructureConfigError(f"invalid [structure] configuration in {target.name}: {exc}") from exc

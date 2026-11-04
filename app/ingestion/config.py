"""Ingestion configuration: the [ingestion] section of config/default.toml, validated with Pydantic.

Nothing is read at import time. The file is read only when a caller asks for the configuration.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.ingestion.errors import IngestionConfigError

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "default.toml"

_LANGUAGE_PATTERN = r"^[A-Za-z0-9_+]+$"


class IngestionConfig(BaseModel):
    """Thresholds and switches for ingestion. Every field is required in the TOML file."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_file_bytes: int = Field(gt=0)
    eof_tail_bytes: int = Field(gt=0)
    blank_check_dpi: int = Field(gt=0)
    blank_ink_ratio_max: float = Field(ge=0, le=1)
    scanned_image_coverage_min: float = Field(gt=0, le=1)
    hidden_text_share_max: float = Field(ge=0, le=1)
    garbled_char_ratio_max: float = Field(ge=0, le=1)
    suspicious_min_non_space_chars: int = Field(ge=1)
    suspicious_letter_ratio_min: float = Field(ge=0, le=1)
    suspicious_min_tokens: int = Field(ge=1)
    suspicious_single_letter_token_ratio_max: float = Field(ge=0, le=1)
    header_footer_band_fraction: float = Field(gt=0, lt=0.5)
    header_footer_min_pages: int = Field(ge=2)
    wide_block_width_fraction: float = Field(gt=0, le=1)
    min_gutter_fraction: float = Field(ge=0, lt=1)
    overlap_area_fraction_max: float = Field(ge=0, le=1)
    line_gap_em: float = Field(ge=0)
    render_dpi: int = Field(gt=0)
    ocr_mode: Literal["auto", "off"]
    ocr_language: str = Field(pattern=_LANGUAGE_PATTERN)
    ocr_dpi: int = Field(gt=0)
    ocr_timeout_seconds: float = Field(gt=0)


def load_ingestion_config(path: Path | str | None = None) -> IngestionConfig:
    """Read and validate the [ingestion] section. Defaults to ``config/default.toml``."""
    target = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    try:
        with target.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise IngestionConfigError(f"configuration file not found: {target.name}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise IngestionConfigError(f"configuration file is not valid TOML: {target.name}: {exc}") from exc
    section = data.get("ingestion")
    if not isinstance(section, dict):
        raise IngestionConfigError(f"{target.name} has no [ingestion] section")
    try:
        return IngestionConfig.model_validate(section)
    except ValidationError as exc:
        raise IngestionConfigError(f"invalid [ingestion] configuration in {target.name}: {exc}") from exc


def config_fingerprint(config: IngestionConfig) -> str:
    """SHA-256 of the canonical JSON form of the configuration. Recorded in every report."""
    canonical = json.dumps(config.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

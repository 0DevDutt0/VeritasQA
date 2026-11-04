"""Conflict configuration: measure families and supersession phrases (config/conflict.toml; ARCHITECTURE §16.2, §16.3).

Nothing is read at import time. The file is read when a caller asks for it, and every entry is validated then. An
unknown key, a unit listed in two families, or an empty phrase is an error, not a silent default.
"""

from __future__ import annotations

import re
import tomllib
import unicodedata
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from app.conflict.errors import ConflictConfigError

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "conflict.toml"
_SECTIONS = frozenset({"measures", "supersession"})


def normalize_unit(label: str) -> str:
    """The lookup form of a unit label: NFKC, case folded, and a plural reduced to its singular (days -> day)."""
    folded = unicodedata.normalize("NFKC", label).casefold().strip()
    if len(folded) > 2 and folded.endswith("s") and not folded.endswith("ss"):
        return folded[:-1]
    return folded


def normalize_phrase(phrase: str) -> str:
    """A supersession phrase in lookup form: case folded, with single spaces between its words."""
    return " ".join(unicodedata.normalize("NFKC", phrase).casefold().split())


class ConflictConfig(BaseModel):
    """The validated configuration. ``measures`` maps each family to its normalized unit labels."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    measures: dict[str, tuple[str, ...]]
    supersession_phrases: tuple[str, ...]

    @field_validator("measures")
    @classmethod
    def _each_unit_in_one_family(cls, value: dict[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
        owner: dict[str, str] = {}
        for family, units in value.items():
            if not family.isidentifier():
                raise ValueError(f"measure family name {family!r} must be a plain identifier")
            if not units:
                raise ValueError(f"measure family {family!r} lists no units")
            for unit in units:
                if unit in owner:
                    raise ValueError(f"unit {unit!r} is listed in both {owner[unit]!r} and {family!r}")
                owner[unit] = family
        return value

    @field_validator("supersession_phrases")
    @classmethod
    def _phrases_distinct(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("at least one supersession phrase is required")
        if any(not phrase for phrase in value):
            raise ValueError("a supersession phrase must not be empty")
        if len(set(value)) != len(value):
            raise ValueError("a supersession phrase is listed twice")
        return value


def load_conflict_config(path: Path | str | None = None) -> ConflictConfig:
    """Read and validate ``config/conflict.toml`` (or ``path``). Raises :class:`ConflictConfigError`."""
    target = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    try:
        with target.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ConflictConfigError(f"configuration file not found: {target.name}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConflictConfigError(f"configuration file is not valid TOML: {target.name}: {exc}") from exc
    unexpected = set(data) - _SECTIONS
    if unexpected:
        raise ConflictConfigError(f"{target.name} has unknown sections: {sorted(unexpected)}")
    measures = data.get("measures")
    supersession = data.get("supersession")
    if not isinstance(measures, dict) or not isinstance(supersession, dict):
        raise ConflictConfigError(f"{target.name} needs a [measures] and a [supersession] section")
    phrases = supersession.get("phrases")
    if not isinstance(phrases, list) or not all(isinstance(phrase, str) for phrase in phrases):
        raise ConflictConfigError(f"{target.name}: [supersession] phrases must be a list of text")
    families: dict[str, tuple[str, ...]] = {}
    for family, units in measures.items():
        if not isinstance(units, list) or not all(isinstance(unit, str) for unit in units):
            raise ConflictConfigError(f"{target.name}: measure family {family!r} must be a list of text")
        families[family] = tuple(normalize_unit(unit) for unit in units)
    try:
        return ConflictConfig(
            measures=families,
            supersession_phrases=tuple(normalize_phrase(phrase) for phrase in phrases),
        )
    except ValidationError as exc:
        raise ConflictConfigError(f"invalid conflict configuration in {target.name}: {exc}") from exc


def family_of(config: ConflictConfig, unit: str) -> str | None:
    """The measure family of a normalized unit label, or ``None`` when the unit is not listed."""
    for family, units in config.measures.items():
        if unit in units:
            return family
    return None


@lru_cache(maxsize=32)
def supersession_pattern(phrases: tuple[str, ...]) -> re.Pattern[str]:
    """One pattern for all phrases. Whole words only, and any run of whitespace between the words."""
    alternatives = [r"\s+".join(re.escape(word) for word in phrase.split()) for phrase in phrases]
    return re.compile(r"(?<![^\W_])(?:" + "|".join(alternatives) + r")(?![^\W_])")

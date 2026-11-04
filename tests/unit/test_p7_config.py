"""Conflict configuration: the strict loader, the unit families and the supersession pattern (ARCHITECTURE §16.2-§16.3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.conflict.config import (
    DEFAULT_CONFIG_PATH,
    family_of,
    load_conflict_config,
    normalize_phrase,
    normalize_unit,
    supersession_pattern,
)
from app.conflict.errors import ConflictConfigError


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "conflict.toml"
    path.write_text(text, encoding="utf-8")
    return path


GOOD = """
[measures]
time = ["day", "month"]
money = ["usd"]

[supersession]
phrases = ["replaced by", "supersedes"]
"""


def test_the_default_file_loads_with_its_families_and_phrases():
    config = load_conflict_config()
    assert DEFAULT_CONFIG_PATH.name == "conflict.toml"
    assert {"time", "money", "percent", "length", "mass", "volume", "data"} <= set(config.measures)
    assert "supersedes" in config.supersession_phrases
    assert all(phrase == phrase.casefold() for phrase in config.supersession_phrases)


def test_a_good_file_loads_and_units_are_normalized(tmp_path):
    config = load_conflict_config(_write(tmp_path, GOOD.replace('"day"', '"Days"')))
    assert config.measures["time"] == ("day", "month")
    assert family_of(config, normalize_unit("DAYS")) == "time"
    assert family_of(config, "furlong") is None


@pytest.mark.parametrize(
    "text, message",
    [
        (GOOD + "\n[extra]\nx = 1\n", "unknown sections"),
        (GOOD.replace('money = ["usd"]', 'money = ["day"]'), "both"),
        (GOOD.replace('phrases = ["replaced by", "supersedes"]', 'phrases = []'), "at least one"),
        (GOOD.replace('phrases = ["replaced by", "supersedes"]', 'phrases = ["supersedes", "SUPERSEDES"]'), "twice"),
        (GOOD.replace('phrases = ["replaced by", "supersedes"]', 'phrases = [""]'), "empty"),
        (GOOD.replace('money = ["usd"]', 'money = []'), "lists no units"),
        (GOOD.replace('time = ["day", "month"]', 'time = "day"'), "list of text"),
        ("[measures]\ntime = [\"day\"]\n", "needs a"),
        ("this is not toml = [", "not valid TOML"),
    ],
)
def test_a_bad_file_is_refused_with_a_reason(tmp_path, text, message):
    with pytest.raises(ConflictConfigError, match=message):
        load_conflict_config(_write(tmp_path, text))


def test_a_missing_file_is_refused(tmp_path):
    with pytest.raises(ConflictConfigError, match="not found"):
        load_conflict_config(tmp_path / "absent.toml")


def test_normalize_unit_folds_case_and_reduces_plurals():
    assert normalize_unit("Days") == "day"
    assert normalize_unit("lbs") == "lb"
    assert normalize_unit("class") == "class"
    assert normalize_unit("%") == "%"
    assert normalize_unit("USD") == "usd"


def test_normalize_phrase_collapses_spaces_and_case():
    assert normalize_phrase("  Replaced\n  BY ") == "replaced by"


@pytest.mark.parametrize(
    "text, phrase, found",
    [
        ("This standard supersedes the 2015 edition.", "supersedes", True),
        ("The fee is replaced by a new fee.", "replaced by", True),
        ("The fee was REPLACED   BY a new fee.", "replaced by", True),
        ("Its limit is replaced\nby 45 days.", "replaced by", True),
        ("The replacements are listed.", "replaced by", False),
        ("The replacements are listed.", "replaces", False),
        ("The fee replaces the old one.", "replaces", True),
        ("It is superseded by the guide.", "superseded by", True),
        ("The supersedesX token is not a phrase.", "supersedes", False),
        ("Staff may share the guide.", "supersedes", False),
    ],
)
def test_the_supersession_pattern_matches_whole_phrases_only(text, phrase, found):
    pattern = supersession_pattern((phrase,))
    assert (pattern.search(text.casefold()) is not None) is found

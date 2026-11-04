"""P2 configuration (config/structure.toml): loads, is immutable, and rejects unknown or missing input.

Run: pytest tests/unit/test_p2_config.py -q
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.document_structure.config import DEFAULT_CONFIG_PATH, load_structure_config
from app.document_structure.errors import StructureConfigError


def _default_text() -> str:
    return DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")


def test_default_config_loads_documented_values():
    config = load_structure_config()
    assert config.line_size_quantum == 0.5
    assert config.heading_level_min_count == 2
    assert config.paragraph_gap_factor == 1.0
    assert config.table_min_claim_share == 0.5


def test_config_is_immutable():
    config = load_structure_config()
    with pytest.raises(ValidationError):
        config.heading_size_delta = 5.0


def test_unknown_key_is_rejected(tmp_path):
    path = tmp_path / "structure.toml"
    path.write_text(_default_text() + "\nbogus_key = 1\n", encoding="utf-8")
    with pytest.raises(StructureConfigError, match="bogus_key"):
        load_structure_config(path)


def test_out_of_range_value_is_rejected(tmp_path):
    path = tmp_path / "structure.toml"
    path.write_text(_default_text().replace("table_min_claim_share = 0.5", "table_min_claim_share = 1.5"), encoding="utf-8")
    with pytest.raises(StructureConfigError, match="table_min_claim_share"):
        load_structure_config(path)


def test_missing_section_is_rejected(tmp_path):
    path = tmp_path / "structure.toml"
    path.write_text("[other]\nvalue = 1\n", encoding="utf-8")
    with pytest.raises(StructureConfigError, match=r"\[structure\]"):
        load_structure_config(path)


def test_invalid_toml_is_rejected(tmp_path):
    path = tmp_path / "structure.toml"
    path.write_text("[structure\n", encoding="utf-8")
    with pytest.raises(StructureConfigError, match="not valid TOML"):
        load_structure_config(path)

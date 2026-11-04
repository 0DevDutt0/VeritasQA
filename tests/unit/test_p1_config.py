"""P1 exit criteria (configuration): the ingestion settings load from config/default.toml and reject bad input.

Run:  pytest tests/unit/test_p1_config.py -q
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.ingestion.config import DEFAULT_CONFIG_PATH, config_fingerprint, load_ingestion_config
from app.ingestion.errors import IngestionConfigError


def _default_text() -> str:
    return DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")


def test_default_config_loads_documented_values():
    config = load_ingestion_config()
    assert config.max_file_bytes == 268435456
    assert config.ocr_mode == "auto"
    assert config.line_gap_em == 1.0
    assert config.header_footer_min_pages == 2
    assert config.hidden_text_share_max == 0.02


def test_config_is_immutable_after_loading():
    config = load_ingestion_config()
    with pytest.raises(ValidationError):
        config.render_dpi = 1


def test_unknown_key_is_rejected(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(_default_text() + "\nbogus_key = 1\n", encoding="utf-8")
    with pytest.raises(IngestionConfigError, match="bogus_key"):
        load_ingestion_config(path)


def test_missing_section_is_reported(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[other]\nvalue = 1\n", encoding="utf-8")
    with pytest.raises(IngestionConfigError, match=r"\[ingestion\]"):
        load_ingestion_config(path)


def test_out_of_range_ratio_is_rejected(tmp_path):
    path = tmp_path / "config.toml"
    text = _default_text().replace("blank_ink_ratio_max = 0.0005", "blank_ink_ratio_max = 2.0")
    assert text != _default_text()
    path.write_text(text, encoding="utf-8")
    with pytest.raises(IngestionConfigError, match="blank_ink_ratio_max"):
        load_ingestion_config(path)


def test_ocr_language_is_limited_to_plain_codes(tmp_path):
    path = tmp_path / "config.toml"
    text = _default_text().replace('ocr_language = "eng"', 'ocr_language = "eng; rm -rf"')
    assert text != _default_text()
    path.write_text(text, encoding="utf-8")
    with pytest.raises(IngestionConfigError, match="ocr_language"):
        load_ingestion_config(path)


def test_missing_file_is_reported(tmp_path):
    with pytest.raises(IngestionConfigError, match="not found"):
        load_ingestion_config(tmp_path / "absent.toml")


def test_invalid_toml_is_reported(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[ingestion\nbroken = ", encoding="utf-8")
    with pytest.raises(IngestionConfigError, match="not valid TOML"):
        load_ingestion_config(path)


def test_fingerprint_is_stable_and_changes_with_any_value():
    config = load_ingestion_config()
    assert config_fingerprint(config) == config_fingerprint(load_ingestion_config())
    changed = config.model_copy(update={"render_dpi": config.render_dpi + 1})
    assert config_fingerprint(config) != config_fingerprint(changed)

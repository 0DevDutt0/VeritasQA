"""P4 configuration: config/retrieval.toml is read and validated, and unknown keys are rejected."""

from __future__ import annotations

import pytest

from app.retrieval import RetrievalConfigError, load_retrieval_config
from app.retrieval.config import DEFAULT_CONFIG_PATH

VALID = """
[retrieval]
k = 20
expansion_k = 0
weight_index = 1.5
weight_heading = 3.0
context_window = 2
"""


def _write(tmp_path, body: str):
    path = tmp_path / "retrieval.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_the_shipped_defaults_load():
    config = load_retrieval_config()
    assert DEFAULT_CONFIG_PATH.name == "retrieval.toml"
    assert (config.k, config.expansion_k, config.weight_index, config.weight_heading, config.context_window) == (
        50,
        10,
        1.0,
        2.0,
        1,
    )


def test_valid_values_load(tmp_path):
    config = load_retrieval_config(_write(tmp_path, VALID))
    assert (config.k, config.expansion_k, config.weight_index, config.weight_heading, config.context_window) == (
        20,
        0,
        1.5,
        3.0,
        2,
    )


@pytest.mark.parametrize(
    "body",
    [
        VALID.replace("k = 20", "k = 0"),
        VALID.replace("expansion_k = 0", "expansion_k = -1"),
        VALID.replace("context_window = 2", "context_window = -1"),
        VALID.replace("weight_heading = 3.0", "weight_heading = 0"),
        VALID.replace("weight_index = 1.5", "weight_index = -2"),
        VALID.replace("k = 20", "k = 'many'"),
        VALID + "\nunexpected = 1\n",
    ],
)
def test_invalid_or_unknown_values_are_refused(tmp_path, body):
    with pytest.raises(RetrievalConfigError):
        load_retrieval_config(_write(tmp_path, body))


def test_a_missing_section_is_refused(tmp_path):
    with pytest.raises(RetrievalConfigError, match=r"no \[retrieval\] section"):
        load_retrieval_config(_write(tmp_path, "[other]\nk = 1\n"))


def test_a_missing_field_is_refused(tmp_path):
    with pytest.raises(RetrievalConfigError):
        load_retrieval_config(_write(tmp_path, "[retrieval]\nk = 5\n"))


def test_a_missing_file_is_refused(tmp_path):
    with pytest.raises(RetrievalConfigError, match="not found"):
        load_retrieval_config(tmp_path / "absent.toml")


def test_invalid_toml_is_refused(tmp_path):
    with pytest.raises(RetrievalConfigError, match="not valid TOML"):
        load_retrieval_config(_write(tmp_path, "[retrieval\nk = 1"))

"""P10: the command-line parser, its defaults and its error output (ARCHITECTURE §19.1 to §19.5).

No store is opened by these tests. The guards are checked before any file is created.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.api.cli import DEFAULT_EXTRACTED_ROOT, DEFAULT_RUN_DIR, REPO_ROOT, build_parser, main

GOLD = Path(__file__).resolve().parents[1] / "fixtures" / "p8_synthetic_gold.jsonl"


def test_help_lists_the_four_commands(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    text = capsys.readouterr().out
    for command in ("ingest", "ask", "report", "evaluate"):
        assert command in text


def test_a_missing_required_option_is_a_usage_error_with_exit_code_2():
    with pytest.raises(SystemExit) as exc:
        main(["ask", "--document-id", "doc-x", "What is the limit?"])  # no --store
    assert exc.value.code == 2


def test_the_split_must_be_dev_or_heldout():
    with pytest.raises(SystemExit) as exc:
        main(["evaluate", "--store", "s.sqlite", "--document-id", "d", "--gold", "g.jsonl", "--split", "test"])
    assert exc.value.code == 2


def test_defaults_are_anchored_to_the_repository_not_the_working_directory():
    ingest = build_parser().parse_args(["ingest", "paper.pdf", "--store", "s.sqlite"])
    assert ingest.extracted_root == DEFAULT_EXTRACTED_ROOT == REPO_ROOT / "data" / "extracted"
    evaluate = build_parser().parse_args(
        ["evaluate", "--store", "s.sqlite", "--document-id", "d", "--gold", "g.jsonl", "--split", "dev"]
    )
    assert evaluate.output_dir == DEFAULT_RUN_DIR == REPO_ROOT / "data" / "evaluations" / "runs"
    assert evaluate.final_run is False


def test_a_held_out_run_without_the_final_flag_is_refused_and_no_store_is_created(tmp_path, capsys):
    store = tmp_path / "absent.sqlite"
    code = main(
        ["evaluate", "--store", str(store), "--document-id", "doc-x", "--gold", str(GOLD), "--split", "heldout"]
    )
    assert code == 1
    assert not store.exists()
    error = json.loads(capsys.readouterr().err)["error"]
    assert "--final-run" in error["message"]


def test_the_final_flag_is_refused_on_the_development_split(tmp_path, capsys):
    store = tmp_path / "absent.sqlite"
    code = main(
        [
            "evaluate",
            "--store",
            str(store),
            "--document-id",
            "doc-x",
            "--gold",
            str(GOLD),
            "--split",
            "dev",
            "--final-run",
        ]
    )
    assert code == 1
    assert not store.exists()
    assert "--final-run" in json.loads(capsys.readouterr().err)["error"]["message"]


@pytest.mark.parametrize(
    "command",
    [
        ["ask", "--document-id", "doc-x", "What is the limit?"],
        ["report"],
        ["evaluate", "--document-id", "doc-x", "--gold", str(GOLD), "--split", "dev"],
    ],
)
def test_read_commands_refuse_a_store_that_does_not_exist(tmp_path, capsys, command):
    store = tmp_path / "absent.sqlite"
    code = main([command[0], "--store", str(store), *command[1:]])
    assert code == 1
    assert not store.exists(), "Store.open would create an empty file, so the CLI must check first"
    message = json.loads(capsys.readouterr().err)["error"]["message"]
    assert "store" in message and "ingest" in message


def test_an_error_is_one_json_object_on_standard_error_and_nothing_on_standard_output(tmp_path, capsys):
    code = main(["report", "--store", str(tmp_path / "absent.sqlite")])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    error = json.loads(captured.err)
    assert set(error) == {"error"}
    assert set(error["error"]) == {"type", "message"}

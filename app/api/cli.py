"""The VeritasQA command line: ingest, ask, report, evaluate and compare (ARCHITECTURE §19, §20).

Each command writes exactly one JSON object to standard output. A failure writes one JSON object to standard error and
returns exit code 1. A usage error returns argparse's exit code 2. Paths default to the repository root, not to the
working directory.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any, TextIO

from app.api.errors import CliError
from app.common.errors import VeritasQAError
from app.comparison import (
    DocumentComparison,
    DocumentInfo,
    PageRecord,
    Selection,
    compare_documents,
    render_report,
    select_earlier,
)
from app.decision import answer
from app.document_structure import build_structure
from app.evaluation import load_gold, run_evaluation
from app.ingestion.extract import extract_document
from app.ingestion.report import REPORT_NAME
from app.storage import Store
from app.storage.store import DocumentRecord

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXTRACTED_ROOT = REPO_ROOT / "data" / "extracted"
DEFAULT_RUN_DIR = REPO_ROOT / "data" / "evaluations" / "runs"
DEFAULT_REPORT_DIR = REPO_ROOT / "data" / "reports"
SPLITS = ("dev", "heldout")

Handler = Callable[[argparse.Namespace], dict[str, Any]]


def _write(stream: TextIO, text: str) -> None:
    """Write UTF-8 whatever the console code page is, so a redirected file is valid JSON."""
    stream.flush()
    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        buffer.write(text.encode("utf-8"))
        buffer.flush()
    else:
        stream.write(text)
        stream.flush()


def _emit(payload: dict[str, Any]) -> None:
    _write(sys.stdout, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _emit_error(exc: BaseException) -> None:
    body = {"error": {"type": type(exc).__name__, "message": str(exc)}}
    _write(sys.stderr, json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.api",
        description="VeritasQA command line. Each command writes one JSON object to standard output (ARCHITECTURE §19).",
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")

    ingest = commands.add_parser("ingest", help="extract, structure and store one PDF")
    ingest.add_argument("pdf", type=Path, help="the PDF file to ingest")
    ingest.add_argument("--store", type=Path, required=True, help="the SQLite store (created when missing)")
    ingest.add_argument(
        "--extracted-root",
        type=Path,
        default=DEFAULT_EXTRACTED_ROOT,
        help="where the extraction outputs are written (default: data/extracted)",
    )
    ingest.add_argument(
        "--against",
        help="the earlier version to compare with, by document id (default: the one stored with the same file name)",
    )
    ingest.add_argument(
        "--report-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
        help="where the comparison report is written (default: data/reports)",
    )
    ingest.set_defaults(handler=_ingest)

    compare = commands.add_parser("compare", help="compare two documents already in the store, page by page (no ingest)")
    compare.add_argument("--store", type=Path, required=True, help="the SQLite store")
    compare.add_argument("--document-id", required=True, help="the newer document")
    compare.add_argument("--against", help="the earlier document (default: the one stored with the same file name)")
    compare.add_argument(
        "--report-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
        help="where the comparison report is written (default: data/reports)",
    )
    compare.set_defaults(handler=_compare)

    ask = commands.add_parser("ask", help="answer one question about one stored document")
    ask.add_argument("--store", type=Path, required=True, help="the SQLite store")
    ask.add_argument("--document-id", required=True, help="the document to search")
    ask.add_argument("question", help="the question, in quotation marks")
    ask.set_defaults(handler=_ask)

    report = commands.add_parser("report", help="list the stored documents, or describe one (read only)")
    report.add_argument("--store", type=Path, required=True, help="the SQLite store")
    report.add_argument("--document-id", help="describe this document; without it, list every document")
    report.set_defaults(handler=_report)

    evaluate = commands.add_parser("evaluate", help="run one split of a gold file against one stored document")
    evaluate.add_argument("--store", type=Path, required=True, help="the SQLite store")
    evaluate.add_argument("--document-id", required=True, help="the document the gold file describes")
    evaluate.add_argument("--gold", type=Path, required=True, help="the gold file (JSON Lines)")
    evaluate.add_argument("--split", choices=SPLITS, required=True)
    evaluate.add_argument(
        "--final-run", action="store_true", help="required for --split heldout: the one final run (D84)"
    )
    evaluate.add_argument(
        "--output-dir", type=Path, default=DEFAULT_RUN_DIR, help="where the run file is written (default: data/evaluations/runs)"
    )
    evaluate.add_argument("--run-id", help="a plain file name for the run; generated when omitted")
    evaluate.set_defaults(handler=_evaluate)
    return parser


def _open_store(path: Path) -> Store:
    """Open a store that must already exist. ``Store.open`` would otherwise create an empty file (ARCHITECTURE §19.5)."""
    if not path.is_file():
        raise CliError(f"store file not found: {path}. Run ingest first, or check the path.")
    return Store.open(path)


def _require_document(store: Store, document_id: str, path: Path) -> None:
    if not store.has_document(document_id):
        raise CliError(f"document {document_id} is not in the store {path}. Run report to list the documents.")


def _document_brief(record: DocumentRecord) -> dict[str, Any]:
    return {
        "document_id": record.document_id,
        "source_name": record.source_name,
        "page_count": record.page_count,
        "created_at": record.created_at,
        "sha256": record.sha256,
    }


def _ingest(args: argparse.Namespace) -> dict[str, Any]:
    if not args.pdf.is_file():
        raise CliError(f"PDF file not found: {args.pdf}")
    if args.against is not None and not args.store.is_file():
        raise CliError(f"--against names an earlier version, but the store does not exist yet: {args.store}")
    extracted = extract_document(args.pdf, out_root=args.extracted_root)
    structure = build_structure(extracted, args.pdf)
    with Store.open(args.store) as store:
        if args.against is not None:
            if args.against == extracted.document_id:
                raise CliError("--against names the file being ingested; name an earlier version of it")
            _require_document(store, args.against, args.store)
        before = _document_info_or_none(store, extracted.document_id)
        store.write_document(extracted, structure)
        stored = _stored_infos(store)
        new = next(info for info in stored if info.document_id == extracted.document_id)
        selection = select_earlier(new, stored, against=args.against, same_file_before=before)
        qa = _run_comparison(store, new, selection, args.report_dir)
    return {
        "document_id": extracted.document_id,
        "source_name": extracted.source_name,
        "sha256": extracted.sha256,
        "page_count": extracted.page_count,
        "status_counts": dict(sorted(extracted.status_counts.items())),
        "sections": len(structure.sections),
        "units": len(structure.units),
        "table_cells": len(structure.table_cells),
        "structure_issues": len(structure.issues),
        "store": str(args.store),
        "report_path": str(args.extracted_root / extracted.document_id / REPORT_NAME),
        "qa": qa,
    }


def _document_info_or_none(store: Store, document_id: str) -> DocumentInfo | None:
    record = store.document_record(document_id)
    if record is None:
        return None
    return DocumentInfo(
        document_id=record.document_id,
        source_name=record.source_name,
        sha256=record.sha256,
        page_count=record.page_count,
        extractor_version=record.extractor_version,
        extraction_config_sha256=record.extraction_config_sha256,
    )


def _stored_infos(store: Store) -> list[DocumentInfo]:
    infos = [_document_info_or_none(store, document_id) for document_id in store.document_ids()]
    return [info for info in infos if info is not None]


def _page_records(store: Store, document_id: str) -> list[PageRecord]:
    rows = store.page_rows(document_id)
    texts = store.page_texts(document_id, [row.pdf_page for row in rows])
    return [
        PageRecord(pdf_page=row.pdf_page, raw_text=texts[row.pdf_page], status=row.status, warnings=row.warnings)
        for row in rows
    ]


def _run_comparison(store: Store, new: DocumentInfo, selection: Selection, report_dir: Path) -> dict[str, Any]:
    """The ``qa`` object. Its status and reason are always present; the comparison is added when two versions were compared."""
    qa: dict[str, Any] = {
        "status": selection.status,
        "reason": selection.reason,
        "earlier_document_id": selection.earlier.document_id if selection.earlier is not None else None,
        "candidates": list(selection.candidates),
        "report_path": None,
        "report_error": None,
    }
    if selection.status != "compared" or selection.earlier is None:
        return qa
    comparison = compare_documents(
        new=new,
        earlier=selection.earlier,
        new_pages=_page_records(store, new.document_id),
        earlier_pages=_page_records(store, selection.earlier.document_id),
    )
    qa.update(
        status=comparison.status,
        text_identical=comparison.text_identical,
        counts=dict(comparison.counts),
        notices=list(comparison.notices),
        earlier_page_count=comparison.earlier.page_count,
        new_page_count=comparison.new.page_count,
        differences=[asdict(difference) for difference in comparison.differences],
    )
    if comparison.status == "compared":
        qa["report_path"], qa["report_error"] = _write_report(comparison, report_dir)
    return qa


def _write_report(comparison: DocumentComparison, report_dir: Path) -> tuple[str | None, str | None]:
    """Write the text report. A failure is returned, not raised: the document is already stored (ARCHITECTURE §20.5)."""
    path = report_dir / f"{comparison.new.document_id}-vs-{comparison.earlier.document_id}.txt"
    try:
        report_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(render_report(comparison), encoding="utf-8")
    except OSError as exc:
        return None, str(exc)
    return str(path), None


def _compare(args: argparse.Namespace) -> dict[str, Any]:
    with _open_store(args.store) as store:
        _require_document(store, args.document_id, args.store)
        if args.against is not None:
            if args.against == args.document_id:
                raise CliError("compare needs two different documents; --against names the same document as --document-id")
            _require_document(store, args.against, args.store)
        stored = _stored_infos(store)
        new = next(info for info in stored if info.document_id == args.document_id)
        selection = select_earlier(new, stored, against=args.against)
        qa = _run_comparison(store, new, selection, args.report_dir)
    return {"document_id": new.document_id, "source_name": new.source_name, "qa": qa}


def _ask(args: argparse.Namespace) -> dict[str, Any]:
    with _open_store(args.store) as store:
        _require_document(store, args.document_id, args.store)
        response = answer(store, args.document_id, args.question)
    return response.model_dump(mode="json")


def _report(args: argparse.Namespace) -> dict[str, Any]:
    with _open_store(args.store) as store:
        if args.document_id is None:
            documents = []
            for document_id in store.document_ids():
                record = store.document_record(document_id)
                if record is not None:
                    documents.append(_document_brief(record))
            return {"store": str(args.store), "documents": documents}
        _require_document(store, args.document_id, args.store)
        record = store.document_record(args.document_id)
        structure = store.load_structure(args.document_id)
        return {
            "document": record.model_dump(mode="json") if record is not None else {},
            "pages": [row.model_dump(mode="json") for row in store.page_rows(args.document_id)],
            "structure": {
                "sections": len(structure.sections),
                "units": len(structure.units),
                "units_by_type": dict(sorted(Counter(unit.content_type.value for unit in structure.units).items())),
                "table_cells": len(structure.table_cells),
                "issues_by_code": dict(sorted(Counter(issue.code for issue in structure.issues).items())),
            },
        }


def _evaluate(args: argparse.Namespace) -> dict[str, Any]:
    if args.split == "heldout" and not args.final_run:
        raise CliError("a held-out run needs --final-run, the one final run (ARCHITECTURE §17.5, D84).")
    if args.split == "dev" and args.final_run:
        raise CliError("--final-run applies only to --split heldout.")
    if not args.gold.is_file():
        raise CliError(f"gold file not found: {args.gold}")
    with _open_store(args.store) as store:
        _require_document(store, args.document_id, args.store)
        dataset = load_gold(args.gold)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        run = run_evaluation(
            store,
            args.document_id,
            dataset,
            args.split,
            final_run=args.final_run,
            output_dir=args.output_dir,
            run_id=args.run_id,
        )
    payload = json.loads(run.output_path.read_text(encoding="utf-8"))
    return {
        "run_id": run.run_id,
        "run_file": str(run.output_path),
        "split": payload["split"],
        "final_run": payload["final_run"],
        "source": payload["source"],
        "banner": payload["banner"],
        "annotators": payload["annotators"],
        "record_count": run.record_count,
        "metrics": payload["metrics"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command and return its exit code (ARCHITECTURE §19.4)."""
    args = build_parser().parse_args(None if argv is None else list(argv))
    handler: Handler = args.handler
    try:
        payload = handler(args)
    except (VeritasQAError, OSError) as exc:
        _emit_error(exc)
        return 1
    _emit(payload)
    return 0

"""P2 on the public QA corpus (data/corpus/public): real public documents, not the owner's PDF (B1).

The PDFs are git-ignored, so a fresh clone skips these tests and states why. Each file is first checked
against data/corpus/public/manifest.json. Every structure check is a property check
(tests/fixtures/structure_checks.py); no expected heading, unit or answer is written here, because no
human has verified one.

Run: pytest tests/integration/test_p2_corpus.py -q
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.document_structure import build_structure
from app.ingestion.extract import extract_document
from tests.fixtures.structure_checks import check_invariants

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = REPO_ROOT / "data" / "corpus" / "public"
MANIFEST_PATH = CORPUS_DIR / "manifest.json"
DOCUMENTS = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["documents"]

pytestmark = pytest.mark.public_corpus


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _present(entry: dict) -> Path:
    path = CORPUS_DIR / entry["file"]
    if not path.is_file():
        pytest.skip(f"{entry['file']} is not in data/corpus/public (git-ignored); re-fetch it from {entry['source_url']}")
    return path


@pytest.mark.parametrize("entry", DOCUMENTS, ids=lambda entry: entry["file"])
def test_corpus_file_matches_its_manifest_entry(entry):
    path = _present(entry)
    assert path.stat().st_size == entry["bytes"], "the file size differs from the manifest"
    assert _sha256(path) == entry["sha256"], "the SHA-256 differs from the manifest"


@pytest.mark.parametrize("entry", DOCUMENTS, ids=lambda entry: entry["file"])
def test_structure_invariants_hold_on_a_corpus_document(entry, tmp_path):
    path = _present(entry)
    extracted = extract_document(path, out_root=tmp_path / "p1")
    assert extracted.page_count == entry["pages"], "the page count differs from the manifest"
    structure = build_structure(extracted, path)
    check_invariants(extracted, structure)
    assert structure.units, "a corpus document must produce evidence units"
    assert structure.sections, "a corpus document must produce at least one section"

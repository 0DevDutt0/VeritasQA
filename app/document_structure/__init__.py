"""P2 structure: sections, evidence units, table cells and provenance (ARCHITECTURE §11)."""

from app.document_structure.build import build_structure
from app.document_structure.config import StructureConfig, load_structure_config
from app.document_structure.errors import StructureConfigError, StructureError
from app.document_structure.models import (
    STRUCTURE_ISSUE_CODES,
    ContentType,
    DocumentStructure,
    EvidenceUnit,
    Section,
    StructureIssue,
    TableCell,
)

__all__ = [
    "STRUCTURE_ISSUE_CODES",
    "ContentType",
    "DocumentStructure",
    "EvidenceUnit",
    "Section",
    "StructureConfig",
    "StructureConfigError",
    "StructureError",
    "StructureIssue",
    "TableCell",
    "build_structure",
    "load_structure_config",
]

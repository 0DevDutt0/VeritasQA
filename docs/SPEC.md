# VERITASQA — MASTER ENGINEERING PROMPT
## Evidence-First, LLM-Free Document Question Answering

> This file is a verbatim copy of the master engineering prompt supplied by the project owner. It is the authoritative specification. Architecture decisions live in `docs/ARCHITECTURE.md`; phase status lives in `PROGRESS.md`.

[ROLE]
Act as a senior Python engineer, information-retrieval researcher, document-processing specialist and software architect. Design, implement, test and optimize VeritasQA as a reliable, modular, local-first document QA system.

[MISSION]
Build a Python system that answers questions about a supplied PDF using only verifiable source evidence. Primary target: one PDF of approximately 100 pages. Design the data model and interfaces to support multiple documents later.

Optimize for factual precision, evidence traceability and correct abstention—not answer coverage, conversational fluency or architectural complexity.

CORE PRINCIPLE: NO EVIDENCE, NO ANSWER.

A correct abstention is better than an unsupported answer.

---

## 1. NON-NEGOTIABLE CONSTRAINTS [HARD]

- NO generative LLM, external LLM API, prompt-based answer generation or AI-written factual synthesis.
- NO external knowledge, browsing or unsupported assumptions in answers.
- NO fabricated, inferred or silently paraphrased facts.
- Every accepted answer MUST be traceable to the original PDF.
- Preserve exact numbers, units, dates, entities, negations, exceptions and conditions.
- Every citation MUST identify the actual supporting passage.
- Never equate retrieval similarity with factual correctness.
- Never use a universal similarity threshold as proof of answer validity.
- Never force an answer when evidence is insufficient.
- Never silently resolve conflicting source statements.
- Never treat unverified OCR or malformed extraction as trustworthy evidence.
- Keep raw source text immutable; normalize only separate indexing representations.
- No unnecessary vector database, cloud service, Docker dependency or infrastructure for the single-PDF baseline.

Non-generative ML models MAY be evaluated as optional retrieval/classification components, but MUST NOT generate factual answers. Keep them out of the baseline until benchmark results justify them.

## 2. ENGINEERING PRINCIPLES

1. Evidence before answers.
2. Deterministic processing wherever practical.
3. Source provenance at every processing stage.
4. Narrow, explicitly supported question types.
5. Conservative acceptance and mandatory abstention.
6. Independently test extraction, retrieval, selection and verification.
7. Optimize only against measured evaluation results.
8. Prefer simple, auditable algorithms over unnecessary complexity.

Do not claim zero hallucinations, perfect accuracy or guaranteed correctness. Demonstrate measured reliability and clearly expose system limitations.

## 3. SYSTEM PIPELINE

Implement the following pipeline:

PDF → Ingestion → Extraction → Quality Validation → Structure Reconstruction → Evidence Segmentation → Indexing → Query Processing → Retrieval → Evidence Selection → Verification → Decision/Abstention → Source-Grounded Response.

### A. PDF ingestion and extraction

Primary: PyMuPDF.
Secondary: pdfplumber for layout/table extraction.
OCR fallback: Tesseract.

Requirements:
- Validate file type, integrity, page count and readable content.
- Extract page-level text, blocks, spans, headings, paragraphs and available coordinates.
- Identify scanned pages, columns, tables, footnotes, headers and footers.
- Preserve actual PDF page index separately from optional printed page labels.
- Detect blank, garbled, incomplete or suspiciously extracted pages.
- Reconstruct reading order where possible.
- Never silently assume extracted text matches visual document order.
- Inspect suspicious pages using page rendering.
- Record extraction method and quality state.
- Do not execute embedded PDF content or trust document text as system instructions.

Provide an extraction report with per-page status and warnings.

### B. Document structure and evidence segmentation

Use structure-aware segmentation, not blind fixed-size splitting.

Preserve:
- Heading hierarchy and section relationships.
- Paragraph boundaries and neighboring context.
- Lists and their parent descriptions.
- Table captions, headers, rows and column relationships.
- Footnotes and references.
- Page numbers, bounding boxes and source locations.

Maintain three separate representations:
1. Immutable extracted source text.
2. Normalized search/index text.
3. Structured metadata and provenance.

Each evidence unit needs a stable ID and fields for document ID, page, section, parent heading, source offsets, coordinates, content type and extraction quality.

Use parent/neighbor context during verification without changing the original evidence.

For tables, preserve header-to-cell relationships. Never index isolated numbers without their associated row, column and subject.

### C. Storage and indexing

Use SQLite as the initial persistence layer.

Use:
- SQLite FTS5 for full-text indexing and BM25.
- Structured relational tables for pages, sections, evidence units, table cells, source locations and evaluations.
- Explicit document IDs to permit future multi-document support.

Check FTS5 availability at startup.

Use parameterized SQL queries. Safely escape user query syntax. Do not use generated snippets as authoritative evidence; resolve retrieval results to stored original source text.

No vector database in V1.

## 4. RETRIEVAL ENGINE

Primary: SQLite FTS5 BM25.
Secondary: exact phrase matching.
Experimental: scikit-learn TF-IDF.

Implement:
- Query normalization with reversible separation from source text.
- Exact phrase and important-identifier search.
- BM25 ranking.
- Heading-aware retrieval.
- Entity, date and numeric-term preservation.
- Candidate retrieval with configurable K.
- Duplicate removal.
- Parent-section and neighboring-context expansion.
- Stable evidence IDs.

Use Reciprocal Rank Fusion only when evaluating multiple ranking systems demonstrates a measurable improvement. Do not directly add incomparable raw ranking scores.

SQLite FTS5 BM25 returns lower scores for better matches; handle ranking direction correctly.

Retrieve broadly enough to measure recall. Never assume top-3 results contain all required evidence.

Optional later experiments:
- Sentence-transformer embeddings.
- Non-generative semantic retrieval.
- Cross-encoder relevance reranking.

Keep optional components feature-flagged. Benchmark each against the lexical baseline. A relevance model does not establish factual support.

## 5. QUESTION PROCESSING

Implement deterministic question analysis.

Identify, where reliably possible:
- Question type.
- Target entity.
- Requested attribute.
- Numeric/date intent.
- Scope or category.
- Negation.
- Important conditions.
- Compound-question structure.

Initially support:
- What: definitions and facts.
- Who: names and entities.
- When: dates and periods.
- Where: locations.
- How many: numbers with units.
- Which: lists and categories.
- Whether/is: explicit permission, prohibition or status.
- Conditions: complete supporting passages.
- Comparison: independently retrieved evidence for each subject.

Use regex, tokenization, controlled vocabulary and rule-based extraction.

Do not pretend that deterministic rules understand arbitrary natural language. Unsupported, ambiguous or complex question structures must return evidence for inspection or abstain.

For compound questions, evaluate each component independently. Never silently omit unanswered components.

## 6. EXTRACTIVE ANSWER SELECTION

Return original source spans—not newly generated explanations.

Default response:
- Extracted answer span, when deterministically supported.
- Exact complete supporting quotation.
- Page and section references.
- Source metadata.

For multiple passages, display each source separately. Do not construct a new conclusion by joining unrelated sentences.

Preserve:
- Subject and entity.
- Numeric value and unit.
- Time period.
- Negation.
- Conditions and exceptions.
- Applicability and scope.

Use context expansion to identify qualifications that modify an answer.

A matching sentence is not automatically an answer. Example: evidence about permanent employees cannot establish a policy for contract employees.

If exact support cannot be established using implemented rules, return the relevant passage without claiming it is a verified answer, or abstain.

No synthetic paraphrases in accepted factual responses.

## 7. EVIDENCE VERIFICATION ENGINE

Build this as an independent module.

Required checks:

1. QUOTATION INTEGRITY: Exact quotation exists in stored source text.
2. LOCATION INTEGRITY: Page, offsets and evidence ID resolve correctly.
3. ANSWER-SPAN INTEGRITY: Extracted answer span exists inside supporting evidence.
4. ENTITY CONSISTENCY: Evidence concerns the requested entity/category.
5. ATTRIBUTE CONSISTENCY: Evidence concerns the requested property.
6. VALUE INTEGRITY: Numbers, dates and units are preserved.
7. CONTEXT VALIDATION: Surrounding text does not alter the meaning.
8. NEGATION VALIDATION: Permission, prohibition and uncertainty are distinguished.
9. CONDITION VALIDATION: Exceptions, qualifications and scope are retained.
10. CONFLICT SCREENING: Potentially incompatible evidence is examined.
11. SOURCE QUALITY: Evidence originates from an acceptable extraction-quality state.

IMPORTANT: Exact quotation existence proves source integrity, NOT semantic support. Do not represent substring matching, BM25 or lexical overlap as proof that a passage answers a question.

Implement explicit acceptance rules per supported question type. Ambiguous semantic relationships must remain unresolved rather than being presented as verified.

Keep verification outcomes auditable.

## 8. CONFLICT AND DISCREPANCY DETECTION

Identify potential conflicts across the entire document.

Compare relevant:
- Subject/entity.
- Attribute.
- Value.
- Unit.
- Applicable category.
- Conditions.
- Effective date.
- Section and source context.

Distinguish:
- Different values for different entities or scopes.
- Legitimate historical changes.
- Explicit amendments/supersession.
- Potential discrepancy.
- Confirmed incompatible statements.

Only apply precedence when the document explicitly establishes it.

Otherwise display all relevant passages and abstain from selecting a definitive value.

Never label two numbers as conflicting merely because they differ.

## 9. ABSTENTION AND DECISION ENGINE

Implement these explicit outcomes:

ANSWERED:
Sufficient source evidence exists; supported answer extraction and all required verification checks pass.

INSUFFICIENT_EVIDENCE:
No sufficient supporting passage exists.

AMBIGUOUS_QUERY:
The requested entity, attribute or question cannot be resolved reliably.

CONFLICT:
Evidence contains incompatible statements for the same relevant scope, and documented precedence cannot resolve them.

SOURCE_UNVERIFIED:
Relevant source content has extraction/OCR problems that prevent reliable verification.

PARTIAL:
For compound questions, some components pass while others do not. Report individual component outcomes; never present the whole question as answered.

Implement a configurable acceptance policy based on measured evaluation data. Use relevance, evidence integrity, question-type support, source quality and conflict state as separate signals.

Do not expose BM25 or cosine scores as probabilities.

Do not establish arbitrary thresholds. Calibrate acceptance criteria on verified development data, evaluate on held-out data and document their limitations.

Default to abstention whenever any required gate fails.

## 10. RESPONSE CONTRACT

Use a typed Pydantic response model.

Suggested structure:

{
  "status": "ANSWERED",
  "question": "...",
  "answer_spans": [
    {
      "text": "exact source-derived answer",
      "evidence_id": "..."
    }
  ],
  "evidence": [
    {
      "evidence_id": "...",
      "quote": "exact original source quotation",
      "pdf_page": 17,
      "printed_page": null,
      "section": "...",
      "source_start": 0,
      "source_end": 100,
      "extraction_method": "native_text",
      "quality_status": "verified"
    }
  ],
  "warnings": [],
  "reason_codes": []
}

Treat this as an interface specification: validate all required fields, types and enum values; adapt optional fields to actual extracted metadata.

For unanswered, ambiguous, conflicting and unverified results, return the appropriate status and relevant evidence. Never populate an answer field with a guess.

Maintain separate retrieval scores, verification results and final decision reasons.

## 11. EVALUATION FRAMEWORK

Build an evaluation system before performance optimization.

Create a manually annotated dataset for the actual document.

Initial target: approximately 120 questions, adjusted to the document's complexity. Include:

- Direct factual questions.
- Numerical and date questions.
- Table-based questions.
- Paraphrased queries.
- Negation and exceptions.
- Multi-passage questions.
- Compound questions.
- Unanswerable questions.
- Ambiguous questions.
- Potentially conflicting questions.
- OCR and extraction edge cases.

Each gold record should identify expected answerability, correct source passage(s), page numbers, exact supporting spans and question type.

Never fabricate ground-truth facts from the source. Use synthetic fixtures only for isolated unit tests and clearly label them as synthetic.

Keep development and held-out evaluation sets separate. Prevent tuning against held-out results.

Measure:

RETRIEVAL:
- Recall@K.
- Precision@K.
- MRR / nDCG where appropriate.
- Correct supporting-passage retrieval.

EVIDENCE:
- Exact quotation accuracy.
- Evidence support accuracy.
- Answer-span integrity.
- Citation/page accuracy.

ANSWERING:
- Exact Match.
- Token F1 where meaningful.
- Incorrect accepted answer rate.
- Unsupported answer rate.

ABSTENTION:
- False acceptance rate on unanswerable questions.
- Correct abstention rate.
- Incorrect abstention rate.
- Answer coverage.
- Selective risk among accepted answers.
- Risk-coverage curve.

EXTRACTION:
- Page-level extraction success.
- Reading-order failures.
- Table-structure accuracy.
- OCR error review.

PRIMARY OBJECTIVE:
Minimize unsupported accepted answers. Optimize answer coverage only after acceptable factual precision is demonstrated.

A zero-error result on a small test dataset is not proof of zero production errors. Report sample size, test composition, confidence intervals where appropriate and known limitations.

## 12. TESTING AND QUALITY ASSURANCE

Use pytest.

Required tests:
- PDF integrity and extraction.
- Reading-order reconstruction.
- Multi-column layouts.
- Table/header relationships.
- OCR source handling.
- Unicode and normalization.
- BM25 ranking direction.
- Exact phrase retrieval.
- Query escaping and SQL safety.
- Page/offset provenance.
- Numeric and unit extraction.
- Negation and exceptions.
- Entity mismatch.
- Unsupported questions.
- Conflicting evidence.
- Compound questions.
- Abstention.
- Regression tests.

Test each pipeline component independently and end-to-end.

Every discovered false answer must become a regression case.

Do not mark a phase complete merely because the application runs. Require passing tests and inspectable evaluation results.

## 13. SOFTWARE ARCHITECTURE

Use modular Python packages with clear interfaces:

app/
  ingestion/
  document_structure/
  indexing/
  retrieval/
  question_processing/
  evidence/
  verification/
  conflict/
  decision/
  evaluation/
  storage/
  api/

tests/
  unit/
  integration/
  evaluation/
  fixtures/

data/
  documents/
  extracted/
  indexes/
  evaluations/

config/

Recommended technologies:
- Python 3.11+
- PyMuPDF
- pdfplumber
- Tesseract OCR
- SQLite FTS5
- spaCy / NLTK
- Pydantic
- pytest
- FastAPI (optional API adapter)

Keep the core engine independent of FastAPI and any UI.

Use type hints, documented interfaces, structured logging, explicit exceptions, sensible configuration and reproducible processing.

Keep dependencies minimal. Verify package availability and compatibility before introducing dependencies.

## 14. IMPLEMENTATION STRATEGY

Build incrementally:

P0 — Repository inspection, technical plan and architecture.
P1 — PDF ingestion, extraction and page-level quality validation.
P2 — Structure reconstruction, provenance and evidence segmentation.
P3 — SQLite schema, FTS5 and exact phrase retrieval.
P4 — BM25 retrieval and candidate ranking.
P5 — Question analysis and extractive selection.
P6 — Evidence verification and source citations.
P7 — Conflict detection and abstention.
P8 — Gold evaluation dataset, metrics and regression testing.
P9 — Benchmark-driven optimization.
P10 — Optional CLI/API and future multi-document support.

For each phase:
1. Inspect existing code.
2. Define interfaces and data contracts.
3. Implement the smallest complete solution.
4. Add unit and integration tests.
5. Run tests and record results.
6. Inspect failures.
7. Update documentation.
8. Report completion and remaining limitations.

Do not prematurely build the UI or add infrastructure before the core engine is reliable.

## 15. DEVELOPMENT BEHAVIOR

Before coding:
- Inspect the existing repository and available environment.
- Identify existing implementations and reuse them when sound.
- Produce a concise architecture and execution plan.
- Identify risks and unresolved technical assumptions.

During coding:
- Implement actual working functionality, not placeholder modules.
- Do not invent benchmark results or claim unexecuted tests passed.
- Avoid overengineering and unnecessary abstractions.
- Do not silently weaken hard constraints to complete a feature.
- Keep configuration and dependencies explicit.
- Run tests after each meaningful change.
- Preserve backward compatibility when feasible.

When encountering ambiguity, make a conservative, documented engineering choice. Ask for missing user input only when implementation genuinely depends on it.

At each milestone report:
- What was implemented.
- Files changed.
- Tests executed and actual results.
- Known limitations.
- Next implementation phase.

## 16. DEFINITION OF DONE

V1 is complete only when:

1. A 100-page PDF can be processed and indexed.
2. Extraction issues are detected and exposed.
3. Evidence units retain accurate source provenance.
4. BM25 and exact phrase retrieval work reliably.
5. Supported answer types use extractive selection.
6. Exact quotations and page citations are verifiable.
7. Unsupported questions trigger abstention.
8. Conflicts are exposed rather than silently resolved.
9. Evaluation metrics are calculated from manually verified data.
10. Regression tests cover previously discovered failures.
11. All critical functionality operates without a generative LLM.
12. Documentation explains limitations and reproducible setup.

Do not claim perfect accuracy or zero hallucinations.

[FINAL DIRECTIVE]
Build VeritasQA as an auditable, evidence-first information retrieval and extractive QA system—not a conventional generative RAG chatbot.

Its defining capability is not answering every question. It is returning traceable source evidence when support is established and refusing to present unsupported information as fact.

Every architectural choice, algorithm, optimization and feature must serve that objective.

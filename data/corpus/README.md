# Public QA corpus

Public documents kept in the project for QA and regression checks. They are not the owner's document (blocker B1), so no result obtained from them is a claim about the owner's PDF.

- The PDFs live in `data/corpus/public/`. The `*.pdf` rule in `.gitignore` keeps them out of git (D7). Only `manifest.json` and this README are tracked.
- `data/corpus/public/manifest.json` records each file's source URL, SHA-256, size and page count. Check a copy against it before you rely on it.
- Each file was checked at download time: the `%PDF-` header, encryption, and an active-content scan for `JavaScript`, `JS`, `Launch`, `RichMedia`, `SubmitForm`, `ImportData` and `EmbeddedFile` keys. The scan includes objects inside compressed object streams. It is a heuristic, not a malware scanner.
- Page count is not a selection criterion for this corpus. It exists for QA only.
- No document in this set has page labels (`get_page_labels()` returns nothing), so the printed-page case of D4 is not exercised by any real document here.
- The P2 property checks run on these files. Run `pytest -m public_corpus -q`. A fresh clone has no PDFs, so those tests skip and say which file is missing. Every check is a property check (quotation, coverage, overlap, chain); no expected heading or answer is stored here.

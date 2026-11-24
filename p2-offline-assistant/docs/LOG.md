# p2 failure log

Every failure found during development or benchmarking, appended in order.
Format: what broke, why, how fixed, metric before/after.

## 2026-11-25: BOM in JSONL/markdown input broke loading

- **What broke:** `bench` crashed in `load_cases` with `Invalid JSON: expected value at line 1 column 1`; the file started with a UTF-8 byte-order mark (U+FEFF).
- **Why:** PowerShell 5.1 `Set-Content -Encoding utf8` (and Notepad) write a BOM; readers used `encoding="utf-8"`, which keeps it as a character. In markdown notes the same BOM would stop YAML front matter from matching, silently giving sections the filename as their title.
- **Fix:** read with `utf-8-sig` in `evalkit.load_cases` / `load_results` and `studyqa.sections.load_notes`; regression tests for both.
- **Metric before/after:** BOM-prefixed case file: crash -> 1/1 cases loaded. BOM-prefixed note: front-matter title lost -> kept. No benchmark metrics existed yet.

# Phase 2A status: extraction and quality audit

Run date: 2026-09-15

## Outcome

Phase 2A is implemented and has completed successfully against the full Phase 1
crawl. It produces normalized, provenance-bearing page records; it does not yet
chunk, embed, or vectorize the corpus.

- FCS PDF documents verified and processed: 71/71
- PDF pages extracted: 2,887
- Document-level extraction errors: 0
- Structural/checksum validation failures: 0
- Native-text pages: 2,795
- Native-text, non-Hebrew pages: 5
- Low-text pages requiring review: 58
- Empty pages requiring review: 29
- Total pages flagged for OCR review: 87 across 22 documents
- Phase 2A regression checks: 8/8 passed

The extractor uses Unicode-aware letter counts, so Arabic source material is
not falsely classified as low-text merely because it contains little Hebrew or
Latin text.

## Visual OCR audit

Five representative flagged pages were rendered with Poppler and inspected:

| Document/page | Observation | Decision |
|---|---|---|
| `f70ab750...`, page 13 | Deliberately sparse section-title slide; native title is present | OCR not necessary |
| `52ceaadd...`, page 1 | Arabic guidance with substantial native text | Not an OCR candidate after Unicode-aware correction |
| `ce288782...`, page 4 | Portal screenshot containing useful embedded text; native extraction returns only the page number | Selective OCR would add value |
| `304b1ec4...`, page 2 | Presentation slide with useful flattened/graphic text and only partial native extraction | Selective OCR would add value |
| `d0652c5c...`, page 383 | Blank trailing page | OCR not necessary |

Therefore the 87 automatic flags are triage signals, not 87 mandatory OCR jobs.
Phase 2B will proceed without a corpus-wide OCR pass. Empty pages will be
excluded, while low-text pages will retain their native text and quality flags.
OCR will be applied only to visually confirmed image-text pages or when the
50-question Hebrew evaluation identifies a retrieval gap connected to one of
those pages. Any OCR output must remain separate from native extraction and
carry its own provenance. See `reports/ocr_policy.md` for the complete policy.

## Direct FCS references

The crawler discovered 55 exact external URLs directly referenced by FCS:

- 44 EUR-Lex URLs
- 11 YouTube URLs

The YouTube URLs remain metadata-only because a landing page is not a transcript.
The 44 EUR-Lex requests did not yield legal text in the current collection
environment: initial HTTP responses contained an AWS anti-bot challenge shell,
and the latest refresh returned empty HTML bodies. The collector now detects
these transport-success/content-failure cases, records them as non-ingestible,
and prevents them from entering the corpus. No substitute URLs were introduced.

## Reproducible command

```powershell
Set-Location C:\projects\fcs
.\.venv\Scripts\python.exe -m pip install -r requirements-phase2.txt
.\run_phase2a.ps1
```

Use `-DownloadReferencedSources` only when intentionally retrying the exact FCS
references. The run can succeed structurally while recording inaccessible or
metadata-only references; those records remain excluded from ingestion.

## Next gate

Phase 2B should create section-aware chunks with page-level citations and
benchmark
keyword, dense, and hybrid retrieval against the 50 Hebrew evaluation questions
before selecting the production embedding model or vector database. Selective
OCR is added only if visual review or evaluation results justify it.

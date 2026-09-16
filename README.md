# FCS Israel Food Import Assistant

This repository contains the discovery work for a future LlamaIndex-based
assistant for commercial food imports into Israel.

The active acquisition scope is deliberately narrow: the public FCS publication
catalogue plus exact public URLs directly referenced by its publication records.
Manually selected DataGov, gov.il, Knesset, or other external URLs are not active
sources. The project does not access the authenticated FCS portal, submit forms,
or provide a final legal determination.

## Application language

All interaction between the application and its human users must be in Hebrew,
including questions, answers, clarification prompts, warnings, abstentions, and
error messages. Original source titles and quotations may remain in their source
language, but the application must explain them in Hebrew. Code, internal field
names, and project documentation may remain in English.

The Phase 1 evaluation set contains 50 Hebrew questions. The verifier requires
every row to use `language=he` and to contain Hebrew question text. English
acronyms and formal identifiers may appear inside an otherwise Hebrew question.

## Repository layout

- `config/crawl_policy.json` — machine-enforced acquisition and ingestion boundary.
- `config/sources.json` — the single manually configured FCS entry point.
- `scripts/collect_sources.py` — snapshots only that FCS entry point.
- `scripts/discover_fcs_bundle.py` — records the FCS frontend/configuration and
  extracts candidate public endpoint names without calling authenticated actions.
- `scripts/collect_fcs_publications.py` — browser-rendered metadata collector for
  the public FCS catalogue and creator of the direct-reference manifest.
- `scripts/collect_referenced_sources.py` — downloads only exact URLs present in
  that provenance-bearing FCS reference manifest.
- `scripts/classify_references.py` — classifies those exact references without
  expanding the source scope.
- `scripts/extract_documents.py` — checksum-verifies FCS PDFs and emits
  normalized page-level JSONL with OCR-review signals.
- `scripts/validate_extraction.py` — validates document/page completeness,
  checksums, and extraction metadata.
- `scripts/test_phase2a.py` — regression checks for multilingual text quality
  and rejection of empty, false-PDF, and anti-bot payloads.
- `scripts/build_chunks.py` — builds stable page-citable chunks from the
  validated PDF extraction.
- `scripts/build_indexes.py` — persists a local LlamaIndex vector index and
  Unicode-aware BM25 baseline metadata.
- `scripts/evaluate_retrieval.py` — runs all 50 Hebrew questions through BM25,
  dense, and reciprocal-rank-fusion retrieval.
- `scripts/prepare_expert_review.py` — creates one canonical expert-review JSON
  template with compact IDs and nested human-readable FCS sources, without GUIDs.
- `scripts/import_expert_relevance.py` — maps returned FCS titles, dates, and
  URLs to internal document GUIDs and refuses ambiguous matches.
- `review_app/` — backend-free Hebrew reviewer application deployed with GitHub
  Pages; supports any number of source rows per question and exports one
  canonical JSON file.
- `scripts/search_retrieval.py` — Hebrew command-line retrieval demonstration.
- `scripts/validate_phase2b.py` — verifies chunk provenance, index freshness,
  and evaluation outputs.
- `scripts/audit_public_access.py` — retained historical discovery tool; it is
  not invoked by the active collection workflow.
- `scripts/verify_phase1.py` — validates Phase 1 deliverables and manifests.
- `data/raw/` — immutable source snapshots.
- `data/metadata/` — manifests, inventories, and the initial evaluation set.
- `reports/` — discovery findings and source-authority policy.
- `logs/` — execution logs.

## Quick start

```powershell
Set-Location C:\projects\fcs
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-phase1.txt
.\run_phase1.ps1 -RunBrowserCollection
```

Add `-RunBrowserCollection` to attempt the optional public-catalogue browser
collector. Ministry edge controls may prevent the catalogue data from loading in
a standalone automated browser; this is recorded as a Phase 1 integration risk.

The verified crawl demonstration uses installed Chrome in visible mode and
downloads one FCS-linked guide with a checksum-backed manifest:

```powershell
.\.venv\Scripts\python.exe .\scripts\collect_fcs_publications.py `
  --project-root C:\projects\fcs --show-browser --limit-categories 2 `
  --browser-channel chrome --download-match 'מדריך בנושא יבוא מזון מעודכן'
```

In the Phase 1 environment, visible Chrome rendered the catalogue reliably;
headless Chrome timed out. Treat the collector as browser-assisted until an
unattended mode passes repeated runs.

## Remote crawl with GitHub Actions

The manually triggered workflow at `.github/workflows/fcs-crawl.yml` runs
headed Playwright Chromium inside an Xvfb virtual display on a GitHub-hosted
Linux runner. It never needs a desktop session on the local machine.

Start with `crawl_mode=smoke`, which collects one category. After that succeeds,
run `crawl_mode=full`. `download_documents=true` retrieves every unique
FCS-hosted document found by that run. External direct references are disabled
by default and may be enabled separately; they are still restricted to exact
URLs carrying FCS provenance in `fcs_direct_references.json`.

Every run uploads its raw catalogue responses, manifests, checksums, report, and
downloaded documents as a private workflow artifact retained for 14 days. Crawl
outputs are intentionally ignored by Git: authoritative run results should be
downloaded from the Actions run rather than committed to repository history.

The optional publication collector uses the locally installed Google Chrome channel by
default. To use a Playwright-managed browser instead, keep its files in the
project and pass `--browser-channel bundled`:

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = 'C:\projects\fcs\.playwright-browsers'
python -m playwright install chromium
python .\scripts\collect_fcs_publications.py --browser-channel bundled
```

To collect public pages or documents directly referenced in the crawled FCS
records, run:

```powershell
.\run_phase1.ps1 -DownloadReferencedSources
```

This downloader accepts no arbitrary URL argument. Its only URL input is
`data/metadata/fcs_direct_references.json`, produced by the FCS crawler.

## Safety and provenance rules

1. The only manually configured source is the public FCS catalogue entry point.
2. An external URL is eligible only when an FCS publication supplies it in
   `infoLinkUrl` or `docs[].linkToDocument`, with `discovered_from` provenance.
3. Redirects are recorded and validated; only public HTTPS destinations are used.
4. Every snapshot receives a SHA-256 checksum and retrieval timestamp.
5. Old versions are retained; a later ingestion phase should mark them as
   superseded rather than silently deleting them.
6. The authenticated portal at `fcsportal.health.gov.il` is denied in code.
7. DataGov and pre-policy configured downloads are historical discovery evidence
   and are explicitly excluded from ingestion.
8. Informational pages and Q&A never override statutes, regulations, or official
   gazette publications.

See `reports/source_scope_policy.md` for the enforceable boundary and
`data/README.md` for active versus historical paths.

## Phase 2A: extraction and quality audit

Install the Phase 2 dependencies and run the manifest-driven extraction flow:

```powershell
Set-Location C:\projects\fcs
.\.venv\Scripts\python.exe -m pip install -r requirements-phase2.txt
.\run_phase2a.ps1
```

Add `-DownloadReferencedSources` to snapshot exact eligible external pages
directly referenced by FCS. YouTube references remain metadata-only until a
caption or transcript collection strategy can preserve provenance. A successful
HTTP response is not automatically accepted as source content: anti-bot
challenge shells are retained as retrieval evidence, marked non-ingestible, and
excluded from later chunking.

The Phase 2A runner first executes its regression checks, classifies external
references, verifies every input document against its download checksum,
extracts page-level text, flags low-text pages for OCR review, and validates
page/document consistency. Generated JSONL, manifests,
and run reports are ignored by Git and remain under the local project root.

Phase 2A does not create embeddings or a vector index. Its validated page JSONL
is the controlled input to the next step: selective OCR, section-aware chunking,
and retrieval benchmarking against the 50-question Hebrew evaluation set.

See `reports/phase2a_status.md` for the latest corpus metrics, visual OCR audit,
and direct-reference retrieval findings. The accepted MVP decision in
`reports/ocr_policy.md` is to proceed without bulk OCR and add it selectively
only when visual evidence or retrieval evaluation demonstrates a need.

## Phase 2B: LlamaIndex retrieval baseline

Phase 2B uses a local LlamaIndex `VectorStoreIndex`, a lightweight multilingual
FastEmbed model, a Unicode-aware BM25 implementation, and reciprocal rank
fusion. The model and index remain below `data/models/` and `data/indexes/` and
are intentionally not committed to Git.

```powershell
Set-Location C:\projects\fcs
.\.venv\Scripts\python.exe -m pip install -r requirements-phase2b.txt
.\run_phase2b.ps1
```

The index is content-addressed by the chunk-file checksum, so an unchanged run
reuses the existing vectors. To demonstrate retrieval in Hebrew:

```powershell
.\.venv\Scripts\python.exe .\scripts\search_retrieval.py `
  --query "מה מבדיל בין מזון רגיל למזון רגיש?" --mode hybrid --top-k 5
```

The 50-question run currently produces candidate evidence, not an accuracy
claim. The expert searches the FCS website independently in the Hebrew reviewer
and returns the single GUID-free `eval_relevance_expert.json` file. Place it
under `data/metadata/`, then run:

```powershell
.\.venv\Scripts\python.exe .\scripts\import_expert_relevance.py --check
.\.venv\Scripts\python.exe .\scripts\import_expert_relevance.py
.\run_phase2b.ps1
```

The first command validates human-readable document matching without writing
labels. The second creates the compact `eval_relevance.csv`. Recall and MRR
remain unavailable until rows are domain-approved. See
`reports/evaluation_review_guide.md` and `reports/phase2b_status.md`.

## Expert-review web application

The static application under `review_app/` provides a Hebrew RTL interface for
the independent domain review. It saves drafts only in the reviewer's browser,
allows sources to be added or removed interactively, validates approval rules
and FCS URLs, and exports one English-keyed JSON file consumed by
`scripts/import_expert_relevance.py`. Sources are nested under compact question
IDs, eliminating the duplicated question/source CSV rows. The same JSON file is
the portable backup and can be restored in another browser or device.

GitHub Pages deployment is defined in `.github/workflows/pages.yml`. The
workflow verifies that `review_app/questions.json` exactly matches the canonical
50-question CSV before publishing. To rebuild and test locally:

```powershell
.\.venv\Scripts\python.exe .\scripts\build_review_app_questions.py
.\.venv\Scripts\python.exe .\scripts\test_review_app.py
```

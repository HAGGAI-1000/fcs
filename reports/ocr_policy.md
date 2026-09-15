# OCR policy

Status: accepted for the Phase 2B MVP

## Decision

OCR is not a prerequisite for building the initial RAG index. Native PDF text
extraction produced usable text for 2,800 of 2,887 pages (about 97%). Running OCR
over the entire corpus would add processing time and can introduce recognition
errors without materially improving most documents.

The 87 pages marked `needs_ocr=true` are review candidates, not confirmed OCR
jobs. The visual audit found three different cases among them: intentionally
blank pages, sparse title pages whose useful native text was already extracted,
and image-based pages or screenshots containing useful text that native PDF
extraction missed.

## Phase 2B handling

1. Pages with `needs_ocr=false` are eligible for normal chunking.
2. Empty pages are excluded from retrieval.
3. Low-text pages retain their native text and the `needs_ocr` and
   `quality_state` metadata. Chunking may merge useful sparse titles with an
   adjacent page, but must not present them as complete page extraction.
4. No corpus-wide OCR pass is performed before the first retrieval benchmark.
5. Selective OCR is run only when visual review confirms meaningful image text,
   or when the 50-question Hebrew evaluation exposes a retrieval gap traceable
   to a flagged page.
6. OCR output must not overwrite native extraction. It must record the OCR
   engine, language model, run timestamp, source page, and confidence/quality
   information so answers remain auditable.

## Reassessment trigger

Reconsider bulk or document-level OCR only if evaluation shows that selective
OCR is insufficient, or if a future crawl adds a substantial number of scanned
documents. Until then, OCR is an optional quality-improvement step rather than
an ingestion dependency.

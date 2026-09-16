# Phase 2B status: chunking and retrieval baseline

Run date: 2026-09-15

## Outcome

The Phase 2B technical pipeline is implemented and runs end to end. It creates
page-citable chunks, persists a local LlamaIndex vector index, implements a
Unicode-aware BM25 baseline, combines the two with reciprocal rank fusion, runs
all 50 Hebrew evaluation questions, and validates provenance and index freshness.

- Validated FCS source documents: 71
- Validated source pages: 2,887
- Generated chunks: 10,358
- Empty pages excluded: 29
- Non-content low-text pages excluded: 20
- Sparse heading pages merged with following content: 31
- Chunks retaining an OCR-review flag: 58
- LlamaIndex embedding dimension: 384
- Persisted index size: approximately 136.6 MB
- Local model cache size: approximately 240.5 MB
- Phase 2B regression checks: 8/8 passed
- Phase 2B structural/provenance validation: passed with zero failures

The dense baseline uses
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` through a small
LlamaIndex `BaseEmbedding` adapter. The adapter is used because the older
packaged LlamaIndex FastEmbed integration is not compatible with the project's
Python 3.14 environment; the current FastEmbed runtime itself is compatible.

## Retrieval diagnostic

All 50 questions produced BM25, dense, and hybrid candidates.

- BM25/dense top-result document agreement: 8/50
- Mean top-five document Jaccard overlap: 0.220
- Domain-approved relevance labels: 0/50

The low agreement confirms that lexical and dense retrieval behave differently,
but it does not show which is more accurate. Recall and MRR are intentionally
withheld until expected source documents are reviewed independently. The expert
uses the Hebrew web reviewer, exports one GUID-free JSON file, and searches the
FCS website directly.
`data/processed/eval_candidate_review.csv` is reserved for an unranked second-pass
completeness check; it is not shown during the initial review.

## Scope and limitations

Only checksum-validated FCS PDFs are present in the index. The non-ingestible
EUR-Lex responses and metadata-only YouTube references are excluded. Every
chunk carries document GUID, checksum, page range, category, and FCS catalogue
URL. No answer generation or end-user application is included yet.

The current multilingual model is a local baseline, not a production model
selection. Chunk sizes, embedding models, fusion weights, reranking, and OCR
must not be tuned against unreviewed candidate output.

## Next gate

A domain reviewer should complete the Hebrew web form using the FCS website and
return `eval_relevance_expert.json`. Run
`scripts/import_expert_relevance.py --check`, resolve every
missing or ambiguous title match, then import the compact GUID labels. After
that, rerun Phase 2B, compare Recall@5 and MRR@10, inspect failures by category
and risk level, and only then choose the production retrieval configuration.

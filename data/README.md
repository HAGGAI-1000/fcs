# Data scope

## Active collection and future ingestion

- `metadata/fcs_publication_inventory.json` - crawled FCS categories and items.
- `metadata/fcs_entrypoint_manifest.jsonl` - snapshot manifest for the sole FCS
  catalogue entry point.
- `metadata/fcs_document_downloads.json` - FCS-hosted documents selected and
  downloaded from publication items.
- `metadata/fcs_direct_references.json` - exact external URLs directly supplied
  by FCS publication records, with `discovered_from` provenance.
- `metadata/fcs_referenced_downloads.json` - results from downloading those exact
  references; created when the referenced-source collector runs.
- `raw/fcs_publications/` - captured public FCS catalogue responses.
- `raw/fcs_entrypoint/` - snapshot of the public FCS catalogue application shell.
- `raw/fcs_documents/` - downloaded FCS-hosted documents.
- `raw/fcs_referenced_sources/` - downloaded exact FCS references.
- `raw/github_artifacts/` - checksum-verified GitHub Actions crawl archives kept
  as immutable run evidence; never ingest these ZIP files into the RAG corpus.
- `processed/fcs_documents.jsonl` - one extraction-quality record per FCS PDF.
- `processed/fcs_pages.jsonl` - normalized page-level text and provenance used
  as the input to later chunking.
- `metadata/fcs_reference_classification.json` - type and collection routing for
  exact direct references.
- `metadata/extraction_manifest.json` - extraction dependency, input checksum,
  and aggregate quality metrics.
- `metadata/extraction_validation.json` - structural and checksum validation
  results for extracted documents and pages.

Future ingestion must use the active manifests, never a recursive scan of this
directory.

## Historical discovery - excluded from ingestion

- `raw/access_audit/`
- `raw/configured_sources/`
- `metadata/open_data_candidates.json`
- `metadata/source_manifest.jsonl`

These paths document earlier feasibility research, including DataGov and manually
seeded official sources. They remain for auditability but are not corpus inputs.

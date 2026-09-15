# Collection status

Run date: 2026-09-14

## Current active result

- Manually configured acquisition sources: 1 (the public FCS catalogue)
- Browser-verified FCS publication categories: 12
- Demonstration categories crawled: 2
- Demonstration publication items captured: 28
- Demonstration FCS documents discovered: 20
- Demonstration FCS PDF downloaded and verified: 1
- Hebrew seed evaluation questions: 50
- Phase 1 verification: passed

The active provenance chain and checksum-backed result are stored in
`data/metadata/fcs_publication_inventory.json`,
`data/metadata/fcs_direct_references.json`, and
`data/metadata/fcs_document_downloads.json`.

## Historical discovery material

The original 14-source registry, five downloaded non-crawl snapshots, and the
DataGov access audit are retained for reproducibility. They are excluded from
active ingestion by `config/crawl_policy.json`. The prior registry is archived as
`config/archived_sources_pre_fcs_only.json`.

## Recorded blockers

Visible Chrome repeatedly rendered the FCS catalogue and retrieved a selected
31-page PDF. Headless Chrome did not render catalogue rows within 45 seconds.
Candidate request shapes remain public frontend implementation details rather
than a supported API contract.

## Recommended resolution

Use the verified visible-browser collector while hardening unattended execution.
Only follow exact links emitted by FCS publication records. Do not attempt to
bypass the authenticated portal or edge controls, and do not recursively ingest
historical discovery directories.

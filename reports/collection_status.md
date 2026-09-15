# Collection status

Run date: 2026-09-15

## Current active result

- Manually configured acquisition sources: 1 (the public FCS catalogue)
- GitHub-hosted FCS publication categories crawled: 12 of 12
- Publication items captured: 72
- Unique FCS-hosted documents downloaded: 71
- FCS-hosted document download errors: 0
- Downloaded document bytes: 89,694,338
- Exact external references discovered from FCS records: 55
- Per-document size and SHA-256 validation failures: 0
- Successful GitHub Actions run: 34959980681 (11m 58s)
- GitHub artifact SHA-256: `92a92ba4d2dfa2f3b4bca03fe78f95d50f3bd8c7d2856a2d9d73151627da44b0`
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

The GitHub workflow ran headed Chromium inside an Xvfb virtual display. Its first
full run encountered two HTTP 403 document responses; paced retries with backoff
closed both gaps in the successful run. The 55 direct external references were
discovered and provenance-recorded but were not downloaded in this core-corpus
run.

## Remaining constraints

Native headless Chrome did not render catalogue rows within 45 seconds. Headed
Chromium under Xvfb is therefore the verified unattended mode. Candidate request
shapes remain public frontend implementation details rather than a supported API
contract.

## Recommended resolution

Use the verified GitHub Actions workflow for reproducible remote crawls. Only
follow exact links emitted by FCS publication records. Do not attempt to bypass
the authenticated portal or edge controls, and do not recursively ingest
historical discovery directories.

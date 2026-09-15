# Active source-scope policy

Effective decision: use only the public FCS publication portal and public
sources directly referenced by a publication record returned by that portal.

## Enforced acquisition graph

```text
FCS publication catalogue (the only manual entry point)
  -> FCS category
  -> FCS publication item
     -> FCS-hosted document identified by that item
     -> exact HTTPS URL present in infoLinkUrl
     -> exact HTTPS URL present in docs[].linkToDocument
```

No other discovery route is active. A domain being governmental or authoritative
is not sufficient by itself. An external URL must carry a `discovered_from`
record connecting it to the FCS catalogue, category, and publication item.

## Code enforcement

- `config/sources.json` contains one source: the FCS catalogue entry point.
- `config/crawl_policy.json` defines the entry point, provenance requirement,
  denied authenticated host, redirect limit, and ingestion exclusions.
- `scripts/collect_sources.py` rejects configured URLs that are not policy entry
  points and rejects redirects outside the FCS service boundary.
- `scripts/collect_fcs_publications.py` renders the catalogue, captures its public
  publication records, downloads FCS-hosted documents, and writes
  `data/metadata/fcs_direct_references.json` for exact external references.
- `scripts/collect_referenced_sources.py` accepts no arbitrary URL input. It can
  download only eligible entries from the direct-reference manifest, validating
  HTTPS, denied hosts, redirects, content type, and size.
- `scripts/verify_phase1.py` fails if manual external seeds return, the default
  workflow invokes DataGov, the authenticated portal is not denied, or an
  external download lacks FCS provenance.

## Active ingestion inputs

Future LlamaIndex ingestion must read only the manifests declared in
`config/crawl_policy.json`:

- `data/metadata/fcs_document_downloads.json`
- `data/metadata/fcs_entrypoint_manifest.jsonl`
- `data/metadata/fcs_direct_references.json`
- `data/metadata/fcs_referenced_downloads.json`

It must never recursively ingest `data/raw` as a whole.

## Historical material

Earlier DataGov and manually curated official-source investigations are retained
for reproducibility. They are not active sources and are excluded from ingestion
by policy. Their presence on disk does not authorize their use in the RAG corpus.

## Operational boundary

The authenticated portal `fcsportal.health.gov.il`, form submissions, personal
records, and access-control bypass are prohibited. Visible Chrome is currently
the verified catalogue collection mode; headless mode has not yet proved reliable.

# Public API, export, feed, and access assessment

> Historical discovery report. DataGov and other non-FCS discoveries in this
> report are excluded from the active corpus. The current enforceable boundary is
> defined in `reports/source_scope_policy.md` and `config/crawl_policy.json`.

Audited: 2026-09-14T11:23:52.700517+00:00

## Executive result

- **Green:** DataGov's documented CKAN API and dataset resources, subject to each dataset's licence.
- **Amber:** Public FCS publications visible in the browser and internal request names found in the frontend, but no published FCS API contract was found.
- **Red/out of scope:** Authenticated importer records, form submission endpoints, or any access requiring bypass of portal controls.

## 1. Documented public API

The documented DataGov `package_search` API was queried with 6 terms.
It produced 3 food/import-related candidate datasets after local relevance filtering.
The complete API responses and normalized inventory are stored under `data/raw/access_audit/datagov/` and `data/metadata/open_data_candidates.json`.

No official OpenAPI/Swagger documentation for the FCS publication endpoints was found in the inspected public FCS page or configuration. Internal endpoint names therefore remain unsupported implementation details.

## 2. Bulk exports

Health-ministry candidate datasets: 2.
Resources that advertise a DataStore or common bulk format: 3.
Direct resource URLs returning a usable non-empty HTTP 200 file: 0.
Direct resource response statuses: {202: 3}.
Resources successfully sampled through the documented DataStore API: 3.
Complete tables exported through the documented DataStore API: 3.
Observed formats: {'CSV': 3}.

| Dataset | Organization | Rows | Fields |
|---|---|---:|---:|
| יבואני מזון בעלי תעודות רישום יבואן בתוקף | משרד הבריאות | 3,075 | 11 |
| יצרני ועסקי מזון בעלי רישיון יצרן | משרד הבריאות | 4,995 | 12 |
| נקודות מכירה ומחירים מרביים של מוצרי מזון מיובאים | משרד הכלכלה והתעשייה | 627 | 10 |

A resource counts as production-ready only after verifying its URL, licence, update timestamp, schema, and whether the resource is current or merely archival.

## 3. RSS/XML/JSON feeds

FCS feed-style links explicitly advertised by the inspected public HTML: 0.
FCS robots status: 200; returned application shell: True.
FCS sitemap status: 200; returned application shell: True.
The full observations are stored in `data/metadata/feed_discovery.json`.

The existence of JSON responses in a browser session is not treated as a supported feed unless an official page or owner documents that use.

## 4. Automated-access policy

DataGov documentation status in the plain HTTP collector: 202; terms status: 202.
The browser-indexed official documentation and licence pages exist, and the documented CKAN API calls themselves succeeded; non-standard frontend responses in the plain HTTP collector are an acquisition quirk, not evidence that DataGov lacks documentation.
gov.il terms status from the non-browser collector: 403.

DataGov is the preferred channel because it explicitly documents API consumption and dataset licensing. Preserve the applicable licence and retrieval time with every snapshot, identify the source, avoid misleading presentation, and do not process personal information outside the licence and applicable law.

For FCS/gov.il pages, use only the interfaces and instructions the site provides. Do not bypass authentication, WAF restrictions, CAPTCHAs, or other controls. A production crawler still needs a documented permission basis, conservative rate limits, caching, identifiable user agent, and a takedown/change process.

## Evidence files

- `data/metadata/open_data_candidates.json`
- `data/metadata/feed_discovery.json`
- `data/raw/access_audit/datagov/`
- `data/raw/access_audit/discovery/`
- `data/metadata/fcs_frontend_findings.json`
- `data/metadata/source_manifest.jsonl`

## Remaining uncertainty

This audit can establish what is publicly documented today. It cannot turn an undocumented FCS endpoint into a supported contract. Written owner confirmation remains the final check for endpoint stability, rate limits, notification of breaking changes, and commercial RAG reuse when no published licence or API policy covers the interface.

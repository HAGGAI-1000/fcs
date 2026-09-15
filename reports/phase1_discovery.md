# Phase 1 discovery report

Observed: 2026-09-14 (Asia/Jerusalem)

## Scope and intended first release

The recommended first release covers commercial import into Israel of food not
of animal origin. It should assist with preliminary route classification,
document checklists, labeling research, source discovery, and gap analysis. It
should not submit official forms or claim to issue a binding legal decision.

Animal-origin food, veterinary requirements, personal imports, customs tariff
classification, quotas, and authenticated case-status access remain separate
workstreams.

## FCS portal findings

The public portal is an Angular single-page application.

- Public home: `https://fcs.health.gov.il/`
- Public publication route: `/publicationsCategories/0`
- Separate authenticated portal found in frontend configuration:
  `https://fcsportal.health.gov.il`
- Public configuration identifies a Ministry services API and an Umbraco API.
- The frontend bundle uses a `GetTables` request with function code `94` for
  publication categories and `95` for the selected category's information items.
- Document retrieval is represented by `GetSpecificDocument`, with document type
  `26` and a document GUID.

These endpoints are implementation details and are not documented as a stable
public API. Direct command-line probes were rejected or intercepted while the
catalogue rendered in the in-app browser. A standalone headless Playwright run
also failed to receive the catalogue rows. The supplied browser collector is
therefore experimental and opt-in. Production use should obtain Ministry
confirmation or a supported feed before depending on endpoint contracts.

The public catalogue displayed these subjects during inspection:

1. Webinars.
2. Guides.
3. Sample bank-guarantee text for food import.
4. Legislative updates, orders, and notices.
5. Public announcements.
6. Group 1 — contaminants in food.
7. Group 2 — labeling provisions.
8. Group 3 — food improvement agents (FIA).
9. Group 4 — food-contact materials (FCM).
10. Group 5 — other contaminants, substances, and methods.
11. Questions and answers.
12. Hebrew translations of adopted provisions.

The seed inventory in `data/metadata/fcs_publication_inventory.json` records
these browser-verified categories. It is evidence for discovery, not a complete
or stable API export.

## Active source boundary

`config/sources.json` now contains a single manually configured acquisition
source: the public FCS publication catalogue. Additional sources are eligible
only when an FCS publication record directly supplies their exact URL. The
crawler records that relationship in `fcs_direct_references.json`; the referenced
source collector accepts no arbitrary URL input.

The earlier manually curated gov.il, Knesset, Ministry of Economy, and DataGov
targets remain historical discovery evidence only. They are explicitly excluded
from ingestion. See `reports/source_scope_policy.md`.

## Key product requirements discovered

All human-facing application interaction must be in Hebrew. This includes user
questions, answers, follow-up questions, warnings, abstentions, and errors.
Source-language citations may be preserved, while their application explanation
remains Hebrew. Internal code and metadata may remain English.

The assistant needs structured facts before retrieval, including product type,
full ingredients and percentages, target population, intended use, country,
manufacturer and site, processing, storage, animal-derived content, import date,
package/label, and importer status.

The corpus is strongly temporal. Adopted EU provisions, Israeli exceptions, and
transition periods mean that a result can be correct for one date and wrong for
another. Effective-date filtering is therefore a release requirement, not an
optional RAG enhancement.

## Collection risks

- JavaScript rendering and unpublished endpoint contracts.
- Scanned Hebrew PDFs and right-to-left extraction errors.
- Tables and appendices whose row structure is legally significant.
- Multiple copies of a document with unclear amendment status.
- Hebrew translations linked to source-language provisions.
- Informational pages that lag binding legal publications.
- Documents available only inside an authenticated importer account.

## Phase 1 outputs

- Reproducible public-source collector and provenance manifest.
- FCS frontend/bundle discovery script.
- Browser-rendered FCS catalogue collector.
- Direct-FCS-reference manifest and restricted referenced-source collector.
- Machine-enforced source scope and ingestion exclusions.
- Initial legal source hierarchy.
- Curated source registry.
- Fifty-question Hebrew evaluation seed set with automated language checks.
- Verification script for checksums and expected deliverables.

## Exit criteria before Phase 2

1. A domain expert reviews the source hierarchy and question set.
2. Relevant laws, classifications, and procedures directly referenced by FCS
   are captured with their publication provenance.
3. Ministry terms and the permitted browser-assisted access pattern are
   documented.
4. At least one sample from each important PDF type is checked for Hebrew text,
   headings, tables, footnotes, and page-number extraction.
5. Each evaluation question is assigned expected source documents and a
   reviewed reference answer.

## Recommended Phase 2 handoff

Expand the browser crawl across all FCS categories and download the FCS-hosted
documents plus exact eligible references. Build normalized documents and
structured rule records in parallel, then benchmark Hebrew keyword, multilingual
dense, and hybrid retrieval against the evaluation seed set before selecting an
embedding model or vector database. Do not supplement gaps with independently
discovered URLs without an explicit future scope decision.

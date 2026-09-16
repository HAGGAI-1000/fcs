# Evaluation relevance review guide

The 50 Hebrew questions are evaluated against independently reviewed evidence.
The domain expert works in the Hebrew web application, uses human-readable FCS
information, and is never asked to find or enter internal document GUIDs.

## File supplied by the expert

The preferred interface is the static Hebrew application in `review_app/`,
published through GitHub Pages. It presents one question at a time, supports an
arbitrary number of source records per question, and saves drafts locally in
the browser.

The expert returns one file: `eval_relevance_expert.json`. It is both the
portable backup and the canonical review handoff. Its structure uses:

- compact question IDs and English machine-field names;
- Hebrew question and reference-answer text;
- stable English outcome and approval enum values; and
- a nested `sources` array under each question.

Nesting removes the need for separate question and source tables and avoids
repeating the full question for every accepted source. The expert still records
the exact FCS document title, relevant pages, displayed date, FCS URL, and
optional notes. The JSON contains no document GUIDs.

The expert searches the FCS website independently. Retrieval candidates are not
provided at any point, and there is no retrieval-assisted second pass. A
document catalogue is not required.

## Review outcomes

The Hebrew interface presents these choices while the JSON stores the stable
values shown in parentheses:

- `טרם נבדק` (`not_reviewed`)
- `נמצא מקור מתאים` (`source_found`)
- `לא נמצא מקור לאחר חיפוש` (`source_not_found`)
- `נדרש מקור מחוץ לאתר FCS` (`requires_non_fcs_source`)
- `לא ודאי` (`uncertain`)

Failure to find a source is not automatically an out-of-scope decision. Reviews
marked `source_not_found` or `uncertain` must remain `pending` until adjudicated.
A reviewer may set `review_status=approved` only when a source-backed answer is
complete or when the need for evidence outside the FCS scope has itself been
established.

## Validating and using the returned JSON

Place the returned file at
`data/metadata/eval_relevance_expert.json`, then validate document mapping:

```powershell
.\.venv\Scripts\python.exe .\scripts\import_expert_relevance.py
```

The mapper resolves each exact human-readable document title, optionally
narrowed by date, against `data/metadata/fcs_document_downloads.json`. It
validates that provided URLs use `fcs.health.gov.il`. Missing and ambiguous
matches stop with an error; the script never guesses a GUID or writes a derived
label file.

After resolving any reported issues, run `run_phase2b.ps1`. Evaluation reads the
same expert JSON, maps sources to GUIDs in memory, and calculates document
Recall@5 and MRR@10 for approved questions with expected FCS documents. The
report records the SHA-256 checksum of the exact expert-review file used.

`data/processed/retrieval_candidates.jsonl` is internal diagnostic output. It
contains full BM25, dense, and hybrid results and is not part of the reviewer
workflow or an additional source of relevance truth.

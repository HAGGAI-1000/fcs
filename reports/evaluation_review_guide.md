# Evaluation relevance review guide

The 50 Hebrew questions are evaluated against independently reviewed evidence.
The domain expert works with human-readable FCS information and is never asked
to find or enter internal document GUIDs.

## Files supplied to the expert

- `data/metadata/eval_relevance_expert_he.csv` contains one row per question.
  The expert records the review outcome, Hebrew reference answer, notes, and
  approval status.
- `data/metadata/eval_relevance_expert_sources_he.csv` contains one blank source
  row per question. The expert records the exact FCS document title, relevant
  pages, displayed publication/update date, and FCS URL. Additional accepted
  documents are added as additional rows with the exact same question text.
- `data/metadata/eval_relevance_instructions_he.txt` contains the short Hebrew
  instructions to send with both CSV files.

The expert searches the FCS website independently. Do not provide retrieval
candidates during the first pass. A document catalogue is not required, and
the expert does not need to understand the crawler's GUIDs.

The preferred interface is the Hebrew static application in `review_app/`,
published through GitHub Pages. It combines the two logical tables in one form,
supports an arbitrary number of source rows per question, saves drafts locally,
and exports the two CSV files described above. The standalone CSV templates
remain supported as a fallback.

## Review outcomes

The question-level file accepts these Hebrew outcomes:

- `נמצא מקור מתאים`
- `לא נמצא מקור לאחר חיפוש`
- `נדרש מקור מחוץ לאתר FCS`
- `לא ודאי`
- `טרם נבדק`

Failure to find a source is not automatically an out-of-scope decision. Rows
marked `לא נמצא מקור לאחר חיפוש` or `לא ודאי` must remain pending until they
are adjudicated. An expert may set `סטטוס_בדיקה=מאושר` only when a source-backed
answer is complete or when the need for evidence outside the FCS scope has
itself been established.

## Mapping the returned files

After the expert returns both files, validate the document mapping without
writing the compact labels:

```powershell
.\.venv\Scripts\python.exe .\scripts\import_expert_relevance.py --check
```

The mapper resolves an exact human-readable document title, optionally narrowed
by date, against `data/metadata/fcs_document_downloads.json`. It validates that
provided URLs use `fcs.health.gov.il`. Missing and ambiguous matches stop with
an error; the script never guesses a GUID.

After resolving any reported issues, create the machine-readable labels:

```powershell
.\.venv\Scripts\python.exe .\scripts\import_expert_relevance.py
```

This writes `data/metadata/eval_relevance.csv`, which keeps compact question IDs
and internal document GUIDs for the evaluator. Pending expert rows remain
pending and do not contribute to Recall or MRR.

## Second-pass completeness check

Only after the independent first pass may the reviewer use
`data/processed/eval_candidate_review.csv`. It contains an alphabetically
ordered, unranked pool drawn from BM25, dense, and hybrid results. It omits
retrieval method, rank, and GUID so it can be used to check for missed evidence
without asking the expert to accept the system's output as truth.

After approved labels have been imported, rerun `run_phase2b.ps1`. The evaluation
report will calculate document Recall@5 and MRR@10 for approved questions that
have expected FCS documents.

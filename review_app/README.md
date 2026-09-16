# Hebrew expert review app

This static, backend-free GitHub Pages application supports independent domain
review of the 50 Hebrew evaluation questions.

## Reviewer workflow

1. Open the published application.
2. Search the FCS website independently for each question.
3. Record the outcome, Hebrew reference answer, and any number of supporting
   source rows.
4. Press the save button at the bottom of the question. The app validates that
   question, marks it approved, and stores a recoverable IndexedDB snapshot.
   Editing an approved question returns it to draft status until it is saved
   again.
5. At completion, export and return the single results file,
   `eval_relevance_expert.json`.

Every edit is also saved automatically to `localStorage`, so an unfinished
draft survives navigation and browser restarts. The recovery dialog lists up to
20 full-state snapshots created by successful question saves and imports. A
pre-restore snapshot is created before any older version is restored. Both the
draft and snapshots remain local to the current browser profile and device and
can be removed by clearing site data.

The exported results file is the required transfer and handoff mechanism for
another browser, device, or the evaluation pipeline. It is not described as an
optional backup control in the interface.

The app never exposes internal GUIDs or retrieval candidates. The JSON uses
compact question IDs, English machine-field names and English enum values while
retaining the Hebrew question and answer text. Sources are nested under their
question, so question text is not repeated for each source. The same file can be
imported back into the app and is accepted by
`scripts/import_expert_relevance.py`.

## Local preview

```powershell
Set-Location C:\projects\fcs\review_app
..\.venv\Scripts\python.exe -m http.server 8765
```

Open `http://127.0.0.1:8765/`.

## Question synchronization

After changing `data/metadata/eval_questions.json`, rebuild the static question
file and run the app tests:

```powershell
.\.venv\Scripts\python.exe .\scripts\build_review_app_questions.py
.\.venv\Scripts\python.exe .\scripts\test_review_app.py
```

GitHub Pages deployment also runs the synchronization test and refuses to
publish a stale question file.

# Hebrew expert review app

This static, backend-free GitHub Pages application supports independent domain
review of the 50 Hebrew evaluation questions.

## Reviewer workflow

1. Open the published application.
2. Search the FCS website independently for each question.
3. Record the outcome, Hebrew reference answer, and any number of supporting
   source rows.
4. Export `eval_relevance_expert.json` periodically. Browser autosave is local
   to one browser profile and device.
5. At completion, return that single JSON file.

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

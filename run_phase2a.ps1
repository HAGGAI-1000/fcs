param(
    [string]$ProjectRoot = "C:\projects\fcs",
    [switch]$DownloadReferencedSources
)

$ErrorActionPreference = "Stop"
$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Project virtual environment not found: $python"
}

& $python -B (Join-Path $ProjectRoot "scripts\test_phase2a.py")
if ($LASTEXITCODE -ne 0) {
    throw "Phase 2A regression checks failed"
}

& $python (Join-Path $ProjectRoot "scripts\classify_references.py") --project-root $ProjectRoot

if ($DownloadReferencedSources) {
    & $python (Join-Path $ProjectRoot "scripts\collect_referenced_sources.py") `
        --project-root $ProjectRoot --refresh
    if ($LASTEXITCODE -ne 0) {
        throw "Direct-reference collection completed with errors"
    }
}

& $python (Join-Path $ProjectRoot "scripts\extract_documents.py") --project-root $ProjectRoot
if ($LASTEXITCODE -ne 0) {
    throw "PDF extraction completed with document-level errors"
}

& $python (Join-Path $ProjectRoot "scripts\validate_extraction.py") --project-root $ProjectRoot
if ($LASTEXITCODE -ne 0) {
    throw "Extraction validation failed"
}

Write-Host "Phase 2A extraction and validation completed successfully."

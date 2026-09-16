param(
    [string]$ProjectRoot = "C:\projects\fcs",
    [switch]$SkipIndexBuild
)

$ErrorActionPreference = "Stop"
$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Project virtual environment not found: $python"
}

& $python -B (Join-Path $ProjectRoot "scripts\test_phase2b.py")
if ($LASTEXITCODE -ne 0) {
    throw "Phase 2B regression checks failed"
}

& $python -B (Join-Path $ProjectRoot "scripts\build_chunks.py") --project-root $ProjectRoot
if ($LASTEXITCODE -ne 0) {
    throw "Chunk construction failed"
}

if (-not $SkipIndexBuild) {
    & $python -B (Join-Path $ProjectRoot "scripts\build_indexes.py") --project-root $ProjectRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Index construction failed"
    }
}

& $python -B (Join-Path $ProjectRoot "scripts\evaluate_retrieval.py") --project-root $ProjectRoot
if ($LASTEXITCODE -ne 0) {
    throw "Retrieval evaluation failed"
}

& $python -B (Join-Path $ProjectRoot "scripts\validate_phase2b.py") --project-root $ProjectRoot
if ($LASTEXITCODE -ne 0) {
    throw "Phase 2B validation failed"
}

Write-Host "Phase 2B chunking, indexing, and retrieval diagnostics completed successfully."

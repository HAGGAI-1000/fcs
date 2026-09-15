[CmdletBinding()]
param(
    [switch]$Refresh,
    [switch]$RunBrowserCollection,
    [switch]$HeadlessBrowserCollection,
    [switch]$DownloadReferencedSources
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot

$refreshArgs = @()
if ($Refresh) {
    $refreshArgs += '--refresh'
}

python .\scripts\discover_fcs_bundle.py --project-root $projectRoot @refreshArgs
python .\scripts\collect_sources.py --project-root $projectRoot @refreshArgs

if ($RunBrowserCollection) {
    $browserArgs = @('--project-root', $projectRoot, '--browser-channel', 'chrome')
    if (-not $HeadlessBrowserCollection) {
        $browserArgs += '--show-browser'
    }
    python .\scripts\collect_fcs_publications.py @browserArgs
} else {
    Write-Host 'Skipping optional browser catalogue collection. Pass -RunBrowserCollection to enable it.'
}

if ($DownloadReferencedSources) {
    python .\scripts\collect_referenced_sources.py --project-root $projectRoot @refreshArgs
}

python .\scripts\verify_phase1.py --project-root $projectRoot

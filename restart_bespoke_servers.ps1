Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$stopScript = Join-Path $PSScriptRoot "stop_bespoke_servers.ps1"
$startScript = Join-Path $PSScriptRoot "start_bespoke_servers.ps1"

Write-Host "Restarting bespoke services..."

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $stopScript
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $startScript
exit $LASTEXITCODE

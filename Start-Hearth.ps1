$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
Write-Host 'Opening your local Hearth test build…'
uv run --group appliance python scripts/start_local.py
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Setup did not finish. See DEVELOPMENT.md for recovery instructions.'
    Read-Host 'Press Enter to close'
}

$ErrorActionPreference = 'Stop'
$katharoPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $katharoPython)) {
    Write-Host 'Install Katharo using the steps in README.md first.'
    exit 1
}
& $katharoPython -m katharo.server

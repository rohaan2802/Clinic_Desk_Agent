# Run ClinicDesk from any working directory.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$py = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $py)) {
    Write-Host 'Creating virtualenv...'
    python -m venv .venv
    & $py -m pip install -r requirements.txt
}

if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot '.env'))) {
    $example = Join-Path $PSScriptRoot '.env.example'
    if (Test-Path -LiteralPath $example) {
        Copy-Item -LiteralPath $example -Destination (Join-Path $PSScriptRoot '.env')
    }
}

& $py (Join-Path $PSScriptRoot 'run.py')

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath ".venv")) {
    py -3.12 -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e ".[dev]"

Write-Host "Bootstrap complete. Copy .env.example to .env and add the Schwab app settings."

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath ".venv")) {
    $created = $false
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($version in @("3.12", "3.13", "3.14")) {
            & py "-${version}" -c "import sys" *> $null
            if ($LASTEXITCODE -eq 0) {
                & py "-${version}" -m venv .venv
                if ($LASTEXITCODE -ne 0) {
                    throw "Python ${version} could not create .venv."
                }
                $created = $true
                break
            }
        }
    }
    if (-not $created -and (Get-Command python -ErrorAction SilentlyContinue)) {
        & python -c "import sys; raise SystemExit(0 if (3, 12) <= sys.version_info[:2] <= (3, 14) else 1)" *> $null
        if ($LASTEXITCODE -eq 0) {
            & python -m venv .venv
            if ($LASTEXITCODE -ne 0) {
                throw "Python could not create .venv."
            }
            $created = $true
        }
    }
    if (-not $created) {
        throw "Install Python 3.12, 3.13, or 3.14, then run bootstrap again."
    }
}

& .\.venv\Scripts\python.exe -c "import sys; raise SystemExit(0 if (3, 12) <= sys.version_info[:2] <= (3, 14) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "The existing .venv does not use supported Python 3.12, 3.13, or 3.14."
}
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "pip could not be upgraded."
}
& .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
if ($LASTEXITCODE -ne 0) {
    throw "Incoooming dependencies could not be installed."
}

Write-Host "Bootstrap complete. Try the demo with .\scripts\run-demo.cmd."
Write-Host "For CSV files, use .\scripts\run-local.cmd. Only Schwab setup needs a .env file; see docs\getting-started-schwab.md."

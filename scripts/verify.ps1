$ErrorActionPreference = "Stop"

& .\.venv\Scripts\ruff.exe check .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& .\.venv\Scripts\ruff.exe format --check .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& .\.venv\Scripts\mypy.exe src
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$pytestTemp = Join-Path (
    [System.IO.Path]::GetTempPath()
) ("incoooming-pytest-{0}-{1}" -f $PID, [guid]::NewGuid().ToString("N"))
& .\.venv\Scripts\pytest.exe -p no:cacheprovider "--basetemp=$pytestTemp"
exit $LASTEXITCODE

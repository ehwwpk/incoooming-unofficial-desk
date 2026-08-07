$ErrorActionPreference = "Stop"

& .\.venv\Scripts\ruff.exe check .
& .\.venv\Scripts\ruff.exe format --check .
& .\.venv\Scripts\mypy.exe src
& .\.venv\Scripts\pytest.exe --basetemp=.pytest-tmp

$ErrorActionPreference = "Stop"
$env:SCHWAB_DASHBOARD_DEMO_MODE = "true"
& .\.venv\Scripts\schwab-dashboard.exe demo

param(
    [switch]$Restart,
    [switch]$Background
)

$ErrorActionPreference = "Stop"
$dashboard = (Resolve-Path -LiteralPath ".\.venv\Scripts\schwab-dashboard.exe").Path
$runtimeConfig = (& $dashboard runtime-config | ConvertFrom-Json)
$settingsHost = [string]$runtimeConfig.host
$settingsPort = [int]$runtimeConfig.port
$baseUrl = "http://${settingsHost}:${settingsPort}"
$healthUrl = "${baseUrl}/api/v1/health/live"
$expectedBuild = [string]$runtimeConfig.build_id
$health = $null

try {
    $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2 -Headers @{ Accept = "application/json" }
} catch {
    $health = $null
}

if ($null -ne $health) {
    $verified = $health.app -eq "incoooming-local-desk" -and $null -ne $health.pid
    if (-not $verified) {
        Write-Error "Port ${settingsPort} answered, but it did not identify itself as Incoooming. Nothing was stopped."
    }
    $stale = $health.build_id -ne $expectedBuild
    if (-not $Restart -and -not $stale) {
        Write-Host "Incoooming is already online at ${baseUrl} (PID $($health.pid))." -ForegroundColor Green
        exit 0
    }
    $reason = if ($Restart) { "restart requested" } else { "older local code detected" }
    try {
        $confirmedHealth = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2 -Headers @{ Accept = "application/json" }
    } catch {
        Write-Error "Incoooming changed state before restart. Nothing was stopped; run the shortcut again."
    }
    if (
        $confirmedHealth.app -ne "incoooming-local-desk" -or
        [int]$confirmedHealth.pid -ne [int]$health.pid
    ) {
        Write-Error "The listener changed identity before restart. Nothing was stopped."
    }
    Write-Host "Stopping verified Incoooming PID $($health.pid): ${reason}." -ForegroundColor Yellow
    Stop-Process -Id ([int]$health.pid) -ErrorAction Stop
    $deadline = (Get-Date).AddSeconds(10)
    do {
        Start-Sleep -Milliseconds 150
        $listener = Get-NetTCPConnection -LocalPort $settingsPort -State Listen -ErrorAction SilentlyContinue
    } while ($listener -and (Get-Date) -lt $deadline)
    if ($listener) {
        Write-Error "Verified Incoooming PID $($health.pid) did not release port ${settingsPort}."
    }
}

$listener = Get-NetTCPConnection -LocalPort $settingsPort -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    $owners = ($listener | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "
    Write-Error "Port ${settingsPort} is held by unverified process PID ${owners}. Incoooming left it alone."
}

& $dashboard db-upgrade
if ($LASTEXITCODE -ne 0) {
    throw "Incoooming could not prepare the local database."
}

if ($Background) {
    Write-Host "Starting Incoooming at ${baseUrl} in the background." -ForegroundColor Green
    $serverPath = (Resolve-Path -LiteralPath ".\.venv\Scripts\schwab-dashboard.exe").Path
    $process = Start-Process `
        -FilePath $serverPath `
        -ArgumentList "serve" `
        -WindowStyle Hidden `
        -PassThru
    $deadline = (Get-Date).AddSeconds(20)
    do {
        Start-Sleep -Milliseconds 250
        try {
            $startedHealth = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2 -Headers @{ Accept = "application/json" }
        } catch {
            $startedHealth = $null
        }
    } while ($null -eq $startedHealth -and (Get-Date) -lt $deadline)
    if (
        $null -eq $startedHealth -or
        $startedHealth.app -ne "incoooming-local-desk" -or
        $startedHealth.build_id -ne $expectedBuild
    ) {
        Write-Error "Incoooming started, but its self-identifying health check did not pass. Run .\scripts\run-local.cmd to see the server log."
    }
    Write-Host "Incoooming is healthy at ${baseUrl} (PID $($startedHealth.pid))." -ForegroundColor Green
    exit 0
}

Write-Host "Starting Incoooming at ${baseUrl}. Keep this window open." -ForegroundColor Green
& .\.venv\Scripts\schwab-dashboard.exe serve

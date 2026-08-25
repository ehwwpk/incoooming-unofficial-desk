param(
    [int]$TimeoutSeconds = 300,
    [switch]$NoBrowser,
    [switch]$NoSync
)

$ErrorActionPreference = "Stop"

function Get-QueryValue {
    param(
        [Uri]$Uri,
        [string]$Name
    )

    foreach ($part in $Uri.Query.TrimStart("?").Split("&", [System.StringSplitOptions]::RemoveEmptyEntries)) {
        $pair = $part.Split("=", 2)
        $key = [System.Net.WebUtility]::UrlDecode($pair[0])
        if ($key -eq $Name -and $pair.Count -eq 2) {
            return [System.Net.WebUtility]::UrlDecode($pair[1])
        }
    }
    return $null
}

$dashboard = (Resolve-Path -LiteralPath ".\.venv\Scripts\schwab-dashboard.exe").Path
$originalClipboard = Get-Clipboard -Raw -ErrorAction SilentlyContinue
$authorizationUrl = (& $dashboard auth-url).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($authorizationUrl)) {
    throw "Incoooming could not create the Schwab authorization URL. Run doctor before retrying."
}

$authorizationUri = [Uri]$authorizationUrl
$expectedCallbackValue = Get-QueryValue -Uri $authorizationUri -Name "redirect_uri"
$expectedCallback = if ($expectedCallbackValue) { [Uri]$expectedCallbackValue } else { $null }
if ($null -eq $expectedCallback) {
    throw "The local Schwab authorization URL did not contain a callback URL."
}

Write-Host "Incoooming is waiting locally for the one-time Schwab callback." -ForegroundColor Yellow
Write-Host "Approve Schwab in the browser. On the final 127.0.0.1 page, press Ctrl+L and Ctrl+C once." -ForegroundColor White
Write-Host "Do not paste the URL anywhere. Incoooming will exchange it immediately." -ForegroundColor DarkGray

try {
    Set-Clipboard -Value " "
    if (-not $NoBrowser) {
        Start-Process -FilePath $authorizationUrl
    }

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $callback = $null
    do {
        Start-Sleep -Milliseconds 100
        $candidate = Get-Clipboard -Raw -ErrorAction SilentlyContinue
        if (-not [string]::IsNullOrWhiteSpace($candidate)) {
            try {
                $candidateUri = [Uri]$candidate.Trim()
                $sameTarget = (
                    $candidateUri.Scheme -eq $expectedCallback.Scheme -and
                    $candidateUri.Host -eq $expectedCallback.Host -and
                    $candidateUri.Port -eq $expectedCallback.Port -and
                    $candidateUri.AbsolutePath -eq $expectedCallback.AbsolutePath
                )
                $candidateCode = Get-QueryValue -Uri $candidateUri -Name "code"
                if ($sameTarget -and -not [string]::IsNullOrWhiteSpace($candidateCode)) {
                    $callback = $candidate.Trim()
                }
            } catch {
                # Ignore unrelated clipboard content while waiting for the exact callback.
            }
        }
    } while ($null -eq $callback -and (Get-Date) -lt $deadline)

    if ($null -eq $callback) {
        throw "No Schwab callback was captured within ${TimeoutSeconds} seconds. Nothing was changed."
    }

    $callback | & $dashboard auth-complete --from-stdin
    if ($LASTEXITCODE -ne 0) {
        throw "Schwab rejected the freshly captured callback. The local token was not replaced."
    }
    Write-Host "Schwab authorization is stored." -ForegroundColor Green

    if (-not $NoSync) {
        & $dashboard sync
        if ($LASTEXITCODE -ne 0) {
            throw "Authorization succeeded, but the first Schwab sync failed. The token remains stored."
        }
        & .\scripts\run-local.ps1 -Restart -Background
        if ($LASTEXITCODE -ne 0) {
            throw "Sync succeeded, but Incoooming did not restart cleanly."
        }
        Write-Host "Incoooming is connected, synced, and back online at http://127.0.0.1:8182/." -ForegroundColor Green
    }
} finally {
    if ($null -eq $originalClipboard) {
        Set-Clipboard -Value " "
    } else {
        Set-Clipboard -Value $originalClipboard
    }
}

<#
Opens Carteira B3: builds the frontend when the sources changed, starts the backend on :8000 (hidden, it
also serves the built UI) and opens the browser. If it is already running, only opens the browser.
Used by the "Carteira B3" desktop shortcut (scripts/install_shortcuts.ps1). Logs: backend\data\logs\
#>
param([switch]$NoBrowser)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$logs = Join-Path $backend "data\logs"
$url = "http://127.0.0.1:8000"  # not "localhost": it resolves to ::1 first and times out
New-Item -ItemType Directory -Force $logs | Out-Null

function Test-Up {
    try { (Invoke-WebRequest "$url/api/health" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch { $false }
}

function Show-Error([string]$message) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show($message, "Carteira B3", "OK", "Error") | Out-Null
}

if (-not (Test-Up)) {
    # Rebuild the UI only when something under frontend\src (or the config) is newer than the last build
    $index = Join-Path $frontend "dist\index.html"
    $built = if (Test-Path $index) { (Get-Item $index).LastWriteTime } else { [datetime]::MinValue }
    $sources = @(Get-ChildItem (Join-Path $frontend "src") -Recurse -File) + @(Get-ChildItem $frontend -File)
    $newest = ($sources | Measure-Object LastWriteTime -Maximum).Maximum
    if ($newest -gt $built) {
        $build = Start-Process "cmd.exe" -ArgumentList "/c npm run build > `"$logs\frontend_build.log`" 2>&1" `
            -WorkingDirectory $frontend -WindowStyle Hidden -Wait -PassThru
        if ($build.ExitCode -ne 0) { Show-Error "Falha ao compilar o frontend. Veja $logs\frontend_build.log"; exit 1 }
    }

    $uv = $null
    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($cmd) { $uv = $cmd.Source }
    if (-not $uv) {
        $found = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\astral-sh.uv_*\uv.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) { $uv = $found.FullName }
    }
    if (-not $uv) { Show-Error "uv nao encontrado (winget install astral-sh.uv)."; exit 1 }

    Start-Process $uv -ArgumentList "run python -m uvicorn app.main:app --port 8000" -WorkingDirectory $backend `
        -WindowStyle Hidden -RedirectStandardOutput "$logs\backend.out.log" -RedirectStandardError "$logs\backend.log"

    $deadline = (Get-Date).AddSeconds(90)
    while (-not (Test-Up)) {
        if ((Get-Date) -gt $deadline) { Show-Error "O backend nao respondeu. Veja $logs\backend.log"; exit 1 }
        Start-Sleep -Milliseconds 500
    }
}

if (-not $NoBrowser) { Start-Process $url }

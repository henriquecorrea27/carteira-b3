<#
Registers the Carteira B3 jobs in the Windows Task Scheduler (current user, no admin needed).

  "Carteira B3 - Relatorio diario"  business days at REPORT_TIME (backend/.env, default 19:00) and at logon.
      Runs app.jobs.daily_report: refreshes prices, provents and decisions, then sends the Discord report.
      It only sends what is due, so extra runs are harmless; a missed day is sent late at the next run.
  "Carteira B3 - Dados CVM"         every 4 weeks, Saturday 10:00. Runs app.jobs.ingest_cvm.

Both start as soon as possible when the computer was off at the scheduled time.

Usage (from the repository root):
  powershell -ExecutionPolicy Bypass -File scripts\register_tasks.ps1          # create / update
  powershell -ExecutionPolicy Bypass -File scripts\register_tasks.ps1 -Remove  # remove

Logs: backend\data\logs\daily_report.log
#>
param([switch]$Remove)
$ErrorActionPreference = "Stop"

$backend = Join-Path (Split-Path $PSScriptRoot -Parent) "backend"
$reportTask = "Carteira B3 - Relatorio diario"
$cvmTask = "Carteira B3 - Dados CVM"

if ($Remove) {
    foreach ($name in @($reportTask, $cvmTask)) {
        try { Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction Stop; Write-Host "Removida: $name" } catch {}
    }
    return
}

$uv = $null
$cmd = Get-Command uv -ErrorAction SilentlyContinue
if ($cmd) { $uv = $cmd.Source }
if (-not $uv) {
    $found = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\astral-sh.uv_*\uv.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { $uv = $found.FullName }
}
if (-not $uv) { throw "uv not found (install with: winget install astral-sh.uv)" }

$time = "19:00"
$envFile = Join-Path $backend ".env"
if (Test-Path $envFile) {
    $line = Get-Content $envFile | Where-Object { $_ -match '^\s*REPORT_TIME\s*=\s*(\d{1,2}:\d{2})' } | Select-Object -First 1
    if ($line) { $time = $Matches[1] }
}

function New-JobAction([string]$module) {
    # conhost --headless runs the console job without flashing a window
    New-ScheduledTaskAction -Execute "conhost.exe" -Argument "--headless `"$uv`" run python -m $module" -WorkingDirectory $backend
}

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew

$weekdays = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At $time
$logon = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$logon.Delay = "PT3M"  # let the network come up first

Register-ScheduledTask -TaskName $reportTask -Action (New-JobAction "app.jobs.daily_report") `
    -Trigger @($weekdays, $logon) -Settings $settings -Force `
    -Description "Carteira B3: atualiza cotacoes/proventos/decisoes e envia o relatorio diario ao Discord." | Out-Null
Write-Host "Registrada: $reportTask (dias uteis as $time e ao entrar no Windows)"

$monthly = New-ScheduledTaskTrigger -Weekly -WeeksInterval 4 -DaysOfWeek Saturday -At "10:00"
Register-ScheduledTask -TaskName $cvmTask -Action (New-JobAction "app.jobs.ingest_cvm") `
    -Trigger $monthly -Settings $settings -Force `
    -Description "Carteira B3: baixa os dados abertos da CVM e recalcula os indicadores." | Out-Null
Write-Host "Registrada: $cvmTask (a cada 4 semanas, sabado as 10:00)"

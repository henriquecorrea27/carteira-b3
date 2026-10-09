<#
Stops Carteira B3: the backend on :8000 and, if running, its Vite dev server (:5180/:5181).
Only processes of this app are stopped (other projects using these ports are left alone).
Used by the "Parar Carteira B3" desktop shortcut.
#>
$root = Split-Path $PSScriptRoot -Parent
foreach ($port in 8000, 5180, 5181) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($_.OwningProcess)"
        $cmd = "$($proc.CommandLine)"
        $ours = if ($port -eq 8000) { $cmd -like "*uvicorn app.main:app*--port 8000*" } else { $cmd -like "*$root*" }
        if ($ours) {
            try { Stop-Process -Id $proc.ProcessId -Force -Confirm:$false -ErrorAction Stop } catch {}
        }
    }
}

<#
Creates the desktop shortcuts "Carteira B3" (opens the app) and "Parar Carteira B3" (stops it).
  powershell -ExecutionPolicy Bypass -File scripts\install_shortcuts.ps1
#>
$ErrorActionPreference = "Stop"
$desktop = [Environment]::GetFolderPath("Desktop")
$shell = New-Object -ComObject WScript.Shell
$icon = Join-Path $PSScriptRoot "carteira.ico"

function New-Shortcut([string]$name, [string]$script, [string]$description) {
    $link = $shell.CreateShortcut((Join-Path $desktop "$name.lnk"))
    # conhost --headless runs PowerShell without opening a console window
    $link.TargetPath = "$env:SystemRoot\System32\conhost.exe"
    $link.Arguments = "--headless powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $PSScriptRoot $script)`""
    $link.WorkingDirectory = Split-Path $PSScriptRoot -Parent
    $link.IconLocation = "$icon,0"
    $link.Description = $description
    $link.Save()
    Write-Host "Atalho criado: $desktop\$name.lnk"
}

New-Shortcut "Carteira B3" "start_app.ps1" "Abre a Carteira B3 no navegador"
New-Shortcut "Parar Carteira B3" "stop_app.ps1" "Encerra o servidor da Carteira B3"

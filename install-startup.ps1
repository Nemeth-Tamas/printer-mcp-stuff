# Run once from an elevated Windows PowerShell.
$ErrorActionPreference = 'Stop'
$who = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($who)
if (!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Run PowerShell as Administrator.' }
Set-Location $PSScriptRoot
if (!(Test-Path '.venv\Scripts\python.exe')) { throw 'Run start-api.ps1 once to install dependencies.' }
if (!(Test-Path '.env')) { throw 'Configure .env before installing startup tasks.' }
$runner = Join-Path $PSScriptRoot 'run-server.ps1'
foreach ($service in @('api','mcp')) {
  $name = 'Cellnet-Birch-' + $service.ToUpperInvariant()
  $arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $runner + '" -Mode ' + $service
  $action = New-ScheduledTaskAction -Execute (Join-Path $PSHOME 'powershell.exe') -Argument $arguments -WorkingDirectory $PSScriptRoot
  $trigger = New-ScheduledTaskTrigger -AtStartup
  $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable
  $system = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
  Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Principal $system -Force | Out-Null
  Write-Host "Installed $name"
}
Write-Host 'Startup tasks installed. Stop interactive servers before starting tasks.'
Write-Host 'Run: Start-ScheduledTask -TaskName Cellnet-Birch-API'
Write-Host 'Run: Start-ScheduledTask -TaskName Cellnet-Birch-MCP'

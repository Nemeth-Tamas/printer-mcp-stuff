param([ValidateSet('api','mcp')][string]$Mode = 'api')
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (!(Test-Path $python)) { throw 'Python venv missing. Run start-api.ps1 interactively first.' }
if (!(Test-Path '.env')) { throw 'Missing .env configuration.' }
foreach ($line in Get-Content '.env') {
  if ($line -match '^\s*([^#=\s]+)=(.*)$') {
    [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim(), 'Process')
  }
}
if (!$env:PRINT_API_TOKEN -or $env:PRINT_API_TOKEN -eq 'REPLACE_WITH_A_LONG_RANDOM_SECRET') { throw 'Invalid PRINT_API_TOKEN' }
if (!$env:PRINTER_NAME) { throw 'Missing PRINTER_NAME' }
$hostAddress = if ($env:PRINT_BIND) { $env:PRINT_BIND } else { '127.0.0.1' }
$target = if ($Mode -eq 'api') { 'bridge.api:app' } else { 'bridge.mcp_http:app' }
$port = if ($Mode -eq 'api') { 8765 } else { 8766 }
& $python -m uvicorn $target --host $hostAddress --port $port

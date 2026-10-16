$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (!(Test-Path '.venv')) { py -3 -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (Test-Path '.env') {
    foreach ($line in Get-Content '.env') {
        if ($line -match '^\s*([^#=\s]+)=(.*)$') {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim(), 'Process')
        }
    }
}
if (!$env:PRINT_API_TOKEN -or $env:PRINT_API_TOKEN -eq 'REPLACE_WITH_A_LONG_RANDOM_SECRET') { throw 'Set PRINT_API_TOKEN in .env first.' }
if (!$env:PRINTER_NAME) { throw 'Set PRINTER_NAME in .env first.' }
$bindAddress = if ($env:PRINT_BIND) { $env:PRINT_BIND } else { '127.0.0.1' }
& .\.venv\Scripts\python.exe -m uvicorn bridge.api:app --host $bindAddress --port 9005

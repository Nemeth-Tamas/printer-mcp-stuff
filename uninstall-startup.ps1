# Run as Administrator.
$ErrorActionPreference = 'Stop'
foreach ($name in @('Cellnet-Birch-API','Cellnet-Birch-MCP')) {
  Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
}
Write-Host 'Birch startup tasks removed.'

# Echo Birch Print Bridge

Windows print bridge for the **Birch CP-Q1UN** thermal printer. Includes an authenticated FastAPI HTTP endpoint for the future Ubuntu/Docker booking application and an MCP **stdio** adapter for Echo.

## Install on Echo's Windows machine

Install Python 3.11+ and the Windows Birch driver, and confirm a Windows test page prints.

```powershell
git clone https://github.com/Nemeth-Tamas/printer-mcp-stuff.git
cd printer-mcp-stuff
Get-Printer | Select-Object Name
Copy-Item .env.example .env
notepad .env
```

In `.env`, set `PRINTER_NAME` to the exact Windows printer queue name and `PRINT_API_TOKEN` to a long random token. Keep the file local; it is gitignored.

```powershell
powershell -ExecutionPolicy Bypass -File .\start-api.ps1
```

Test locally via `http://127.0.0.1:8765/health`. For the Ubuntu machine to connect, set `PRINT_BIND=0.0.0.0` and create a Windows Firewall rule restricted to the Ubuntu machine's IP for TCP 8765. Never expose this API to the public Internet.

## HTTP API

- `GET /health` — basic liveness (no authentication)
- `GET /printers` — installed Windows queues (Bearer token)
- `POST /print/text` — JSON `{"text":"Árvíztűrő tükörfúrógép","cut":true,"beep":false}` (Bearer token)

PowerShell example:

```powershell
$token = (Get-Content .env | Where-Object { $_ -match '^PRINT_API_TOKEN=' }) -replace '^PRINT_API_TOKEN=', ''
Invoke-RestMethod -Uri http://127.0.0.1:8765/print/text -Method Post -Headers @{Authorization="Bearer $token"} -ContentType 'application/json; charset=utf-8' -Body '{"text":"Cellnet printer test","cut":true,"beep":false}'
```

## MCP (stdio)

Run `python -m bridge.mcp_server` using the **same Python environment** as the API. Echo's MCP client must launch that command and pass environment variables `PRINT_API_URL` and `PRINT_API_TOKEN`. The bridge offers `print_receipt` and `available_printers`. MCP is not exposed on the HTTP port.

## Important hardware caveat

Receipt output is rendered to a 576-dot ESC/POS raster so Hungarian accents survive. This sends **RAW ESC/POS** via the Windows queue. The installed driver and printer must allow RAW pass-through. A Windows test page alone does not verify RAW command support. Cutter and beeper commands are tentative until tested on your specific CP-Q1UN firmware. Printing a job means it was queued, not that paper definitely emerged.

No secrets are committed. Keep the listener on localhost until ready for LAN testing.

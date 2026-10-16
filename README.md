# Echo Birch Print Bridge

Windows print bridge for the **Birch CP-Q1UN**, used by Echo (MCP) and future Cellnet Booking (REST).

**v0.2.0:** text, QR codes, appointment tickets, adjustable bottom feed; tested on hardware in v0.1.0 for printing, cutter, and beeper. New v0.2.0 functionality has not yet been tested on hardware.

## Windows setup

Install Python 3.11+, Birch printer driver, then:

```powershell
git clone https://github.com/Nemeth-Tamas/printer-mcp-stuff.git
cd printer-mcp-stuff
Copy-Item .env.example .env
notepad .env
powershell -ExecutionPolicy Bypass -File .\start-api.ps1
```

On an existing install, stop the server with Ctrl+C, then `git pull` and restart. Existing `.env` is not overwritten; add `PRINT_BOTTOM_FEED_LINES=4` (or change to 5 if needed). The default is four lines even if omitted.

Use `PRINTER_NAME=CP-Q1UN` (the local Windows queue, not the redirected RDP printer). Set a unique 32-byte random token for `PRINT_API_TOKEN`. Keep the token private and exclude `.env` from Git.

## HTTP API

`GET /health` is unauthenticated. Every other endpoint requires `Authorization: Bearer <token>`.

- `GET /printers`: list Windows queues.
- `POST /print/text`: `{"text":"ÁRVÍZTŰRŐ TÜKÖRFÚRÓGÉP","cut":true,"beep":true}`
- `POST /print/qr`: `{"data":"https://cellnet.hu","caption":"Scan me","module_size":5,"cut":true,"beep":false}`
- `POST /print/appointment`: `{"customer":"Kovács Péter","starts_at":"2026-10-19 10:00","service":"Laptop bevizsgálás","notes":"Átvétel a műhelyben","reference":"CEL-123","cut":true,"beep":true}`

All print endpoints return a Windows job ID and queued status, *not proof the physical print completed*. Date/time is a display string, not a calendar integration yet.

PowerShell quick test (in project directory):

```powershell
$token = (Get-Content .env | Where-Object { $_ -match '^PRINT_API_TOKEN=' }) -replace '^PRINT_API_TOKEN=', ''
$payload = '{"data":"https://github.com/Nemeth-Tamas/printer-mcp-stuff","caption":"Echo QR test","cut":true,"beep":true}'
Invoke-RestMethod -Uri http://127.0.0.1:8765/print/qr -Method Post -Headers @{Authorization="Bearer $token"} -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($payload))
```

## Echo MCP adapter (stdio)

The MCP adapter is *not* an HTTP MCP server; it talks to the Windows HTTP API. It can run on Echo's own machine, including Linux, with Python and dependencies `mcp` and `httpx`. Run `python -m bridge.mcp_server` with these environment variables:

- `PRINT_API_URL=http://WINDOWS_WIREGUARD_IP:8765`
- `PRINT_API_TOKEN=<same token as Windows server>`

Configure Echo's MCP client to launch the Python module using the full Python executable path and the repository as working directory. MCP tools: `print_receipt`, `print_qr_code`, `print_appointment`, `available_printers`.

## Networking and security

Set `PRINT_BIND=0.0.0.0` only when remote clients need access. This binds every reachable interface, **not just WireGuard**. In particular, the API is unencrypted HTTP (bearer tokens travel in HTTP headers), so only use it over trusted LAN or an encrypted WireGuard tunnel, and limit inbound reachability on the host or upstream network. Do not port-forward TCP 8765 to the public internet. An exposed print endpoint permits arbitrary receipt printing by token holders.

## Hardware notes

UTF-8 text is rendered to a 576-dot-wide raster before sending RAW ESC/POS via the Windows spooler. Cutter `GS V` and beeper `ESC B` worked on the user's CP-Q1UN in v0.1.0. Images and QR codes require v0.2.0 hardware verification. For QR print size problems, reduce `module_size`. Configurable bottom paper feed: `PRINT_BOTTOM_FEED_LINES` 0–12.

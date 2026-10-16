# Echo: remote MCP setup

This project provides a **Streamable HTTP MCP** service on the Windows PC, separate from the REST API.

- REST API: `http://WINDOWS_WG_IP:8765` for the future Docker booking app.
- MCP: `http://WINDOWS_WG_IP:8766/mcp/` for Echo.
- Both endpoints use the `PRINT_API_TOKEN` bearer token from the Windows machine's `.env` file.

## Start on Windows

Pull the latest files and stop/restart the existing API after changes. For the MCP service, open a **second PowerShell session**:

```powershell
cd C:\path\to\printer-mcp-stuff
powershell -ExecutionPolicy Bypass -File .\start-mcp.ps1
```

The server prints `Uvicorn running on http://0.0.0.0:8766` if `PRINT_BIND=0.0.0.0`.

## Connect Echo

Use transport **Streamable HTTP** (not SSE or stdio), URL `http://WINDOWS_WG_IP:8766/mcp/`, and header:

```
Authorization: Bearer YOUR_PRINT_API_TOKEN
```

Available tools: `print_receipt`, `print_qr_code`, `print_appointment`, `available_printers`.

A GET in the browser will not work without the bearer header, and MCP requires an MCP-aware client rather than browsing the URL. The server is stateless so it works with HTTP MCP clients without a persistent session.

**Network security:** the listener is HTTP, not HTTPS. Expose it only over trusted encrypted WireGuard links. Binding `0.0.0.0` exposes the port on **all** reachable host interfaces, not only WireGuard. Without a host firewall, protect both TCP 8765 and 8766 at network boundaries and never port-forward them to the public internet.

## Troubleshooting

- HTTP 401: incorrect or missing bearer token.
- Connection refused/timeout: wrong host, routing, or service not started.
- HTTP 404: use the full `/mcp/` path including trailing slash.
- Ensure Echo's remote MCP client supports Streamable HTTP, arbitrary auth headers, and HTTP URLs over your WireGuard tunnel.
- Spooler results mean **queued**, not physical print confirmation.

## Note

The original local stdio MCP adapter remains available if needed, but Echo no longer has to run it. The v0.3 network MCP implementation needs to be tested against Echo's MCP client.

## v0.4 additions

The **Streamable HTTP** endpoint now exposes `print_daily_schedule`, `print_reminder` and `recent_print_jobs` in addition to the original four tools. For example, Echo can call:

```json
{
  "day": "2026-10-19",
  "appointments": [
    {"time": "10:00", "customer": "Kovács Péter", "service": "Laptop bevizsgálás", "notes": "Átvétel"}
  ],
  "cut": true,
  "beep": false
}
```

The daily schedule is **supplied to the MCP tool by Echo**; it doesn't fetch Google Calendar itself. The reminder tool accepts `title`, `message`, optional `when`, and `priority` (`normal` or `urgent`). `recent_print_jobs` returns job timestamps and Windows spooler IDs, not customer details and not confirmation of physical printing.

The REST API also has `POST /print/schedule`, `POST /print/reminder`, and `GET /jobs?limit=20` using the same Bearer token. A local SQLite file stores at most 500 recent print submissions; no message content is retained. The DB is gitignored.

**Updating the Windows host:** stop both uvicorn processes, run `git pull`, then relaunch `start-api.ps1` and `start-mcp.ps1`. Echo should refresh its tool list after reconnecting. These features are code-complete but need live printer verification.

## Windows boot-time startup (v0.6)

API and MCP run independently at boot through Windows Task Scheduler, without an interactive RDP login.

1. `git pull`, then stop the two interactive uvicorn instances.
2. Open **Windows PowerShell as Administrator** in the project folder.
3. Run `powershell -ExecutionPolicy Bypass -File .\install-startup.ps1`.
4. Start them now with `Start-ScheduledTask Cellnet-Birch-API` and `Start-ScheduledTask Cellnet-Birch-MCP`.
5. Verify `Get-ScheduledTask Cellnet-Birch-*` and `http://127.0.0.1:8765/health`; reconnect Echo.

Tasks use **SYSTEM**. Windows printers installed only for the interactive user may not be available under SYSTEM. If printing fails while the endpoints are online, install/share the printer machine-wide or change the task identity to an appropriate service account. Uninstall with `uninstall-startup.ps1` in elevated PowerShell. Startup runner installs no Python packages; dependency updates remain manual via `start-api.ps1`.

## Custom and two-copy printing (v0.6)

`POST /print/appointment` accepts `mode="customer"` (name/time/service/reference, no technician notes) or `mode="technician"` (adds phone and private notes). The Docker booking page has one button per copy. No "Várjuk szeretettel" footer.

Echo's new `print_custom_receipt` tool, and the authenticated REST `POST /print/custom`, accept e.g.:

```json
{"blocks":[
  {"type":"heading","text":"CELLNET"},
  {"type":"text","text":"Árvíztűrő tükörfúrógép"},
  {"type":"divider"},
  {"type":"qr","data":"https://example.com","size":5}
],"cut":true,"beep":false,"urgent":false}
```

Valid block types are `text`, `heading`, `divider`, `qr`. Free layout is rendered to raster (no arbitrary raw ESC/POS bytes accepted). New MCP tools appear after refreshing/reconnecting the client. Untested on this version of firmware.

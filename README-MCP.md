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

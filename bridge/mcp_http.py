"""Network-accessible Streamable HTTP MCP server for Echo.

Runs as an independent ASGI service on TCP 8766.
Authorization is checked before MCP requests reach the server.
"""
import os
import secrets
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .tickets import daily_schedule, reminder
from .history import recent
from .printer import list_printers, print_appointment as do_appointment, print_qr as do_qr, print_text as do_text

mcp = FastMCP(
    "echo-birch-printer",
    instructions="Print receipts, QR codes and Cellnet appointment tickets on the Windows Birch CP-Q1UN.",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["localhost:*", "127.0.0.1:*", "10.10.10.12:8766"],
        allowed_origins=["http://localhost:*", "http://127.0.0.1:*", "http://10.10.10.12:8766"],
    ),
)

@mcp.tool()
def print_receipt(text: str, cut: bool = True, beep: bool = False, urgent: bool = False) -> dict:
    """Queue a Unicode thermal receipt (Hungarian accents supported)."""
    return {"status": "queued", "job_id": do_text(text, cut, beep, urgent)}

@mcp.tool()
def print_qr_code(data: str, caption: str = "", cut: bool = True, beep: bool = False) -> dict:
    """Queue a QR code print with optional text caption."""
    return {"status": "queued", "job_id": do_qr(data, caption, cut=cut, beep=beep)}

@mcp.tool()
def print_appointment(customer: str, starts_at: str, service: str,
                      notes: str = "", reference: str = "",
                      cut: bool = True, beep: bool = True) -> dict:
    """Queue a Cellnet appointment ticket with customer, date/time and service."""
    return {"status": "queued", "job_id": do_appointment(
        customer, starts_at, service, notes, reference, cut, beep
    )}

@mcp.tool()
def available_printers() -> dict:
    """List available Windows printer queues."""
    return {"printers": list_printers(), "selected": os.getenv("PRINTER_NAME")}


@mcp.tool()
def print_daily_schedule(day: str, appointments: list[dict], cut: bool = True, beep: bool = False) -> dict:
    """Print a daily Cellnet schedule. Each appointment has time, customer, service and optional notes. Dates/events must be supplied by Echo; this tool does not access Google Calendar."""
    if not isinstance(appointments, list) or len(appointments) > 60:
        raise ValueError("appointments must be a list with at most 60 entries")
    for appt in appointments:
        if not isinstance(appt, dict) or not all(isinstance(appt.get(k), str) and appt[k] for k in ("time", "customer", "service")):
            raise ValueError("Every appointment needs time, customer and service strings")
        if any(len(str(value)) > 400 for value in appt.values()):
            raise ValueError("Appointment field exceeds 400 characters")
    if not day or len(day) > 80:
        raise ValueError("day must contain 1-80 characters")
    return {"status": "queued", "job_id": do_text(daily_schedule(day, appointments), cut, beep)}

@mcp.tool()
def print_reminder(title: str, message: str, when: str = "", priority: str = "normal",
                   cut: bool = True, beep: bool = True) -> dict:
    """Print a concise physical reminder. Set priority to urgent for a prominent heading."""
    if not title or len(title) > 200 or not message or len(message) > 1200 or len(when) > 100:
        raise ValueError("Invalid reminder length")
    if priority not in ("normal", "urgent"):
        raise ValueError("priority must be normal or urgent")
    return {"status": "queued", "job_id": do_text(reminder(title, message, when, priority), cut, beep, priority == "urgent")}


@mcp.tool()
def recent_print_jobs(limit: int = 20) -> dict:
    """List recently queued Windows print jobs (IDs/timestamps only; no private ticket contents)."""
    return {"jobs": recent(limit)}


class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        expected = os.getenv("PRINT_API_TOKEN", "")
        authorization = request.headers.get("authorization", "")
        if not expected or not authorization.startswith("Bearer ") or not secrets.compare_digest(
            authorization[len("Bearer "):], expected
        ):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)


@asynccontextmanager
async def lifespan(app):
    async with mcp.session_manager.run():
        yield


app = Starlette(lifespan=lifespan)
app.mount("/mcp", mcp.streamable_http_app())
app.add_middleware(BearerAuthMiddleware)

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
def print_receipt(text: str, cut: bool = True, beep: bool = False) -> dict:
    """Queue a Unicode thermal receipt (Hungarian accents supported)."""
    return {"status": "queued", "job_id": do_text(text, cut, beep)}

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

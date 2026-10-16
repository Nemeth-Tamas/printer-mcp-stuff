"""MCP stdio adapter for Echo (can run on any machine with Python)."""
import os
import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("echo-birch-printer")

def request(method: str, path: str, **kwargs):
    url = os.getenv("PRINT_API_URL", "http://127.0.0.1:8765").rstrip("/") + path
    token = os.environ["PRINT_API_TOKEN"]
    with httpx.Client(timeout=30) as client:
        response = client.request(method, url, headers={"Authorization": f"Bearer {token}"}, **kwargs)
        response.raise_for_status()
        return response.json()

@mcp.tool()
def print_receipt(text: str, cut: bool = True, beep: bool = False) -> dict:
    """Print a Unicode receipt including Hungarian accents."""
    return request("POST", "/print/text", json={"text": text, "cut": cut, "beep": beep})

@mcp.tool()
def print_qr_code(data: str, caption: str = "", cut: bool = True, beep: bool = False) -> dict:
    """Print a QR code with optional caption."""
    return request("POST", "/print/qr", json={"data": data, "caption": caption, "cut": cut, "beep": beep})

@mcp.tool()
def print_appointment(customer: str, starts_at: str, service: str, notes: str = "",
                      reference: str = "", cut: bool = True, beep: bool = True) -> dict:
    """Print a Cellnet customer appointment ticket."""
    return request("POST", "/print/appointment", json={
        "customer": customer, "starts_at": starts_at, "service": service,
        "notes": notes, "reference": reference, "cut": cut, "beep": beep})

@mcp.tool()
def available_printers() -> dict:
    """List Windows printers and selected receipt printer."""
    return request("GET", "/printers")

if __name__ == "__main__":
    mcp.run(transport="stdio")

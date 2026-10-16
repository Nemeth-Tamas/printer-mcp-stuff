"""MCP stdio adapter for Echo. Calls the authenticated HTTP print API."""
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
    """Print text with Hungarian Unicode on the configured receipt printer."""
    return request("POST", "/print/text", json={"text": text, "cut": cut, "beep": beep})

@mcp.tool()
def available_printers() -> dict:
    """List Windows printers and the selected default bridge printer."""
    return request("GET", "/printers")

if __name__ == "__main__":
    mcp.run(transport="stdio")

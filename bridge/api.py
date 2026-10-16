"""Authenticated local/LAN API for the Windows receipt printer."""
import os
import secrets
from fastapi import FastAPI, Header, HTTPException, Depends
from pydantic import BaseModel, Field
from .printer import print_text, list_printers

app = FastAPI(title="Echo Birch Print Bridge", version="0.1.0")

def authorize(authorization: str | None = Header(default=None)):
    token = os.getenv("PRINT_API_TOKEN")
    if not token:
        raise HTTPException(503, "PRINT_API_TOKEN must be configured")
    if not authorization or not authorization.startswith("Bearer ") or not secrets.compare_digest(authorization[7:], token):
        raise HTTPException(401, "Unauthorized")

class PrintRequest(BaseModel):
    text: str = Field(min_length=1, max_length=12000)
    cut: bool = True
    beep: bool = False

@app.get("/health")
def health():
    return {"ok": True, "version": "0.1.0"}

@app.get("/printers", dependencies=[Depends(authorize)])
def printers():
    return {"printers": list_printers(), "selected": os.getenv("PRINTER_NAME")}

@app.post("/print/text", dependencies=[Depends(authorize)])
def print_receipt(req: PrintRequest):
    try:
        job = print_text(req.text, cut=req.cut, beep=req.beep)
        return {"ok": True, "job_id": job, "status": "queued"}
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, "Printer spooler unavailable or print operation failed") from exc

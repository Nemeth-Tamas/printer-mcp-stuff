"""Authenticated local/LAN API for the Windows receipt printer."""
import os
import secrets
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException, Depends
from pydantic import BaseModel, Field
from .printer import print_text, print_qr, print_appointment, print_custom, list_printers
from .tickets import daily_schedule, reminder
from .history import recent

app = FastAPI(title="Echo Birch Print Bridge", version="0.4.1")
LOG_PATH = Path(__file__).resolve().parent.parent / "printer-errors.log"
logger = logging.getLogger("birch.printer")
if not logger.handlers:
    try:
        handler = RotatingFileHandler(LOG_PATH, maxBytes=500_000, backupCount=2, encoding="utf-8")
    except OSError:
        handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

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
    urgent: bool = False

class QRRequest(BaseModel):
    data: str = Field(min_length=1, max_length=1500)
    caption: str = Field(default="", max_length=600)
    module_size: int = Field(default=5, ge=2, le=8)
    cut: bool = True
    beep: bool = False

class AppointmentRequest(BaseModel):
    customer: str = Field(min_length=1, max_length=120)
    starts_at: str = Field(min_length=1, max_length=100)
    service: str = Field(min_length=1, max_length=120)
    notes: str = Field(default="", max_length=1200)
    reference: str = Field(default="", max_length=100)
    cut: bool = True
    beep: bool = True
    mode: str = Field(default="customer", pattern="^(customer|technician)$")
    phone: str = Field(default="", max_length=40)

def submit(fn, *args, **kwargs):
    try:
        job = fn(*args, **kwargs)
        return {"ok": True, "job_id": job, "status": "queued"}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("Print submission failed: %s", type(exc).__name__)
        raise HTTPException(503, f"Printer failure: {type(exc).__name__}; see printer-errors.log on Windows") from exc

@app.get("/health")
def health():
    return {"ok": True, "version": "0.4.0"}

@app.get("/printers", dependencies=[Depends(authorize)])
def printers():
    try:
        return {"printers": list_printers(), "selected": os.getenv("PRINTER_NAME")}
    except Exception as exc:
        raise HTTPException(503, "Could not enumerate printers") from exc

@app.post("/print/text", dependencies=[Depends(authorize)])
def print_receipt(req: PrintRequest):
    return submit(print_text, req.text, cut=req.cut, beep=req.beep, urgent=req.urgent)

@app.post("/print/qr", dependencies=[Depends(authorize)])
def print_qrcode(req: QRRequest):
    return submit(print_qr, req.data, caption=req.caption, size=req.module_size, cut=req.cut, beep=req.beep)

@app.post("/print/appointment", dependencies=[Depends(authorize)])
def appointment(req: AppointmentRequest):
    return submit(print_appointment, req.customer, req.starts_at, req.service,
                  notes=req.notes, reference=req.reference, cut=req.cut, beep=req.beep, mode=req.mode, phone=req.phone)

class ScheduleItem(BaseModel):
    time: str = Field(min_length=1, max_length=30)
    customer: str = Field(min_length=1, max_length=120)
    service: str = Field(min_length=1, max_length=140)
    notes: str = Field(default="", max_length=400)

class ScheduleRequest(BaseModel):
    day: str = Field(min_length=1, max_length=80)
    appointments: list[ScheduleItem] = Field(default_factory=list, max_length=60)
    cut: bool = True
    beep: bool = False

class ReminderRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=1200)
    when: str = Field(default="", max_length=100)
    priority: str = Field(default="normal", pattern="^(normal|urgent)$")
    cut: bool = True
    beep: bool = True

@app.post("/print/schedule", dependencies=[Depends(authorize)])
def schedule_receipt(req: ScheduleRequest):
    text = daily_schedule(req.day, [a.model_dump() for a in req.appointments])
    return submit(print_text, text, cut=req.cut, beep=req.beep)

@app.post("/print/reminder", dependencies=[Depends(authorize)])
def reminder_receipt(req: ReminderRequest):
    text = reminder(req.title, req.message, req.when, req.priority)
    return submit(print_text, text, cut=req.cut, beep=req.beep, urgent=req.priority == "urgent")

@app.get("/jobs", dependencies=[Depends(authorize)])
def jobs(limit: int = 20):
    return {"jobs": recent(limit)}

class CustomRequest(BaseModel):
    blocks: list[dict] = Field(min_length=1, max_length=80)
    cut: bool = True
    beep: bool = False
    urgent: bool = False

@app.post("/print/custom", dependencies=[Depends(authorize)])
def custom_receipt(req: CustomRequest):
    return submit(print_custom, req.blocks, cut=req.cut, beep=req.beep, urgent=req.urgent)

@app.get("/diagnostics/printer", dependencies=[Depends(authorize)])
def printer_diagnostics():
    """Read-only spooler diagnostics; returns no tokens or private print contents."""
    import win32print
    name = os.getenv("PRINTER_NAME", "")
    try:
        handle = win32print.OpenPrinter(name)
        try:
            details = win32print.GetPrinter(handle, 2)
            return {"selected": name, "accessible": True,
                    "port": details.get("pPortName"), "driver": details.get("pDriverName"),
                    "status": details.get("Status"), "service_account": os.getenv("USERNAME", "unknown")}
        finally:
            win32print.ClosePrinter(handle)
    except Exception as exc:
        logger.exception("Spooler diagnostic failed")
        raise HTTPException(503, f"Cannot open printer as service: {type(exc).__name__}; see printer-errors.log") from exc

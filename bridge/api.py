"""Authenticated local/LAN API for the Windows receipt printer."""
import os
import secrets
from fastapi import FastAPI, Header, HTTPException, Depends
from pydantic import BaseModel, Field
from .printer import print_text, print_qr, print_appointment, list_printers
from .tickets import daily_schedule, reminder

app = FastAPI(title="Echo Birch Print Bridge", version="0.4.0")

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

def submit(fn, *args, **kwargs):
    try:
        job = fn(*args, **kwargs)
        return {"ok": True, "job_id": job, "status": "queued"}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, "Printer spooler unavailable or print operation failed") from exc

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
    return submit(print_text, req.text, cut=req.cut, beep=req.beep)

@app.post("/print/qr", dependencies=[Depends(authorize)])
def print_qrcode(req: QRRequest):
    return submit(print_qr, req.data, caption=req.caption, size=req.module_size, cut=req.cut, beep=req.beep)

@app.post("/print/appointment", dependencies=[Depends(authorize)])
def appointment(req: AppointmentRequest):
    return submit(print_appointment, req.customer, req.starts_at, req.service,
                  notes=req.notes, reference=req.reference, cut=req.cut, beep=req.beep)

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
    return submit(print_text, text, cut=req.cut, beep=req.beep)

"""Cellnet Booking MVP: authenticated bookings, simple frontend and printer integration."""
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
DB = Path(os.getenv("BOOKING_DB", "/data/booking.sqlite3"))
TZ = ZoneInfo("Europe/Budapest")
app = FastAPI(title="Cellnet Booking", version="0.1.0")

@contextmanager
def database():
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS appointments(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          customer TEXT NOT NULL, phone TEXT NOT NULL, service TEXT NOT NULL,
          starts_at TEXT NOT NULL, duration_minutes INTEGER NOT NULL,
          notes TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'booked',
          created_at TEXT NOT NULL)""")
        yield conn
        conn.commit()
    finally:
        conn.close()

def require_auth(authorization: str | None = Header(default=None)):
    token = os.getenv("BOOKING_ADMIN_TOKEN", "")
    if not token or token == "GENERATE_A_LONG_RANDOM_PASSWORD":
        raise HTTPException(503, "Configure BOOKING_ADMIN_TOKEN")
    if not authorization or not authorization.startswith("Bearer ") or not secrets.compare_digest(authorization[7:], token):
        raise HTTPException(401, "Unauthorized")

class AppointmentIn(BaseModel):
    customer: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=3, max_length=40)
    service: str = Field(min_length=1, max_length=160)
    starts_at: datetime
    duration_minutes: int = Field(default=60, ge=15, le=480)
    notes: str = Field(default="", max_length=1500)

def validate_time(value: datetime):
    if value.tzinfo is None:
        raise HTTPException(422, "Include an explicit UTC offset in starts_at")
    return value.astimezone(TZ).isoformat()

@app.get("/health")
def health():
    return {"ok": True, "version": "0.1.0"}

@app.get("/", response_class=HTMLResponse)
def home():
    return (ROOT / "index.html").read_text(encoding="utf-8")

@app.get("/api/appointments", dependencies=[Depends(require_auth)])
def list_appointments():
    with database() as db:
        return [dict(row) for row in db.execute("SELECT * FROM appointments ORDER BY starts_at DESC LIMIT 250")]

@app.post("/api/appointments", dependencies=[Depends(require_auth)], status_code=201)
def create_appointment(req: AppointmentIn):
    when = validate_time(req.starts_at)
    with database() as db:
        cursor = db.execute(
          "INSERT INTO appointments(customer, phone, service, starts_at, duration_minutes, notes, created_at) VALUES (?,?,?,?,?,?,?)",
          (req.customer, req.phone, req.service, when, req.duration_minutes, req.notes, datetime.now(TZ).isoformat()))
        return {"id": cursor.lastrowid, "status": "booked", "starts_at": when}

@app.patch("/api/appointments/{appointment_id}/cancel", dependencies=[Depends(require_auth)])
def cancel_appointment(appointment_id: int):
    with database() as db:
        cur = db.execute("UPDATE appointments SET status='cancelled' WHERE id=? AND status='booked'", (appointment_id,))
        if not cur.rowcount:
            raise HTTPException(404, "Active appointment not found")
        return {"ok": True}

@app.post("/api/appointments/{appointment_id}/print", dependencies=[Depends(require_auth)])
def print_appointment(appointment_id: int):
    with database() as db:
        row = db.execute("SELECT * FROM appointments WHERE id=?", (appointment_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Appointment not found")
    url = os.getenv("PRINTER_API_URL", "").rstrip("/")
    token = os.getenv("PRINTER_API_TOKEN", "")
    if not url or not token:
        raise HTTPException(503, "Configure printer API URL/token")
    payload = dict(customer=row["customer"], starts_at=row["starts_at"],
                   service=row["service"], notes=row["notes"], reference=f"CEL-{appointment_id}",
                   cut=True, beep=False)
    try:
        with httpx.Client(timeout=20) as client:
            resp = client.post(url + "/print/appointment",
                               headers={"Authorization": "Bearer " + token}, json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError:
        raise HTTPException(502, "Printer API failed") from None

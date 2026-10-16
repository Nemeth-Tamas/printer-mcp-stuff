"""Cellnet Booking MVP: trusted LAN-only bookings and print integration."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from .google_feed import create_event, delete_event, fetch_events, update_event, write_calendar
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
DB = Path(os.getenv("BOOKING_DB", "/data/booking.sqlite3"))
TZ = ZoneInfo("Europe/Budapest")
app = FastAPI(title="Cellnet Booking", version="0.3.0")

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
        cols = {r[1] for r in conn.execute("PRAGMA table_info(appointments)")}
        if "google_event_id" not in cols:
            conn.execute("ALTER TABLE appointments ADD COLUMN google_event_id TEXT")
        yield conn
        conn.commit()
    finally:
        conn.close()

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
    return {"ok": True, "version": "0.3.0"}

@app.get("/", response_class=HTMLResponse)
def home():
    return (ROOT / "index.html").read_text(encoding="utf-8")

@app.get("/api/appointments")
def list_appointments():
    with database() as db:
        return [dict(row) for row in db.execute("SELECT * FROM appointments ORDER BY starts_at DESC LIMIT 250")]

@app.post("/api/appointments", status_code=201)
def create_appointment(req: AppointmentIn):
    when = validate_time(req.starts_at)
    start_time = datetime.fromisoformat(when)
    end_time = start_time + timedelta(minutes=req.duration_minutes)
    try:
        google, connected = fetch_events(start_time - timedelta(days=1), end_time + timedelta(days=1))
        if not connected:
            raise RuntimeError("Google Calendar not configured")
        for event in google:
            from datetime import date, time
            begin = datetime.fromisoformat(event["start"]) if not event["allDay"] else datetime.combine(date.fromisoformat(event["start"]), time.min, tzinfo=TZ)
            finish = datetime.fromisoformat(event["end"]) if not event["allDay"] else datetime.combine(date.fromisoformat(event["end"]), time.min, tzinfo=TZ)
            if begin < end_time and finish > start_time:
                raise HTTPException(409, "Az időpont ütközik egy Google Calendar eseménnyel")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, "Google Calendar availability check failed: " + str(exc)[:160]) from None
    with database() as db:
        existing = db.execute("SELECT starts_at, duration_minutes FROM appointments WHERE status='booked'").fetchall()
        for current in existing:
            begin = datetime.fromisoformat(current["starts_at"])
            if begin < end_time and begin + timedelta(minutes=current["duration_minutes"]) > start_time:
                raise HTTPException(409, "Az időpont ütközik egy helyi foglalással")
        cursor = db.execute(
          "INSERT INTO appointments(customer, phone, service, starts_at, duration_minutes, notes, created_at) VALUES (?,?,?,?,?,?,?)",
          (req.customer, req.phone, req.service, when, req.duration_minutes, req.notes, datetime.now(TZ).isoformat()))
        booking_id = cursor.lastrowid
        try:
            event_id = create_event(booking_id, req.customer, req.phone, req.service,
                                    when, req.duration_minutes, req.notes)
        except Exception as exc:
            db.rollback()
            raise HTTPException(502, "Google Calendar event creation failed: " + str(exc)[:180]) from None
        db.execute("UPDATE appointments SET google_event_id=? WHERE id=?", (event_id, booking_id))
        return {"id": booking_id, "status": "booked", "starts_at": when, "google_event_id": event_id}

@app.patch("/api/appointments/{appointment_id}/cancel")
def cancel_appointment(appointment_id: int):
    with database() as db:
        row = db.execute("SELECT * FROM appointments WHERE id=? AND status='booked'", (appointment_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Active appointment not found")
        if row["google_event_id"]:
            try:
                delete_event(row["google_event_id"])
            except Exception as exc:
                raise HTTPException(502, "Google Calendar cancellation failed: " + str(exc)[:180]) from None
        db.execute("UPDATE appointments SET status='cancelled' WHERE id=?", (appointment_id,))
        return {"ok": True}

@app.post("/api/appointments/{appointment_id}/print")
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


@app.put("/api/appointments/{appointment_id}")
def edit_appointment(appointment_id: int, req: AppointmentIn):
    when = validate_time(req.starts_at)
    start = datetime.fromisoformat(when)
    finish = start + timedelta(minutes=req.duration_minutes)
    with database() as db:
        original = db.execute("SELECT * FROM appointments WHERE id=? AND status='booked'", (appointment_id,)).fetchone()
        if original is None:
            raise HTTPException(404, "Active appointment not found")
        if not original["google_event_id"]:
            raise HTTPException(409, "Legacy local booking cannot be edited yet")
        others = db.execute("SELECT id, starts_at, duration_minutes FROM appointments WHERE status='booked' AND id<>?", (appointment_id,)).fetchall()
        for other in others:
            other_start = datetime.fromisoformat(other["starts_at"])
            if other_start < finish and other_start + timedelta(minutes=other["duration_minutes"]) > start:
                raise HTTPException(409, "Az időpont ütközik egy helyi foglalással")
        try:
            google, connected = fetch_events(start - timedelta(days=1), finish + timedelta(days=1))
            if not connected:
                raise RuntimeError("Google calendar not configured")
            from datetime import date, time
            for event in google:
                if event.get("id") == original["google_event_id"] and event.get("calendar") == __import__("app.google_feed", fromlist=["write_calendar"]).write_calendar():
                    continue
                begin = datetime.fromisoformat(event["start"]) if not event["allDay"] else datetime.combine(date.fromisoformat(event["start"]), time.min, tzinfo=TZ)
                end = datetime.fromisoformat(event["end"]) if not event["allDay"] else datetime.combine(date.fromisoformat(event["end"]), time.min, tzinfo=TZ)
                if begin < finish and end > start:
                    raise HTTPException(409, "Az időpont ütközik egy Google Calendar eseménnyel")
            update_event(original["google_event_id"], appointment_id, req.customer, req.phone,
                         req.service, when, req.duration_minutes, req.notes)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(502, "Google Calendar update failed: " + str(exc)[:180]) from None
        db.execute("UPDATE appointments SET customer=?, phone=?, service=?, starts_at=?, duration_minutes=?, notes=? WHERE id=?",
                   (req.customer, req.phone, req.service, when, req.duration_minutes, req.notes, appointment_id))
        return {"id": appointment_id, "status": "booked", "google_event_id": original["google_event_id"]}

from .calendar_routes import router as calendar_router
app.include_router(calendar_router)

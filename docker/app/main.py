"""Cellnet Booking MVP: trusted LAN-only bookings and print integration."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from .sms import init_sms, replace_pending, cancel_pending, outbox, normalize_phone, sms_text
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
        if "sms_enabled" not in cols:
            conn.execute("ALTER TABLE appointments ADD COLUMN sms_enabled INTEGER NOT NULL DEFAULT 0")
        init_sms(conn)
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
    sms_enabled: bool = False

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
def list_appointments(view: str = "upcoming", search: str = ""):
    if view not in ("upcoming", "past", "cancelled", "all"):
        raise HTTPException(400, "Invalid view")
    if len(search) > 120:
        raise HTTPException(400, "Search too long")
    now = datetime.now(TZ).isoformat()
    where = []
    params = []
    if view == "upcoming":
        where.extend(["status='booked'", "starts_at>=?"])
        params.append(now)
    elif view == "past":
        where.extend(["status='booked'", "starts_at<?"])
        params.append(now)
    elif view == "cancelled":
        where.append("status='cancelled'")
    if search.strip():
        where.append("(customer LIKE ? OR phone LIKE ? OR service LIKE ?)")
        term = "%" + search.strip() + "%"
        params.extend([term] * 3)
    condition = " WHERE " + " AND ".join(where) if where else ""
    direction = "ASC" if view == "upcoming" else "DESC"
    sql = "SELECT * FROM appointments" + condition + " ORDER BY starts_at " + direction + " LIMIT 250"
    with database() as db:
        return [dict(row) for row in db.execute(sql, params)]

@app.get("/api/customers")
def customers(search: str = ""):
    if len(search) < 2:
        return []
    if len(search) > 120:
        raise HTTPException(400, "Search too long")
    pattern = "%" + search.strip() + "%"
    with database() as db:
        rows = db.execute("""
            SELECT customer, phone, COUNT(*) AS visits, MAX(starts_at) AS last_booking
            FROM appointments WHERE customer LIKE ? OR phone LIKE ?
            GROUP BY customer, phone ORDER BY last_booking DESC LIMIT 15
        """, (pattern, pattern)).fetchall()
        return [dict(row) for row in rows]

@app.post("/api/appointments", status_code=201)
def create_appointment(req: AppointmentIn):
    if req.sms_enabled:
        try:
            normalize_phone(req.phone)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
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
        db.execute("UPDATE appointments SET google_event_id=?, sms_enabled=? WHERE id=?", (event_id, int(req.sms_enabled), booking_id))
        saved = db.execute("SELECT * FROM appointments WHERE id=?", (booking_id,)).fetchone()
        replace_pending(db, saved, req.sms_enabled)
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
        cancel_pending(db, appointment_id)
        return {"ok": True}

@app.post("/api/appointments/{appointment_id}/print")
def print_appointment(appointment_id: int, mode: str = 'customer'):
    with database() as db:
        row = db.execute("SELECT * FROM appointments WHERE id=?", (appointment_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Appointment not found")
    url = os.getenv("PRINTER_API_URL", "").rstrip("/")
    token = os.getenv("PRINTER_API_TOKEN", "")
    if not url or not token:
        raise HTTPException(503, "Configure printer API URL/token")
    if mode not in ("customer", "technician"):
        raise HTTPException(400, "Invalid copy type")
    payload = dict(customer=row["customer"], starts_at=row["starts_at"],
                   service=row["service"], notes=row["notes"], reference=f"CEL-{appointment_id}",
                   cut=True, beep=False, mode=mode, phone=row["phone"])
    try:
        with httpx.Client(timeout=20) as client:
            resp = client.post(url + "/print/appointment",
                               headers={"Authorization": "Bearer " + token}, json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"Printer API HTTP {exc.response.status_code}: {exc.response.text[:180]}") from None
    except httpx.RequestError as exc:
        raise HTTPException(502, f"Printer connection failed ({type(exc).__name__}): {str(exc)[:140]}") from None


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
        db.execute("UPDATE appointments SET customer=?, phone=?, service=?, starts_at=?, duration_minutes=?, notes=?, sms_enabled=? WHERE id=?",
                   (req.customer, req.phone, req.service, when, req.duration_minutes, req.notes, int(req.sms_enabled), appointment_id))
        refreshed = db.execute("SELECT * FROM appointments WHERE id=?", (appointment_id,)).fetchone()
        replace_pending(db, refreshed, req.sms_enabled)
        return {"id": appointment_id, "status": "booked", "google_event_id": original["google_event_id"]}

from .calendar_routes import router as calendar_router
app.include_router(calendar_router)

@app.get("/api/sms/outbox")
def sms_outbox():
    with database() as db:
        return {"mode": os.getenv("SMS_MODE", "dry-run"), "messages": outbox(db)}

@app.post("/api/appointments/{appointment_id}/sms/send")
def send_booking_sms(appointment_id: int):
    """Queue a single explicit manual confirmation; never replay old queued reminders."""
    from datetime import timezone
    with database() as db:
        row = db.execute("SELECT * FROM appointments WHERE id=? AND status='booked'", (appointment_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Active appointment not found")
        if not row["sms_enabled"]:
            raise HTTPException(409, "SMS not enabled for this appointment")
        phone = normalize_phone(row["phone"])
        now = datetime.now(timezone.utc).isoformat()
        # Prevent double clicks / repeated sends while a message is already queued.
        recent = db.execute("""SELECT id FROM sms_outbox WHERE booking_id=? AND kind='manual'
            AND status IN ('pending','processing') LIMIT 1""", (appointment_id,)).fetchone()
        if recent:
            raise HTTPException(409, "Manual SMS already queued")
        cursor = db.execute("""INSERT INTO sms_outbox
            (booking_id, kind, phone, body, due_at, status, created_at)
            VALUES (?,?,?,?,?,'pending',?)""",
            (appointment_id, "manual", phone, sms_text("confirmation", row), now, now))
        return {"ok": True, "sms_id": cursor.lastrowid, "status": "pending"}

@app.get("/api/printer/status")
def printer_status():
    """Diagnostic: distinguish reachability, authentication and spooler errors."""
    url = os.getenv("PRINTER_API_URL", "").rstrip("/")
    token = os.getenv("PRINTER_API_TOKEN", "")
    if not url or not token:
        raise HTTPException(503, "PRINTER_API_URL or PRINTER_API_TOKEN not configured in Docker")
    try:
        with httpx.Client(timeout=5) as client:
            health_response = client.get(url + "/health")
            printer_response = client.get(url + "/diagnostics/printer", headers={"Authorization": "Bearer " + token})
            return {"health_http": health_response.status_code, "printer_http": printer_response.status_code,
                    "diagnostics": printer_response.json() if printer_response.is_success else printer_response.text[:180]}
    except httpx.RequestError as exc:
        raise HTTPException(502, f"Printer unreachable ({type(exc).__name__}): {str(exc)[:140]}") from None

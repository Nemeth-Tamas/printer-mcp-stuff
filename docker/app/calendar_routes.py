"""Combined local booking and Google event calendar preview."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pathlib import Path

from .google_feed import fetch_events

router = APIRouter()
TZ = ZoneInfo("Europe/Budapest")

@router.get("/calendar", response_class=HTMLResponse)
def calendar_page():
    return (Path(__file__).parent / "calendar.html").read_text(encoding="utf-8")

@router.get("/api/calendar/week")
def calendar_week(start: date):
    from .main import database
    beginning = datetime.combine(start, time.min, tzinfo=TZ)
    ending = beginning + timedelta(days=7)
    with database() as conn:
        rows = conn.execute("SELECT starts_at, duration_minutes, service, status FROM appointments WHERE status='booked'").fetchall()
    local = []
    for row in rows:
        begins = datetime.fromisoformat(row["starts_at"])
        ends = begins + timedelta(minutes=row["duration_minutes"])
        if begins < ending and ends > beginning:
            local.append({"title": "Cellnet: " + row["service"], "start": begins.isoformat(),
                          "end": ends.isoformat(), "allDay": False, "source": "local"})
    try:
        remote, connected = fetch_events(beginning, ending)
    except Exception as exc:
        return {"events": local, "google_connected": False, "google_error": str(exc)[:180]}
    return {"events": local + remote, "google_connected": connected}

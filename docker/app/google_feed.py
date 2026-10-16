"""Google Calendar service-account read/write integration."""
import os
from urllib.parse import quote
import httpx
from google.oauth2 import service_account
from google.auth.transport.requests import Request

BASE = "https://www.googleapis.com/calendar/v3/calendars/"
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

def calendar_ids():
    return [v.strip() for v in os.getenv("GOOGLE_CALENDAR_IDS", "").split(",") if v.strip()]

def write_calendar():
    return os.getenv("GOOGLE_WRITE_CALENDAR_ID") or (calendar_ids()[0] if calendar_ids() else "")

def client_credentials():
    filename = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")
    if not filename or not os.path.isfile(filename):
        raise RuntimeError("Google service account JSON not configured or inaccessible")
    credentials = service_account.Credentials.from_service_account_file(filename, scopes=SCOPES)
    credentials.refresh(Request())
    return {"Authorization": "Bearer " + credentials.token}

def fetch_events(start, end):
    ids = calendar_ids()
    if not ids or not os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE"):
        return [], False
    headers = client_credentials()
    output = []
    with httpx.Client(timeout=20) as client:
        for calendar_id in ids:
            next_page = None
            while True:
                params = {"timeMin": start.isoformat(), "timeMax": end.isoformat(),
                          "singleEvents": "true", "orderBy": "startTime", "maxResults": 250}
                if next_page:
                    params["pageToken"] = next_page
                response = client.get(BASE + quote(calendar_id, safe="") + "/events",
                                      params=params, headers=headers)
                response.raise_for_status()
                data = response.json()
                for event in data.get("items", []):
                    if event.get("status") == "cancelled":
                        continue
                    output.append({
                        "id": event.get("id"), "title": event.get("summary", "Foglalt"),
                        "start": event["start"].get("dateTime", event["start"].get("date")),
                        "end": event["end"].get("dateTime", event["end"].get("date")),
                        "allDay": "date" in event["start"], "source": "google",
                        "calendar": calendar_id,
                        "booking_id": event.get("extendedProperties", {}).get("private", {}).get("cellnet_booking_id"),
                    })
                next_page = data.get("nextPageToken")
                if not next_page:
                    break
    return output, True

def create_event(booking_id, customer, phone, service, starts_at, duration_minutes, notes):
    from datetime import datetime, timedelta
    target = write_calendar()
    if not target:
        raise RuntimeError("GOOGLE_WRITE_CALENDAR_ID not configured")
    beginning = datetime.fromisoformat(starts_at)
    ending = beginning + timedelta(minutes=duration_minutes)
    payload = {
        "summary": f"{customer} – {service}",
        "description": f"Cellnet foglalás #{booking_id}\nTelefon: {phone}\nMegjegyzés: {notes}",
        "start": {"dateTime": beginning.isoformat(), "timeZone": "Europe/Budapest"},
        "end": {"dateTime": ending.isoformat(), "timeZone": "Europe/Budapest"},
        "extendedProperties": {"private": {"cellnet_booking_id": str(booking_id)}},
    }
    with httpx.Client(timeout=20) as client:
        response = client.post(BASE + quote(target, safe="") + "/events",
                               json=payload, headers=client_credentials())
        response.raise_for_status()
        return response.json()["id"]

def delete_event(event_id):
    target = write_calendar()
    with httpx.Client(timeout=20) as client:
        response = client.delete(BASE + quote(target, safe="") + "/events/" + quote(event_id, safe=""),
                                 headers=client_credentials())
        response.raise_for_status()

def update_event(event_id, booking_id, customer, phone, service, starts_at, duration_minutes, notes):
    """Update an existing event in place, retaining its Google event ID."""
    from datetime import datetime, timedelta
    beginning = datetime.fromisoformat(starts_at)
    ending = beginning + timedelta(minutes=duration_minutes)
    payload = {
        "summary": f"{customer} – {service}",
        "description": f"Cellnet foglalás #{booking_id}\nTelefon: {phone}\nMegjegyzés: {notes}",
        "start": {"dateTime": beginning.isoformat(), "timeZone": "Europe/Budapest"},
        "end": {"dateTime": ending.isoformat(), "timeZone": "Europe/Budapest"},
    }
    url = BASE + quote(write_calendar(), safe="") + "/events/" + quote(event_id, safe="")
    with httpx.Client(timeout=20) as client:
        response = client.patch(url, json=payload, headers=client_credentials())
        response.raise_for_status()
        return response.json()["id"]

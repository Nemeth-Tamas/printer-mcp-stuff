"""Fetch shared Google Calendar events using a service account."""
import os
from urllib.parse import quote
import httpx
from google.oauth2 import service_account
from google.auth.transport.requests import Request

def fetch_events(start, end):
    filename = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")
    ids = [x.strip() for x in os.getenv("GOOGLE_CALENDAR_IDS", "").split(",") if x.strip()]
    if not filename or not ids:
        return [], False
    credentials = service_account.Credentials.from_service_account_file(
        filename, scopes=["https://www.googleapis.com/auth/calendar.events.readonly"])
    credentials.refresh(Request())
    output = []
    with httpx.Client(timeout=20) as client:
        for calendar_id in ids:
            next_page = None
            while True:
                params = {"timeMin": start.isoformat(), "timeMax": end.isoformat(),
                          "singleEvents": "true", "orderBy": "startTime", "maxResults": 250}
                if next_page:
                    params["pageToken"] = next_page
                response = client.get(
                    "https://www.googleapis.com/calendar/v3/calendars/" + quote(calendar_id, safe="") + "/events",
                    params=params, headers={"Authorization": "Bearer " + credentials.token})
                response.raise_for_status()
                data = response.json()
                for event in data.get("items", []):
                    if event.get("status") == "cancelled":
                        continue
                    output.append({
                        "title": event.get("summary", "Foglalt"),
                        "start": event["start"].get("dateTime", event["start"].get("date")),
                        "end": event["end"].get("dateTime", event["end"].get("date")),
                        "allDay": "date" in event["start"], "source": "google",
                        "calendar": calendar_id,
                    })
                next_page = data.get("nextPageToken")
                if not next_page:
                    break
    return output, True

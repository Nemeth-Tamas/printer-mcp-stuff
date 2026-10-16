# Cellnet Booking — LAN/VPN Docker MVP

Simple Hungarian booking interface for trusted local and WireGuard clients. No login/register or admin token prompts.

## Deploy to Ubuntu

```sh
git pull
cd docker
cp .env.example .env  # first installation only
nano .env
docker compose up -d --build
```

For existing deployments, preserve the existing `.env`; it can retain unused `BOOKING_ADMIN_TOKEN` harmlessly. Configure `PRINTER_API_URL=http://10.10.10.12:8765` and `PRINTER_API_TOKEN` to use the Windows print bridge.

Open `http://UBUNTU_LAN_IP:8088` or `http://UBUNTU_WG_IP:8088` from your browser.

The Compose published port is `8088:8088` (all host interfaces). **This version has no authentication**, intentionally. Restrict access at your LAN/VPN boundary and do not forward it to the internet. Anyone who can reach the port can read customer names/phone numbers and create/cancel appointments.

Features: create, list, cancel bookings and print tickets via the printer bridge. Persistent SQLite Docker volume. Calendar and SMS are future integrations: appointments currently exist in SQLite **only**, not Google Calendar.


## Google calendar preview

Enable the Google Calendar API in a Google Cloud project. Create a service account and download its JSON key. Share the existing personal calendar(s) with the service account email with **See all event details** permission; share a dedicated Cellnet calendar too if applicable. Only calendars explicitly shared with the service account can be read.

On Ubuntu:

```sh
mkdir -p docker/credentials
cp /secure/path/to/service-account.json docker/credentials/service-account.json
chmod 600 docker/credentials/service-account.json
```

In `docker/.env`, set:

```ini
GOOGLE_SERVICE_ACCOUNT_FILE=/run/google/service-account.json
GOOGLE_CALENDAR_IDS=your_calendar_id@gmail.com,another_calendar_id@group.calendar.google.com
```

Calendar IDs may be your primary email or a secondary calendar ID. Do not commit credential JSON. Docker mounts `./credentials` read-only. Restart with `docker compose up -d --build`. Visit `http://UBUNTU_IP:8088/calendar`.

Google preview is **read-only** at this stage. Creating an appointment still writes to local SQLite only; Google event creation/sync comes next. The calendar feed displays event titles to anyone on the trusted LAN/VPN who can load the page. It never exposes Google tokens to browser JavaScript.

## Google write-back and calendar availability

The configured calendar `cellnet.kft@gmail.com` is the default write destination (or set `GOOGLE_WRITE_CALENDAR_ID` explicitly). The service account needs **Make changes to events** permission on that calendar. Google Calendar API must be enabled in its Google Cloud project.

Ubuntu credentials at `/run/google/service-account.json` are bind-mounted read-only into the Docker container, with `GOOGLE_SERVICE_ACCOUNT_FILE=/run/google/service-account.json`. This must be the path visible on the **Docker host**. Existing `.env` can remain unchanged; the write calendar defaults to the first `GOOGLE_CALENDAR_IDS` entry.

A new booking checks existing Google events and local bookings for overlap, then creates a Google event and stores its ID with the SQLite booking. A Google API failure aborts a new booking instead of silently saving it only in SQLite. Cancelling a synced booking deletes its Google event. Older local-only bookings remain local-only; synced events are not duplicated in the weekly view.

**Known MVP limits:** no reschedule/edit UI, no background reconciliation for changes made directly in Google Calendar, no automatic recovery from network outages, no SMS. Only make bookings from one operator at a time while the MVP is being tested. Service account setup (not OAuth) requires explicit calendar sharing. Google events and private appointment details are visible on the trusted LAN/VPN.

## Editing and rescheduling

The booking page now has **Szerkesztés** for Google-synced active bookings. Editing preserves the Google event ID, checks new times against Google and SQLite appointments, and updates the Google event. The calendar UI offers 30-minute starting slots and disables slots overlapping an event. The server rechecks collisions before saving; a 30-minute free button does not necessarily mean that a longer service will fit.

Existing legacy local-only bookings intentionally cannot yet be edited with Google rescheduling. This is a trusted-LAN MVP, not a multi-user transactional scheduler; concurrent operators and calendar edits from another device can still race. SMS, reconciliation and automatic reschedule notifications are not implemented.

Deploy changes with `git pull && cd docker && docker compose up -d --build`. Keep your existing `.env` and credentials.

## Booking workflow additions

The main page now defaults to upcoming appointments (ascending), with tabs for past, cancelled and all appointments, plus live search by customer name, phone or service. Repeat customers can be reused from name suggestions or the **Új foglalás ugyanennek** action. Customer suggestions are derived from existing SQLite appointments, not a separate CRM database. All appointment changes still use the existing Google Calendar sync and conflict checks.

`GET /api/appointments?view=upcoming|past|cancelled|all&search=...` and `GET /api/customers?search=...` are available on the trusted LAN/VPN. Calendar and printer services need no restart for these changes; only rebuild the Docker application. SMS sending is not implemented.

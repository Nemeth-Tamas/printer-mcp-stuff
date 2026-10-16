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

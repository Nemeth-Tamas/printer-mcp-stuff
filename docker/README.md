# Cellnet Booking — Docker MVP

Small self-hosted appointment admin application (FastAPI + SQLite + responsive HTML frontend).

## Start on Ubuntu

```sh
cd docker
cp .env.example .env
nano .env
docker compose up -d --build
```

Set a long unique `BOOKING_ADMIN_TOKEN`; configure `PRINTER_API_URL=http://10.10.10.12:8765` and `PRINTER_API_TOKEN` to match the Windows print bridge.

Visit `http://127.0.0.1:8088` **on the Ubuntu host**, or use an SSH tunnel from another machine:

```sh
ssh -L 8088:127.0.0.1:8088 user@ubuntu-host
```

The app intentionally binds only the host loopback interface until an HTTPS reverse proxy and real login/session system are configured. The frontend asks for an admin bearer token and keeps it only in the current page (not localStorage).

**MVP features:** create/list/cancel appointments, print appointment tickets to the existing Windows print API, persistent SQLite volume, Hungarian mobile-friendly interface.

**Not implemented yet:** Google Calendar synchronization/OAuth, SMS gateway, contact management, automated reminders, edit/reschedule, overlapping appointment checks, multi-user accounts, HTTPS/reverse proxy. Do not expose this version publicly. The booking database is authoritative for this MVP; do not assume entries reach Google Calendar.

`GET /health` is public; other `/api/*` endpoints require `Authorization: Bearer <BOOKING_ADMIN_TOKEN>`.

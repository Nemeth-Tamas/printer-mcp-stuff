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


# Changelog

## v0.5 (development)
- Improved Hungarian appointment receipt wording.
- `urgent=true` on `/print/text` and MCP `print_receipt`: prominent boxed heading and forced buzzer.
- `priority=urgent` on reminder routes also forces beeping and the urgent heading.
- Added `docker/` Cellnet Booking MVP: admin-only mobile-first UI, SQLite bookings, cancel and print workflows, Docker Compose.
- Calendar synchronization and SMS are **not** yet implemented.
- The Docker app starts on host loopback port 8088; use SSH tunneling or a secured reverse proxy.
- Tests scaffold for booking CRUD; live validation on the Ubuntu host is pending.

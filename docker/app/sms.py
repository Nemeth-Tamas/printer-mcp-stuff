"""SMS outbox: deterministic messages, opt-in reminders, no sending without gateway."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import re

TZ = ZoneInfo("Europe/Budapest")

def normalize_phone(value):
    digits = re.sub(r"[\s()\-]", "", value)
    if digits.startswith("06"):
        digits = "+36" + digits[2:]
    if digits.startswith("36") and not digits.startswith("+"):
        digits = "+" + digits
    if not re.fullmatch(r"\+36\d{8,9}", digits):
        raise ValueError("Adj meg érvényes magyar mobilszámot, pl. +36301234567")
    return digits

def init_sms(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS sms_outbox(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        booking_id INTEGER NOT NULL,
        kind TEXT NOT NULL,
        phone TEXT NOT NULL,
        body TEXT NOT NULL,
        due_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        sent_at TEXT,
        error TEXT
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS sms_due ON sms_outbox(status,due_at)")

def sms_text(kind, booking):
    moment = datetime.fromisoformat(booking["starts_at"]).astimezone(TZ).strftime("%Y.%m.%d. %H:%M")
    if kind == "confirmation":
        return f"Cellnet: Idopontja rogzitve: {moment}, {booking['service']}. Azonosito: CEL-{booking['id']}."
    if kind == "reminder":
        return f"Cellnet emlekezteto: Holnap {moment} idopontja van nalunk ({booking['service']}). Azonosito: CEL-{booking['id']}."
    raise ValueError("Unknown SMS kind")

def replace_pending(conn, booking, enabled):
    init_sms(conn)
    conn.execute("UPDATE sms_outbox SET status='cancelled' WHERE booking_id=? AND status='pending'", (booking["id"],))
    if not enabled:
        return
    phone = normalize_phone(booking["phone"])
    now = datetime.now(timezone.utc)
    starts = datetime.fromisoformat(booking["starts_at"]).astimezone(timezone.utc)
    messages = [("confirmation", now)]
    remind = starts - timedelta(hours=24)
    if remind > now:
        messages.append(("reminder", remind))
    for kind, due in messages:
        conn.execute("""INSERT INTO sms_outbox(booking_id,kind,phone,body,due_at,status,created_at)
                     VALUES (?,?,?,?,?,'pending',?)""",
                     (booking["id"], kind, phone, sms_text(kind, booking), due.isoformat(), now.isoformat()))

def cancel_pending(conn, booking_id):
    init_sms(conn)
    conn.execute("UPDATE sms_outbox SET status='cancelled' WHERE booking_id=? AND status='pending'", (booking_id,))

def outbox(conn, limit=100):
    init_sms(conn)
    return [dict(r) for r in conn.execute(
        "SELECT id, booking_id, kind, phone, body, due_at, status, sent_at, error FROM sms_outbox ORDER BY id DESC LIMIT ?", (limit,))]

"""Single-process SMS worker; dry-run by default. Never auto-retry uncertain sends."""
import os
import sqlite3
import time
from datetime import datetime, timezone

from .bulkgate import submit
from .sms import init_sms

DB = os.getenv("BOOKING_DB", "/data/booking.sqlite3")

def run_once():
    conn = sqlite3.connect(DB, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        init_sms(conn)
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("""
            SELECT o.* FROM sms_outbox o JOIN appointments a ON a.id=o.booking_id
            WHERE o.status='pending' AND a.status='booked' AND a.sms_enabled=1
            AND o.due_at<=? ORDER BY o.due_at, o.id LIMIT 1
        """, (datetime.now(timezone.utc).isoformat(),)).fetchone()
        if row is None:
            conn.commit()
            return False
        conn.execute("UPDATE sms_outbox SET status='processing' WHERE id=?", (row["id"],))
        conn.commit()
        # A successful HTTP call is 'accepted', not necessarily delivered to a handset.
        try:
            result = submit(row["phone"], row["body"], "cellnet-" + str(row["id"]))
            status = "simulated" if result["status"] == "dry_run" else "accepted"
            conn.execute("UPDATE sms_outbox SET status=?, sent_at=?, error=NULL WHERE id=?",
                         (status, datetime.now(timezone.utc).isoformat(), row["id"]))
        except Exception as exc:
            # No automatic retry: a timeout could mean BulkGate actually received the SMS.
            conn.execute("UPDATE sms_outbox SET status='failed', error=? WHERE id=?",
                         (str(exc)[:200], row["id"]))
        return True
    finally:
        conn.close()

if __name__ == "__main__":
    while True:
        try:
            while run_once():
                pass
        except Exception as exc:
            print("SMS worker: " + str(exc), flush=True)
        time.sleep(30)

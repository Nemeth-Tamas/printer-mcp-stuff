"""BulkGate transactional SMS client. Disabled unless SMS_MODE=live."""
import os
import httpx

ENDPOINT = "https://portal.bulkgate.com/api/1.0/simple/transactional"

def submit(phone: str, message: str, tag: str):
    if os.getenv("SMS_MODE", "dry-run") != "live":
        return {"status": "dry_run", "sms_id": None}
    app_id = os.getenv("BULKGATE_APPLICATION_ID", "").strip()
    token = os.getenv("BULKGATE_APPLICATION_TOKEN", "").strip()
    if not app_id or not token:
        raise RuntimeError("BulkGate credentials not configured")
    payload = {"application_id": app_id, "application_token": token,
               "number": phone.lstrip("+"), "text": message,
               "unicode": False, "tag": tag}
    sender = os.getenv("BULKGATE_SENDER", "").strip()
    if sender:
        payload.update(sender_id="gText", sender_id_value=sender)
    with httpx.Client(timeout=20) as client:
        response = client.post(ENDPOINT, json=payload)
        response.raise_for_status()
        result = response.json()
        if result.get("data", {}).get("status") not in ("accepted", "sent", "scheduled"):
            raise RuntimeError("BulkGate did not accept SMS: " + str(result.get("error", result.get("type", "unknown"))))
        return {"status": result["data"]["status"], "sms_id": result["data"].get("sms_id")}

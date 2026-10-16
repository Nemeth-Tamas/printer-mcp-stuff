"""Run with pytest and BOOKING_DB set to a temporary filename."""
import os
import tempfile
from pathlib import Path

fd, path = tempfile.mkstemp(suffix=".sqlite3")
os.close(fd)
os.environ["BOOKING_DB"] = path
os.environ["BOOKING_ADMIN_TOKEN"] = "test-secret-only"
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
HEADERS = {"Authorization": "Bearer test-secret-only"}

def test_auth_required():
    assert client.get("/api/appointments").status_code == 401

def test_create_list_cancel():
    payload = {"customer": "Teszt Ügyfél", "phone": "+36301234567",
               "service": "Laptop", "starts_at": "2026-10-19T10:00:00+02:00",
               "duration_minutes": 60, "notes": "Árvíztűrő"}
    res = client.post("/api/appointments", headers=HEADERS, json=payload)
    assert res.status_code == 201, res.text
    number = res.json()["id"]
    items = client.get("/api/appointments", headers=HEADERS).json()
    assert any(x["id"] == number for x in items)
    assert client.patch(f"/api/appointments/{number}/cancel", headers=HEADERS).status_code == 200

def test_naive_time_rejected():
    res = client.post("/api/appointments", headers=HEADERS, json={
        "customer": "Test", "phone": "+361234567", "service": "Laptop",
        "starts_at": "2026-10-19T10:00:00"})
    assert res.status_code == 422

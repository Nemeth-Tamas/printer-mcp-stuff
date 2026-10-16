"""Run with pytest and BOOKING_DB set to a temporary filename."""
import os
import tempfile
from pathlib import Path

fd, path = tempfile.mkstemp(suffix=".sqlite3")
os.close(fd)
os.environ["BOOKING_DB"] = path
from fastapi.testclient import TestClient
from app.main import app
from unittest.mock import patch

client = TestClient(app)

def test_create_list_cancel():
    payload = {"customer": "Teszt Ügyfél", "phone": "+36301234567",
               "service": "Laptop", "starts_at": "2026-10-19T10:00:00+02:00",
               "duration_minutes": 60, "notes": "Árvíztűrő"}
    with patch('app.main.fetch_events', return_value=([], True)), patch('app.main.create_event', return_value='test-event'):
        res = client.post("/api/appointments", json=payload)
    assert res.status_code == 201, res.text
    number = res.json()["id"]
    items = client.get("/api/appointments").json()
    assert any(x["id"] == number for x in items)
    with patch('app.main.delete_event'):
        assert client.patch(f"/api/appointments/{number}/cancel").status_code == 200

def test_naive_time_rejected():
    res = client.post("/api/appointments", json={
        "customer": "Test", "phone": "+361234567", "service": "Laptop",
        "starts_at": "2026-10-19T10:00:00"})
    assert res.status_code == 422

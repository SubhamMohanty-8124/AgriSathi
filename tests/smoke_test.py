"""Basic API smoke test. Run from project root: python tests/smoke_test.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app)
assert c.get("/api/health").status_code == 200
overview = c.get("/api/overview").json()
assert overview["farms"], "Expected seeded demo farm"
farm_id = overview["farms"][0]["id"]
zone = c.post("/api/zones", json={"farm_id":farm_id,"name":"Automated test plot","crop":"Paddy","area_acres":0.2,"moisture":25,"observation":"normal"})
assert zone.status_code == 200, zone.text
zone_id = zone.json()["id"]
reading = c.post("/api/readings", json={"zone_id":zone_id,"moisture":25,"source":"manual"})
assert reading.status_code == 200 and reading.json()["risk"]["level"] == "HIGH"
task = c.post("/api/tasks", json={"zone_id":zone_id,"title":"Test inspection","priority":"normal"})
assert task.status_code == 200
report = c.post("/api/reports", json={"zone_id":zone_id,"category":"General observation","notes":"Smoke test"})
assert report.status_code == 200
assert c.get("/api/export").status_code == 200
assert c.delete(f"/api/zones/{zone_id}").status_code == 200
print("AgriSathi API smoke tests passed.")

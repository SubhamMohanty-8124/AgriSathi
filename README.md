# AgriSathi — Intelligent Farm Decision & Risk Management System

**Team:** TECHKSHETRA · NIST University  
**Challenge:** HACK-KALP HK26-PS-13 — 5G-Enabled Smart Farming Assistant  
**Product:** AgriSathi — Intelligent Farm Decision & Risk Management System

This repository contains a software-first, paddy-focused farm workspace. It has a browser frontend, FastAPI backend, SQLite persistence, weather API integration, optional Gemini vision analysis, camera/microphone capture, field reports, task tracking, risk review and JSON export.

## Run locally (Windows / macOS / Linux)

Requirements: Python 3.10+ and internet access for package installation / weather / optional AI.

```bash
# 1. Extract this folder
cd AgriSathi_Round3

# 2. Create and activate a virtual environment
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start the application
uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000**. API docs are at **http://127.0.0.1:8000/docs**.

A demo farm and two illustrative paddy zones are seeded on first run. They are sample records, not live sensor readings. The database file `agrisathi.db` is created in the project root.

## Enable real AI crop-image triage

AI analysis is deliberately disabled until a server-side provider key is configured. No key belongs in browser JavaScript.

1. Copy `.env.example` to `.env`.
2. Set `GEMINI_API_KEY` and optionally `GEMINI_MODEL`.
3. Load environment variables before starting the server. For example, install `python-dotenv` and load it in `app/main.py`, or set the variables in your terminal / hosting dashboard.
4. Restart the backend.

For PowerShell:
```powershell
$env:GEMINI_API_KEY="YOUR_KEY"
$env:GEMINI_MODEL="gemini-2.5-flash"
uvicorn app.main:app --reload
```

The vision module requests cautious visual triage, possible causes, safe next steps and uncertainty. It explicitly avoids definitive diagnosis and pesticide dosage instructions. Review provider output with an agriculture expert. Provider model availability and account permissions can change.

## Weather

Weather uses Open-Meteo's forecast API from the backend. The UI starts with example coordinates near Ganjam, Odisha; change latitude/longitude to the farm's location. The weather panel reports the provider and retrieval time. Internet access is required. Do not treat forecast data as a field sensor reading.

## Camera and microphone

Camera and microphone use browser permissions and MediaRecorder / getUserMedia. They work on `localhost` for development and generally require HTTPS after deployment. The user must explicitly grant permission. Captured media is uploaded to the backend and referenced by a field report.

## Main modules

- Farm workspaces and field-zone CRUD
- Moisture readings with source labels
- Transparent demo risk prioritisation
- AI-assisted image triage (optional, real provider only)
- Current weather and 3-day forecast context
- Irrigation review (decision support, not an irrigation prescription)
- Field reports with photo and audio evidence
- Farm tasks and completion tracking
- Decision history and JSON data export
- Responsive desktop/mobile interface and a basic offline app shell

## Risk rules — demo thresholds only

The backend prioritises in this order:
- HIGH: observation is dry / wet / standing water, or moisture <30%, or moisture >=85%
- CHECK: moisture is missing or observation is unknown
- MODERATE: moisture <45%, if no higher-priority condition applies
- LOW: otherwise

These are prototype review triggers, **not scientifically validated paddy thresholds**. They must be calibrated and reviewed with qualified local agronomists before field use.

## Architecture

```text
Browser (responsive UI / camera / microphone)
       |
       | HTTP JSON + media upload
       v
FastAPI backend  -------------------> Open-Meteo weather API
       |                              Gemini Vision API (optional)
       |
       +---- SQLite database
       +---- Local media uploads
```

### API surface

- `GET /api/health`
- `GET /api/overview`
- `POST/PUT/DELETE /api/farms`
- `POST/PUT/DELETE /api/zones`
- `POST /api/readings`, `GET /api/readings/{zone_id}`
- `POST/GET/DELETE /api/reports`
- `POST /api/tasks`, `PATCH /api/tasks/{id}/toggle`, `DELETE /api/tasks/{id}`
- `GET /api/weather`
- `POST /api/analyse`
- `GET /api/history`
- `GET /api/export`

## Important limitations before public deployment

This is a runnable hackathon MVP, not a production multi-tenant SaaS yet.

- No production user authentication / role management.
- SQLite is intended for a local demo or single-instance prototype; use PostgreSQL for production.
- Media is stored on local disk; use object storage for a hosted multi-instance deployment.
- No cloud synchronisation / multi-device sync.
- Offline support caches the application shell only; data mutations still require the backend.
- Weather depends on internet and the third-party API.
- AI requires a valid Gemini key, enabled model and network. If unavailable, the app displays an error and does not invent a result.
- Sensor integration is intentionally omitted: this build is software-only. Manual or externally imported readings are labelled by source.
- No actual 5G performance is claimed.
- No agricultural recommendations are represented as expert-validated.

Before deploying publicly, add authentication, CSRF/rate limits as appropriate, strict upload validation, malware scanning, secure media access, PostgreSQL, object storage, backups, monitoring and privacy/consent policies. Restrict CORS and protect all farmer records.

## Prototype Demo flow (5–7 minutes)

1. Open the dashboard and explain sample-data labels.
2. Create a farm field zone.
3. Record a moisture value and show the risk reason.
4. Open weather and fetch a forecast for the demo location.
5. Review irrigation context and explain why it is decision support, not a command.
6. Create a field report with a camera photo or voice note.
7. Add and complete a farm task.
8. Export the data and show decision history.
9. If Gemini is configured, upload a crop image and explain uncertainty. If not, show the honest disabled state rather than a fake result.

## Reset demo data

Stop the server, delete `agrisathi.db` and the files in `uploads/`, then restart. The illustrative starter workspace will be seeded again.

## License / ownership

Hackathon prototype source for TECHKSHETRA. Review third-party API terms and dependencies before redistribution.

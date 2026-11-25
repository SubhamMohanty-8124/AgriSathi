# AgriSathi architecture notes

## Domain model

- Farm: a named workspace and geographic context.
- Zone: a distinct plot inside a farm, with crop, area, latest moisture and observation.
- SensorReading: timestamped moisture/environment reading with a source label.
- Report: farmer observation with optional uploaded photo/audio evidence.
- Task: scheduled farm activity with status and priority.
- Event: append-only activity record for important workspace changes.

## Data flow

1. Farmer enters field data in the browser.
2. Frontend sends validated JSON to FastAPI.
3. Backend writes to SQLite and records an event.
4. Overview endpoint returns farm, zone, task, report and event state.
5. Risk rules are computed from the latest zone values and returned with a reason.
6. Weather requests are proxied by the backend.
7. Crop image bytes are sent to Gemini only when a server-side key is configured.

## Trust boundaries

- Browser inputs are untrusted.
- API keys stay in server environment variables.
- Uploaded files are size- and MIME-limited; production should add content sniffing and malware scanning.
- AI output is untrusted and must be shown with uncertainty.
- The app does not prescribe pesticides or chemical dosages.
- Sample workspace values are explicitly illustrative.

## Production evolution

1. Replace SQLite with PostgreSQL and migrations.
2. Add farmer authentication, farm-level authorisation and audit permissions.
3. Move uploads to private object storage with signed URLs.
4. Add background jobs for weather refresh and notification delivery.
5. Add provider abstraction for vision models and source-grounded retrieval.
6. Add offline mutation queue with idempotency and conflict resolution.
7. Validate agronomic rules with OUAT / ICAR / local extension experts.

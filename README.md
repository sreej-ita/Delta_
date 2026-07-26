# Delta — Blue Carbon Ecosystem Monitoring

Delta is an MRV (Measurement, Reporting, Verification) dashboard for blue-carbon restoration projects. It combines satellite remote sensing (Sentinel-2, SRTM, MODIS, NASA GEDI) and machine learning to estimate carbon stocks, monitor forest health, and produce audit-ready evidence for carbon-credit verification.

The app is a React (Vite) frontend backed by a FastAPI REST API. The backend is stateless per request — every `/api/analyze` call resolves coordinates, queries satellite data, runs the ML model, and returns a complete result, with no server-side session state.

---

## Contents

- [Architecture](#architecture)
- [Key Features](#key-features)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
- [Data Persistence](#data-persistence)
- [Sandbox vs. Live Mode](#sandbox-vs-live-mode)
- [Troubleshooting](#troubleshooting)

---

## Architecture

```
┌─────────────────────┐        REST / JSON        ┌──────────────────────┐
│   React + Vite       │ ─────────────────────────▶ │   FastAPI backend     │
│   (frontend/)         │ ◀───────────────────────── │   (backend/)          │
└─────────────────────┘                             └──────────────────────┘
                                                              │
                                    ┌─────────────────────────┼─────────────────────────┐
                                    ▼                         ▼                         ▼
                          Google Earth Engine        Biomass/Carbon ML model     Gemini (chatbot)
                          (or Sandbox simulation)     (mangrove_biomass_model.pkl)  (google-genai)
```

- **Frontend** talks to the backend exclusively through `/api/*` routes, proxied in dev by Vite (`vite.config.js`) to `http://localhost:8000`.
- **Backend** persists state (custom projects, built-in project edits, user accounts) to small JSON files and a SQLite DB rather than in memory, so nothing is lost on restart.
- **Satellite data** comes from live Google Earth Engine queries when authenticated, or a deterministic **Sandbox Mode** simulation otherwise — toggleable per-request from the sidebar.
- **Chatbot** is a separate, optional integration (Gemini via `google-genai`) that grounds its answers in the same data the dashboard displays, with a rule-based fallback when Gemini isn't reachable.

---

## Key Features

### Monitoring Dashboard (per project)
- **Map** — satellite imagery (Esri World Imagery) with a place-name/roads/borders label overlay, project boundary highlighting, and custom-area drawing tools: freehand, rectangle, square, circle, and diamond. Drawing a shape re-runs the full analysis against that exact area.
- **Carbon Analytics** — total carbon stock, CO₂e, annual sequestration rate, aboveground/belowground/soil carbon breakdown, and 5-year NDVI/NDWI + carbon trend charts.
- **Vegetation Health** — NDVI (canopy density), NDWI (water index), and evapotranspiration stress, plus a 2-year ET/temperature trend chart.
- **Deforestation Alerts** — canopy-loss hotspots from real Sentinel-2 NDVI change detection (or simulated in Sandbox Mode), with severity, area lost, and location.
- **MRV Summary Report** — verification readiness score, a pass/warning/fail checklist, and one-click export of an audit-ready **PDF evidence pack**.
- **Sidebar** — Sandbox Mode toggle, refresh control, and project metadata (registry standard, trees planted, species).

### Project Management (landing page)
- Built-in projects: **Baha' Mou** (single location) and **Sundari** (11 named sub-location "blocks": Sagar, Namkhana, Patharpratima, Gosaba, Kakdwip, Mathurapur I, Basanti, Kultali, Hingalganj, Sandeshkhali I/II).
- **Add Project** — name, latitude/longitude (entered as **Degrees / Minutes / Direction**, e.g. `21° 50' N`, converted to decimal degrees internally), area (hectares), registry standard, trees planted, species.
- **Edit / Delete** via a three-dot menu on each project card:
  - Custom (user-added) projects are fully editable/deletable.
  - **Baha' Mou** is fully editable/deletable, same as custom projects.
  - **Sundari** is editable on its descriptive fields only (name, registry standard, trees planted, species) — its location is intentionally not editable here, since it's driven by the 11-block table used elsewhere in the app, not a single point.
  - "Deleting" Baha' Mou/Sundari doesn't remove their underlying logic — it sets a persisted `hidden` flag so they simply stop appearing in the list (reversible by editing `builtin_overrides.json`).
- All additions/edits/deletes persist to disk and survive both page reloads and backend restarts.
- A dropdown info banner (Features / How It Works / About Us) slides down from the top of the landing page hero, showing details for whichever one you click.

### AI Assistant
- Floating chat widget on every page except the landing page.
- Only answers questions about the platform, the mangrove/blue-carbon domain, and — when viewing a project — that project's actual figures (grounded in structured context built from the live `/api/analyze` result, not invented).
- Greetings and small talk ("hi", "I have a few questions") get a friendly reply instead of a refusal; genuinely unrelated questions get exactly `"irrelevant question"`.
- If Gemini is unreachable, a rule-based fallback can still answer common metric questions (NDVI, carbon, readiness, area, alerts, etc.) directly from the project context.

### MRV PDF Evidence Pack
7-part report: title page, project summary, monitoring period, key metrics, pre-verification checklist findings, methodological limitations, and an appendix (carbon pool breakdown + deforestation alert log). Built with `fpdf2`, with dynamically-sized layout so text never overflows its containing box regardless of content length.

---

## Project Structure

```
DELTA.IN/
├── backend/
│   ├── analytics.py             # verification checklist, readiness scoring, trend prep
│   ├── auth.py                  # JWT auth, SQLite users.db, bcrypt hashing
│   ├── backend_app.py           # alternate single-file combined build (all modules merged)
│   ├── biomass_ml.py            # ML biomass/carbon pool predictions
│   ├── chatbot_service.py       # Gemini chatbot + rule-based fallback
│   ├── gee_service.py           # Earth Engine integration + Sandbox Mode simulation
│   ├── main.py                  # FastAPI entry point — all routes
│   ├── pdf_report.py            # MRV evidence pack PDF generation
│   ├── requirements.txt
│   ├── train_biomass_model.py   # offline script to train mangrove_biomass_model.pkl
│   ├── custom_projects.json     # auto-created — user-added projects
│   ├── builtin_overrides.json   # auto-created — edits/hidden flags for Baha' Mou / Sundari
│   ├── users.db                 # auto-created — SQLite auth database
│   └── gee_cache/                # auto-created — cached GEE query results
│
├── frontend/
│   ├── public/
│   │   ├── logo.jpeg
│   │   ├── hero-mangrove.jpeg
│   │   └── mangrove-chatbot-icon.jpg
│   ├── src/
│   │   ├── components/
│   │   │   ├── CarbonAnalytics.jsx
│   │   │   ├── Chatbot.jsx
│   │   │   ├── DeforestationAlerts.jsx
│   │   │   ├── EcosystemReport.jsx
│   │   │   ├── MonitoringMap.jsx
│   │   │   ├── Shared.jsx        # MetricCard, InfoBox, SectionTitle, StatusBadge, Logo, Modal, AddProjectCard
│   │   │   ├── Sidebar.jsx
│   │   │   └── VegetationHealth.jsx
│   │   ├── lib/
│   │   │   ├── api.js            # API client + buildChatProjectContext()
│   │   │   ├── auth.jsx          # AuthContext / useAuth()
│   │   │   └── ProjectChatContext.jsx  # publishes current project data to the chatbot
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx
│   │   │   ├── landing.jsx
│   │   │   ├── login.jsx
│   │   │   ├── ProjectDetail.jsx
│   │   │   └── signup.jsx
│   │   ├── App.jsx               # routes, wraps app in ProjectChatProvider
│   │   ├── main.jsx              # React entry point (BrowserRouter)
│   │   └── index.css             # Tailwind + custom theme, hero styling
│   ├── index.html
│   ├── package.json
│   ├── postcss.config.js
│   ├── tailwind.config.js
│   └── vite.config.js
│
└── README.md
```

---

## Getting Started

### Prerequisites
- Python 3.10+
- Node.js 18+
- (Optional, for live satellite data) A Google Earth Engine account/credentials — without this, the app automatically runs in **Sandbox Mode**.
- (Optional, for the AI assistant) A Gemini API key.

### Backend setup
```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt

# Create backend/.env — see Environment Variables below

uvicorn main:app --reload --port 8000
```
> There's also `backend_app.py`, a single-file build combining every module (`uvicorn backend_app:app --reload --port 8000`). Pick **one** entry point to run consistently — edits to the individual modules (`main.py`, `chatbot_service.py`, etc.) won't take effect if you're actually running `backend_app.py`, since it's a separately merged copy.

### Frontend setup
```bash
cd frontend
npm install
npm run dev
```
Runs on `http://localhost:5173` and proxies all `/api/*` requests to the backend on port 8000 (see `vite.config.js`) — no CORS issues in development.

---

## Environment Variables

Create `backend/.env` (requires `python-dotenv`, already in `requirements.txt`):

```env
GEMINI_API_KEY=your_key_here
```

- **`GEMINI_API_KEY`** — powers the AI assistant via `google-genai`. Without it, the chatbot still works using a rule-based fallback (greetings, and direct lookups for common metrics like NDVI/carbon/readiness from the currently-viewed project), just without full natural-language reasoning.
- **Earth Engine credentials** — needed only for live satellite data; configure per your Earth Engine account setup (see `gee_service.py`). Without valid credentials, or with Sandbox Mode toggled on in the sidebar, the app uses deterministic simulated data instead — the rest of the app behaves identically either way.

`.env` must sit in `backend/` (next to `main.py`), and the backend must be restarted after any change — environment variables are only read once, at process startup.

---

## API Reference

All routes are prefixed `/api`.

| Method & Path | Purpose |
|---|---|
| `GET /health` | Health check |
| `GET /sites` | List all projects (built-in + custom + "draw custom area") |
| `POST /sites` | Add a new custom project |
| `GET /sites/{id}` | Full editable record for one project (pre-fills the Edit modal) |
| `PUT /sites/{id}` | Edit a custom project (full record) |
| `PUT /sites/{id}/metadata` | Edit Baha' Mou / Sundari's descriptive fields only |
| `DELETE /sites/{id}` | Delete a custom project, or hide a built-in one |
| `POST /analyze` | Run satellite analysis + carbon/ML estimate for a site or custom-drawn area |
| `POST /report/pdf` | Generate and stream the MRV evidence pack PDF |
| `POST /chat` | AI assistant — accepts `message`, `history`, and optional `project_context` |
| `POST /auth/signup` | Create an account |
| `POST /auth/login` | Sign in, returns a JWT (7-day expiry) |
| `GET /auth/me` | Current user from the JWT |

---

## Data Persistence

| File | What it stores |
|---|---|
| `backend/custom_projects.json` | User-added projects (name, coordinates, area, registry info) |
| `backend/builtin_overrides.json` | Edits and `hidden` flags for Baha' Mou / Sundari |
| `backend/users.db` | User accounts (SQLite) |
| `backend/gee_cache/` | Cached Earth Engine query results, keyed by spatial coordinates |

All of the above are created automatically on first write — safe to delete any of them to reset that piece of state (e.g. delete `custom_projects.json` to clear all user-added projects).

---

## Sandbox vs. Live Mode

Every analysis request can run against real Earth Engine data or a deterministic offline simulation:

- **Live mode** — real Sentinel-2 NDVI/NDWI, SRTM elevation, MODIS ET stress, NASA GEDI canopy height/biomass, and real Sentinel-2 change detection for deforestation alerts.
- **Sandbox Mode** — the same shapes of data, generated deterministically offline, so the full dashboard (charts, checklist, PDF export) works identically without any Earth Engine credentials. Toggle this per-request from the Sidebar.

---

## Troubleshooting

**Chatbot always replies with the generic fallback message.**
Check the backend terminal right after a restart for a line starting with `Chatbot:` — it states the exact cause:
- `google-genai` not installed — note this is different from the older `google-generativeai` package; verify with `python3 -c "from google import genai; print(genai.__file__)"`.
- `GEMINI_API_KEY` not visible to the running process — confirm `.env` is in `backend/`, `python-dotenv` is installed, and the backend was restarted (env vars load once at startup, not live).
- Confirm you're running `main.py`, not `backend_app.py` (see [Getting Started](#getting-started)) — they're separate copies.

**A newly added/edited/deleted project disappears after a backend restart.**
Confirm `backend/custom_projects.json` (or `builtin_overrides.json` for Baha' Mou/Sundari) is actually being written — check the backend process has write permission to its own directory.

**PDF report layout looks broken.**
The report layout is self-sizing (box heights and header spacing are computed from actual content, not hardcoded), so this should not recur; if it does, it's likely in a customization made to `pdf_report.py` rather than the base logic.

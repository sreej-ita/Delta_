# Blue Carbon Ecosystem Monitor — React + FastAPI Rebuild

Your original Streamlit app, rebuilt as a proper React frontend + FastAPI
backend. **All the science/logic is untouched** — `gee_service.py`,
`biomass_ml.py`, `analytics.py`, and `pdf_report.py` are copied over exactly
as you wrote them (they never imported Streamlit, so they didn't need to
change at all). Only the presentation layer changed.

## What changed vs. the Streamlit version

| Streamlit | React + FastAPI |
|---|---|
| `mainapp.py` (UI + logic mixed) | `backend/main.py` (REST API) + React pages/components |
| `st.session_state` | JWT-authenticated API calls, React state |
| Folium flat map | MapLibre GL **3D** satellite map — tilt, rotate, extruded project boundary, free-draw custom polygons |
| Plotly charts | Recharts (same chart types: line, area, pie, composed bar+line) |
| No login | Full sign up / sign in with hashed passwords + JWT, backed by SQLite |
| `st.download_button` for PDF | `/api/report/pdf` endpoint, browser-native download |

## Project structure

```
project/
├── backend/
│   ├── main.py              ← FastAPI app, all routes
│   ├── auth.py               ← signup/login/JWT
│   ├── gee_service.py        ← unchanged from your original
│   ├── biomass_ml.py         ← unchanged from your original
│   ├── analytics.py          ← unchanged from your original
│   ├── pdf_report.py         ← unchanged from your original
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── pages/             (Login, Signup, Dashboard)
    │   ├── components/        (MonitoringMap, CarbonAnalytics, VegetationHealth,
    │   │                        DeforestationAlerts, EcosystemReport, Sidebar)
    │   └── lib/                (api.js, auth.jsx)
    └── package.json
```

## Setup

### 1. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Drop your `mangrove_biomass_model.pkl` (from `train_biomass_model.py`) into
the `backend/` folder if you have one — `biomass_ml.py` will pick it up
automatically, exactly like before.

If you use **live** Google Earth Engine, make sure your GEE service account
credentials are configured the same way they were for the Streamlit app
(same `ee.Initialize()` call inside `gee_service.py`, untouched).

Run it:
```bash
uvicorn main:app --reload --port 8000
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Visit `http://localhost:5173`. The Vite dev server proxies `/api/*` to
`http://localhost:8000` (see `vite.config.js`), so both need to be running.

## Notes on the 3D map

The map uses **MapLibre GL JS** with Esri World Imagery (free satellite
tiles, no API key) plus open elevation data for terrain tilt. Your project
boundary renders as a translucent extruded green block hovering over the
real terrain — drag to rotate, scroll to zoom, use the "Draw custom
boundary" button to define a new polygon by clicking points on the map
(replaces Folium's draw plugin). This all runs client-side; no map API key
is required.

## Auth

Sign up creates a row in `backend/users.db` (SQLite, auto-created on first
run) with a bcrypt-hashed password, and returns a JWT stored in the
browser. All `/api/analyze` and `/api/report/pdf` calls require this token.
For production, set a real `APP_SECRET_KEY` environment variable instead of
the default dev key in `auth.py`.

## What to check before you consider this "done"

- The habitat validation gate, checklist logic, readiness scoring, and PDF
  generation are all wired to the same functions you already had — verify
  a real analysis end-to-end once your GEE credentials are in place.
- Sundari CD block coordinates and the Baha' Mou reference point are copied
  from your `mainapp.py` constants into `backend/main.py` — double check
  they match if you've updated them since.

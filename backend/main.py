"""
main.py — Blue Carbon Ecosystem Monitor API

Rebuilds the original Streamlit app as a stateless REST API. All the actual
science/ML logic (gee_service, biomass_ml, analytics, pdf_report) is reused
unchanged from the Streamlit version — only the presentation layer moved to
React, and per-request state replaces st.session_state.
"""
import json
import math
import re
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field
from typing import Optional, List

from gee_service import GEEService, validate_mangrove_habitat, locate_real_mangrove_center
from biomass_ml import BiomassModel
from pdf_report import generate_pdf_report
from analytics import (
    prepare_ndvi_ndwi_trend_chart,
    prepare_carbon_trend_chart,
    get_verification_checklist,
    get_readiness_score,
    get_credit_readiness_status,
)
from auth import router as auth_router, get_current_user

app = FastAPI(title="Blue Carbon Ecosystem Monitor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your frontend origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)

# Long-lived, in-process singletons (mirrors the old st.session_state services)
gee_live = GEEService(use_sandbox=False)
gee_sandbox = GEEService(use_sandbox=True)
biomass_model = BiomassModel()

# ----------------------------------------------------
# CONSTANTS & LOCATION TEMPLATES (unchanged from mainapp.py)
# ----------------------------------------------------
BAHA_MOU_REFERENCE = (22.1652, 88.8079)

SUNDARBANS_BLOCKS = {
    "Sagar": (21.6528, 88.0753),
    "Namkhana": (21.7699, 88.2315),
    "Patharpratima": (21.7941, 88.3555),
    "Gosaba": (22.1652, 88.8079),
    "Kakdwip": (21.8791, 88.1913),
    "Mathurapur I": (22.1217, 88.4053),
    "Basanti": (22.1983, 88.7139),
    "Kultali": (22.0866, 88.5937),
    "Hingalganj": (22.4708, 88.9773),
    "Sandeshkhali I": (22.3600, 88.9000),
    "Sandeshkhali II": (22.3600, 88.9000),
}

# Reserved ids that a user-added project must never collide with
RESERVED_SITE_IDS = {"baha_mou", "sundari", "custom"}

# Custom projects (added via the "Add Project" UI) are persisted to a JSON
# file on disk so they survive both page reloads AND backend restarts —
# not just kept in memory, which would be wiped on every server restart.
PROJECTS_FILE = Path(__file__).resolve().parent / "custom_projects.json"


def load_custom_projects() -> dict:
    if PROJECTS_FILE.exists():
        try:
            with open(PROJECTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_custom_projects():
    try:
        with open(PROJECTS_FILE, "w", encoding="utf-8") as f:
            json.dump(CUSTOM_PROJECTS, f, indent=2)
    except OSError:
        pass  # best-effort persistence; project stays usable in memory regardless


CUSTOM_PROJECTS: dict[str, dict] = load_custom_projects()

# Baha' Mou and Sundari are otherwise hardcoded in this file's logic (a fixed
# reference point / a table of sub-location "blocks"). To make them editable
# and deletable from the UI without disturbing that underlying logic (which
# Sundari's block-selector elsewhere in the app depends on), edits are stored
# as lightweight "overrides" layered on top at request time, and "delete" is
# a persisted hidden flag rather than removing the built-in logic itself.
BUILTIN_PROJECT_IDS = {"baha_mou", "sundari"}
BUILTIN_DEFAULT_LABELS = {
    "baha_mou": "Baha' Mou Mangrove Restoration Project, Sundarbans",
    "sundari": "Sundari Mangrove Restoration Project, Kakdwip",
}
BUILTIN_OVERRIDES_FILE = Path(__file__).resolve().parent / "builtin_overrides.json"


def load_builtin_overrides() -> dict:
    if BUILTIN_OVERRIDES_FILE.exists():
        try:
            with open(BUILTIN_OVERRIDES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_builtin_overrides():
    try:
        with open(BUILTIN_OVERRIDES_FILE, "w", encoding="utf-8") as f:
            json.dump(BUILTIN_OVERRIDES, f, indent=2)
    except OSError:
        pass


BUILTIN_OVERRIDES: dict[str, dict] = load_builtin_overrides()


def builtin_label(site_id: str) -> str:
    override = BUILTIN_OVERRIDES.get(site_id, {})
    return override.get("name") or BUILTIN_DEFAULT_LABELS[site_id]


def builtin_hidden(site_id: str) -> bool:
    return BUILTIN_OVERRIDES.get(site_id, {}).get("hidden", False)


def builtin_meta(site_id: str, base_meta: dict) -> dict:
    override = BUILTIN_OVERRIDES.get(site_id, {})
    merged = dict(base_meta)
    if override.get("registry_standard"):
        merged["standard"] = override["registry_standard"]
    if override.get("trees_planted"):
        merged["trees"] = override["trees_planted"]
    if override.get("species"):
        merged["species"] = override["species"]
    return merged


def block_to_polygon(lat, lng, half_width_deg=0.04):
    return [
        [lng - half_width_deg, lat - half_width_deg],
        [lng + half_width_deg, lat - half_width_deg],
        [lng + half_width_deg, lat + half_width_deg],
        [lng - half_width_deg, lat + half_width_deg],
        [lng - half_width_deg, lat - half_width_deg],
    ]


def hectares_to_polygon(lat, lng, area_ha):
    """
    Builds a square boundary box centered on (lat, lng) whose area matches
    area_ha as closely as possible. Longitude degrees are compressed by
    cos(latitude) since a degree of longitude covers less ground distance
    the further you are from the equator.
    """
    area_km2 = area_ha * 0.01  # 1 hectare = 0.01 km^2
    side_km = math.sqrt(area_km2)
    half_km = side_km / 2

    half_lat_deg = half_km / 111.32
    lng_compression = max(math.cos(math.radians(lat)), 1e-6)
    half_lng_deg = half_km / (111.32 * lng_compression)

    return [
        [lng - half_lng_deg, lat - half_lat_deg],
        [lng + half_lng_deg, lat - half_lat_deg],
        [lng + half_lng_deg, lat + half_lat_deg],
        [lng - half_lng_deg, lat + half_lat_deg],
        [lng - half_lng_deg, lat - half_lat_deg],
    ]


def resolve_coords(reference_lat, reference_lng, gee_service, area_ha=None):
    relocated = None
    if gee_service.is_live():
        relocated = locate_real_mangrove_center(reference_lat, reference_lng)
    final_lat, final_lng = relocated if relocated else (reference_lat, reference_lng)

    if area_ha:
        return hectares_to_polygon(final_lat, final_lng, area_ha)
    return block_to_polygon(final_lat, final_lng)


def default_meta_for(project_type, block_name=None):
    if project_type == "baha_mou":
        return {
            "type": "baha_mou",
            "standard": "Verified Carbon Standard (VCS)",
            "trees": "12 Million",
            "species": "14 native species (Sundari, Garjan, Kankra, etc.)",
            "data_confidence": "approximate",
        }
    if project_type == "sundari":
        return {
            "type": "sundari",
            "standard": "Verified Carbon Standard (VCS)",
            "trees": "14 Million",
            "species": "Native Sundari & associate species",
            "data_confidence": "verified",
            "block_name": block_name,
        }
    if project_type == "user_added":
        return {
            "type": "user_added",
            "standard": "N/A (Evaluation Zone)",
            "trees": "N/A",
            "species": "N/A",
            "data_confidence": "approximate",
        }
    return {
        "type": "generic",
        "standard": "N/A (Evaluation Zone)",
        "trees": "N/A",
        "species": "N/A",
        "data_confidence": "unverified",
    }


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "project"


def make_unique_site_id(name: str) -> str:
    base = slugify(name)
    candidate = base
    taken = RESERVED_SITE_IDS | set(SUNDARBANS_BLOCKS.keys()) | set(CUSTOM_PROJECTS.keys())
    if candidate not in taken:
        return candidate
    # append a short unique suffix on collision
    return f"{base}-{uuid.uuid4().hex[:6]}"


# ----------------------------------------------------
# Schemas
# ----------------------------------------------------
class SiteOption(BaseModel):
    id: str
    label: str
    blocks: Optional[List[str]] = None
    editable: bool = False  # True only for user-added projects (Baha' Mou / Sundari are built-in)


class ProjectDetailResponse(BaseModel):
    id: str
    name: str
    kind: str  # "custom" (full editable record) | "builtin" (Baha' Mou / Sundari)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    area_ha: Optional[float] = None
    registry_standard: str
    trees_planted: str
    species: str


class BuiltinProjectUpdateRequest(BaseModel):
    """Edits for Baha' Mou / Sundari: descriptive fields only — their
    location logic (fixed reference point / block table) stays as-is."""
    name: str = Field(..., min_length=1, max_length=120)
    registry_standard: str = Field(..., min_length=1, max_length=200)
    trees_planted: str = Field(..., min_length=1, max_length=100)
    species: str = Field(..., min_length=1, max_length=300)


class AnalyzeRequest(BaseModel):
    site_id: Optional[str] = None          # "baha_mou" | "sundari" | "custom" | <user-added id>
    block_name: Optional[str] = None       # required when site_id == "sundari"
    custom_coords: Optional[list] = None   # [[lng,lat], ...] when site_id == "custom"
    use_sandbox: bool = False
    force_refresh: bool = False


class ReportRequest(BaseModel):
    project_name: str
    analysis: dict
    carbon: dict
    project_meta: dict


class NewProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    area_ha: float = Field(..., gt=0, le=1_000_000)
    registry_standard: str = Field(..., min_length=1, max_length=200)
    trees_planted: str = Field(..., min_length=1, max_length=100)
    species: str = Field(..., min_length=1, max_length=300)


# ----------------------------------------------------
# Routes
# ----------------------------------------------------
@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


@app.get("/api/sites", response_model=List[SiteOption])
def list_sites():
    sites = []

    if not builtin_hidden("baha_mou"):
        sites.append(SiteOption(id="baha_mou", label=builtin_label("baha_mou"), editable=True))

    if not builtin_hidden("sundari"):
        sites.append(SiteOption(
            id="sundari", label=builtin_label("sundari"),
            blocks=list(SUNDARBANS_BLOCKS.keys()), editable=True,
        ))

    # user-added projects, most recently added first
    for project in reversed(list(CUSTOM_PROJECTS.values())):
        sites.append(SiteOption(id=project["id"], label=project["name"], editable=True))

    sites.append(SiteOption(id="custom", label="Draw custom area on map"))
    return sites


@app.post("/api/sites", response_model=SiteOption)
def add_site(payload: NewProjectRequest):
    """
    Registers a new project from a name + lat/lng pair (the "Add Project"
    popup on the landing page). Stores it in-memory and immediately makes it
    resolvable by /api/analyze under its generated id.
    """
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "Project name is required.")

    site_id = make_unique_site_id(name)
    CUSTOM_PROJECTS[site_id] = {
        "id": site_id,
        "name": name,
        "latitude": payload.latitude,
        "longitude": payload.longitude,
        "area_ha": payload.area_ha,
        "registry_standard": payload.registry_standard.strip(),
        "trees_planted": payload.trees_planted.strip(),
        "species": payload.species.strip(),
        "created_at": datetime.utcnow().isoformat(),
    }
    save_custom_projects()
    return SiteOption(id=site_id, label=name, editable=True)


@app.get("/api/sites/{site_id}", response_model=ProjectDetailResponse)
def get_site(site_id: str):
    """
    Returns the editable record for a project — used to pre-fill the
    Edit modal. Custom projects return full lat/lng/area; built-in projects
    (Baha' Mou, Sundari) return kind="builtin" with those fields as null,
    since their location logic isn't a simple single point/area.
    """
    if site_id in CUSTOM_PROJECTS:
        project = CUSTOM_PROJECTS[site_id]
        return ProjectDetailResponse(
            id=project["id"],
            name=project["name"],
            kind="custom",
            latitude=project["latitude"],
            longitude=project["longitude"],
            area_ha=project["area_ha"],
            registry_standard=project.get("registry_standard", ""),
            trees_planted=project.get("trees_planted", ""),
            species=project.get("species", ""),
        )

    if site_id in BUILTIN_PROJECT_IDS and not builtin_hidden(site_id):
        base_meta = default_meta_for(site_id)
        meta = builtin_meta(site_id, base_meta)
        return ProjectDetailResponse(
            id=site_id,
            name=builtin_label(site_id),
            kind="builtin",
            registry_standard=meta.get("standard", ""),
            trees_planted=meta.get("trees", ""),
            species=meta.get("species", ""),
        )

    raise HTTPException(404, "Project not found or is not editable.")


@app.put("/api/sites/{site_id}", response_model=SiteOption)
def update_site(site_id: str, payload: NewProjectRequest):
    """
    Edits an existing user-added project in place. The site_id is kept
    stable even if the name changes, so existing links/URLs to this
    project's dashboard keep working after a rename.
    """
    if site_id not in CUSTOM_PROJECTS:
        raise HTTPException(404, "Project not found or is not editable.")

    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "Project name is required.")

    CUSTOM_PROJECTS[site_id].update({
        "name": name,
        "latitude": payload.latitude,
        "longitude": payload.longitude,
        "area_ha": payload.area_ha,
        "registry_standard": payload.registry_standard.strip(),
        "trees_planted": payload.trees_planted.strip(),
        "species": payload.species.strip(),
        "updated_at": datetime.utcnow().isoformat(),
    })
    save_custom_projects()
    return SiteOption(id=site_id, label=name, editable=True)


@app.put("/api/sites/{site_id}/metadata", response_model=SiteOption)
def update_builtin_metadata(site_id: str, payload: BuiltinProjectUpdateRequest):
    """
    Edits the descriptive fields (name, registry standard, trees planted,
    species) for Baha' Mou or Sundari. Their coordinates/blocks are not
    editable here — Sundari in particular is driven by SUNDARBANS_BLOCKS
    elsewhere in the app (its block selector), so it isn't a single point.
    """
    if site_id not in BUILTIN_PROJECT_IDS or builtin_hidden(site_id):
        raise HTTPException(404, "Project not found or is not editable.")

    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "Project name is required.")

    BUILTIN_OVERRIDES.setdefault(site_id, {}).update({
        "name": name,
        "registry_standard": payload.registry_standard.strip(),
        "trees_planted": payload.trees_planted.strip(),
        "species": payload.species.strip(),
        "updated_at": datetime.utcnow().isoformat(),
    })
    save_builtin_overrides()
    return SiteOption(id=site_id, label=name, editable=True)


@app.delete("/api/sites/{site_id}")
def delete_site(site_id: str):
    if site_id in CUSTOM_PROJECTS:
        del CUSTOM_PROJECTS[site_id]
        save_custom_projects()
        return {"deleted": True, "id": site_id}

    if site_id in BUILTIN_PROJECT_IDS and not builtin_hidden(site_id):
        # "Deleting" a built-in project hides it from the list rather than
        # removing its underlying logic — safe to reverse later if needed
        # by editing builtin_overrides.json directly.
        BUILTIN_OVERRIDES.setdefault(site_id, {})["hidden"] = True
        save_builtin_overrides()
        return {"deleted": True, "id": site_id, "hidden": True}

    raise HTTPException(404, "Project not found or is not editable.")


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    """
    Single endpoint that replaces the old session-state pipeline:
    resolve coordinates -> fetch satellite analysis -> validate habitat ->
    predict biomass/carbon. Stateless: the frontend sends back whatever
    coords/site it wants analyzed each time.
    """
    gee_service = gee_sandbox if req.use_sandbox else gee_live

    if req.site_id == "sundari":
        if builtin_hidden("sundari"):
            raise HTTPException(404, "Project not found.")
        if not req.block_name or req.block_name not in SUNDARBANS_BLOCKS:
            raise HTTPException(400, "Valid block_name is required for the Sundari project.")
        ref_lat, ref_lng = SUNDARBANS_BLOCKS[req.block_name]
        coords = resolve_coords(ref_lat, ref_lng, gee_service)
        project_name = f"{builtin_label('sundari')} - {req.block_name}"
        project_meta = builtin_meta("sundari", default_meta_for("sundari", req.block_name))

    elif req.site_id == "custom":
        if not req.custom_coords:
            raise HTTPException(400, "custom_coords is required for a custom site.")
        coords = req.custom_coords
        project_name = "Custom Area Site"
        project_meta = default_meta_for("generic")

    elif req.site_id in CUSTOM_PROJECTS:
        project = CUSTOM_PROJECTS[req.site_id]
        coords = resolve_coords(
            project["latitude"], project["longitude"], gee_service,
            area_ha=project.get("area_ha"),
        )
        project_name = project["name"]
        project_meta = {
            "type": "user_added",
            "standard": project.get("registry_standard") or "N/A (Evaluation Zone)",
            "trees": project.get("trees_planted") or "N/A",
            "species": project.get("species") or "N/A",
            "data_confidence": "approximate",
        }

    else:  # baha_mou / default
        if req.site_id == "baha_mou" and builtin_hidden("baha_mou"):
            raise HTTPException(404, "Project not found.")
        coords = resolve_coords(*BAHA_MOU_REFERENCE, gee_service)
        project_name = builtin_label("baha_mou")
        project_meta = builtin_meta("baha_mou", default_meta_for("baha_mou"))

    analysis = gee_service.analyze_area(coords, project_meta, force_refresh=req.force_refresh)

    is_valid, reasons = validate_mangrove_habitat(
        analysis.get("current_ndvi"),
        analysis.get("current_ndwi"),
        analysis.get("mean_elevation_m"),
        mangrove_fraction=analysis.get("mangrove_coverage_fraction"),
    )

    if not is_valid:
        return {
            "project_name": project_name,
            "project_meta": project_meta,
            "coords": coords,
            "is_live": gee_service.is_live(),
            "habitat_valid": False,
            "habitat_reasons": reasons,
            "analysis": analysis,
            "carbon": None,
        }

    carbon = biomass_model.predict_biomass_and_carbon(
        ndvi=analysis["current_ndvi"],
        ndwi=analysis["current_ndwi"],
        area_ha=analysis["area_ha"],
        real_agbd_per_ha=analysis.get("gedi_measured_agb_per_ha"),
        canopy_height_m=analysis.get("gedi_canopy_height_m", 15.4),
    )

    ndvi_ndwi_trend = prepare_ndvi_ndwi_trend_chart(analysis)
    carbon_trend = prepare_carbon_trend_chart(analysis, carbon)
    checklist = get_verification_checklist(analysis, carbon, project_meta, is_live=gee_service.is_live())
    readiness = get_credit_readiness_status(checklist, carbon)

    return {
        "project_name": project_name,
        "project_meta": project_meta,
        "coords": coords,
        "is_live": gee_service.is_live(),
        "habitat_valid": True,
        "habitat_reasons": [],
        "analysis": analysis,
        "carbon": carbon,
        "ndvi_ndwi_trend": ndvi_ndwi_trend,
        "carbon_trend": carbon_trend,
        "checklist": checklist,
        "readiness": readiness,
    }


@app.post("/api/report/pdf")
def report_pdf(req: ReportRequest):
    checklist = get_verification_checklist(
        req.analysis, req.carbon, req.project_meta,
        is_live=req.analysis.get("is_live", False),
    )
    pdf_bytes = generate_pdf_report(
        req.project_name, req.analysis, req.carbon, req.project_meta, checklist=checklist
    )
    proj_clean = req.project_name.replace(" ", "_").replace("-", "_")
    date_str = datetime.now().strftime("%Y%m%d")
    filename = f"MRV_Evidence_Pack_{proj_clean}_{date_str}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

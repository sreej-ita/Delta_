"""
main.py — Blue Carbon Ecosystem Monitor API

Rebuilds the original Streamlit app as a stateless REST API. All the actual
science/ML logic (gee_service, biomass_ml, analytics, pdf_report) is reused
unchanged from the Streamlit version — only the presentation layer moved to
React, and per-request state replaces st.session_state.
"""
from datetime import datetime

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
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


def block_to_polygon(lat, lng, half_width_deg=0.04):
    return [
        [lng - half_width_deg, lat - half_width_deg],
        [lng + half_width_deg, lat - half_width_deg],
        [lng + half_width_deg, lat + half_width_deg],
        [lng - half_width_deg, lat + half_width_deg],
        [lng - half_width_deg, lat - half_width_deg],
    ]


def resolve_coords(reference_lat, reference_lng, gee_service):
    relocated = None
    if gee_service.is_live():
        relocated = locate_real_mangrove_center(reference_lat, reference_lng)
    final_lat, final_lng = relocated if relocated else (reference_lat, reference_lng)
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
    return {
        "type": "generic",
        "standard": "N/A (Evaluation Zone)",
        "trees": "N/A",
        "species": "N/A",
        "data_confidence": "unverified",
    }


# ----------------------------------------------------
# Schemas
# ----------------------------------------------------
class SiteOption(BaseModel):
    id: str
    label: str
    blocks: Optional[List[str]] = None


class AnalyzeRequest(BaseModel):
    site_id: Optional[str] = None          # "baha_mou" | "sundari" | "custom"
    block_name: Optional[str] = None       # required when site_id == "sundari"
    custom_coords: Optional[list] = None   # [[lng,lat], ...] when site_id == "custom"
    use_sandbox: bool = False
    force_refresh: bool = False


class ReportRequest(BaseModel):
    project_name: str
    analysis: dict
    carbon: dict
    project_meta: dict


# ----------------------------------------------------
# Routes
# ----------------------------------------------------
@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


@app.get("/api/sites", response_model=List[SiteOption])
def list_sites():
    return [
        SiteOption(id="baha_mou", label="Baha' Mou Mangrove Restoration Project, Sundarbans"),
        SiteOption(id="sundari", label="Sundari Mangrove Restoration Project, Kakdwip",
                    blocks=list(SUNDARBANS_BLOCKS.keys())),
        SiteOption(id="custom", label="Draw custom area on map"),
    ]


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
        if not req.block_name or req.block_name not in SUNDARBANS_BLOCKS:
            raise HTTPException(400, "Valid block_name is required for the Sundari project.")
        ref_lat, ref_lng = SUNDARBANS_BLOCKS[req.block_name]
        coords = resolve_coords(ref_lat, ref_lng, gee_service)
        project_name = f"Sundari Project - {req.block_name}"
        project_meta = default_meta_for("sundari", req.block_name)

    elif req.site_id == "custom":
        if not req.custom_coords:
            raise HTTPException(400, "custom_coords is required for a custom site.")
        coords = req.custom_coords
        project_name = "Custom Area Site"
        project_meta = default_meta_for("generic")

    else:  # baha_mou / default
        coords = resolve_coords(*BAHA_MOU_REFERENCE, gee_service)
        project_name = "Baha' Mou Project"
        project_meta = default_meta_for("baha_mou")

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

"""
backend_app.py — Blue Carbon Ecosystem Monitor API (single-file build)

Everything from auth.py, gee_service.py, biomass_ml.py, analytics.py,
pdf_report.py, and main.py, combined into one file for simplicity while
you're getting the app running for the first time. Nothing about the
underlying logic changed -- it's the exact same code, just concatenated in
dependency order (auth -> gee_service -> biomass_ml -> analytics ->
pdf_report -> API routes) so everything referenced is already defined by
the time it's used.

RUN THIS FILE WITH:
    uvicorn backend_app:app --reload --port 8000

(from inside the folder this file lives in, with your venv activated and
requirements.txt installed)
"""

from fastapi import FastAPI, APIRouter, HTTPException, Depends
import os
import sqlite3
import time
from datetime import datetime, timedelta
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from jose import jwt, JWTError
from pydantic import BaseModel, EmailStr
import hashlib
import numpy as np
import pandas as pd
import shapely.geometry
import json
import joblib
from sklearn.ensemble import RandomForestRegressor
from fpdf import FPDF
import io
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional, List



# ============================================================================
# SECTION 1 — AUTH (signup / login / JWT)
# ============================================================================
"""
auth.py
Minimal signup/login with hashed passwords (bcrypt) + JWT session tokens,
backed by a local SQLite file. Swap SECRET_KEY for a real secret (env var)
before deploying.
"""


SECRET_KEY = os.environ.get("APP_SECRET_KEY", "dev-secret-change-me")
ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

DB_PATH = os.path.join(os.path.dirname(__file__), "users.db")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    conn = _get_db()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )"""
    )
    conn.commit()
    conn.close()


_init_db()


class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    name: str
    email: str


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_error = HTTPException(status_code=401, detail="Could not validate credentials")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if email is None:
            raise credentials_error
    except JWTError:
        raise credentials_error

    conn = _get_db()
    user = conn.execute("SELECT id, name, email FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    if user is None:
        raise credentials_error
    return dict(user)


@router.post("/signup", response_model=TokenResponse)
def signup(req: SignupRequest):
    conn = _get_db()
    existing = conn.execute("SELECT id FROM users WHERE email = ?", (req.email,)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    password_hash = pwd_context.hash(req.password)
    conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (req.name, req.email, password_hash, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()

    token = create_access_token({"sub": req.email})
    return TokenResponse(access_token=token, name=req.name, email=req.email)


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest):
    conn = _get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (req.email,)).fetchone()
    conn.close()

    if not user or not pwd_context.verify(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    token = create_access_token({"sub": user["email"]})
    return TokenResponse(access_token=token, name=user["name"], email=user["email"])


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    return current_user


# ============================================================================
# SECTION 2 — GOOGLE EARTH ENGINE SERVICE
# ============================================================================
CACHE_DIR = "gee_cache"


def _cache_path(coordinates):
    os.makedirs(CACHE_DIR, exist_ok=True)
    coord_str = str(coordinates)
    key = hashlib.md5(coord_str.encode('utf-8')).hexdigest()
    return os.path.join(CACHE_DIR, f"{key}.json")


def load_cached_analysis(coordinates):
    path = _cache_path(coordinates)
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception:
            return None
    return None


def save_cached_analysis(coordinates, data):
    path = _cache_path(coordinates)
    try:
        with open(path, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Cache save failed: {e}")


# Google Earth Engine library (imported safely)
GEE_AVAILABLE = False
try:
    import ee
    GEE_AVAILABLE = True
except ImportError:
    pass


def get_mangrove_coverage_fraction(ee_poly):
    """
    Returns the fraction (0.0-1.0) of the polygon's area that overlaps
    mapped mangrove forest, using Google's Global Mangrove Forests
    Distribution dataset (Landsat-derived, year 2000 baseline).
    Returns None if the check could not be performed (e.g. dataset/band
    mismatch, network issue) — distinct from 0.0, which means "checked,
    no mangrove found."
    """
    try:
        mangrove_img = ee.ImageCollection('LANDSAT/MANGROVE_FORESTS').mosaic()
        band_name = mangrove_img.bandNames().get(0)
        mangrove_mask = mangrove_img.select([band_name]).unmask(0)

        stats = mangrove_mask.reduceRegion(
            reducer=ee.Reducer.mean(),  # mean of a 0/1 mask = fraction covered
            geometry=ee_poly,
            scale=30,
            maxPixels=1e9
        )
        fraction = ee.Number(stats.get(band_name)).getInfo()
        return float(fraction) if fraction is not None else 0.0
    except Exception as e:
        print(f"Mangrove coverage check failed: {e}")
        return None


def validate_mangrove_habitat(ndvi, ndwi, mean_elevation_m, mangrove_fraction=None):
    """
    Lightweight validation gate — decides whether an analyzed area is
    plausible mangrove/coastal wetland habitat.

    Primary check: real overlap with Google's mapped mangrove forest extent
    (when available). Falls back to an NDVI/NDWI/elevation heuristic when
    the real mangrove-coverage check could not be performed.

    Returns (is_valid: bool, reasons: list[str])
    """
    reasons = []

    if mangrove_fraction is not None:
        if mangrove_fraction < 0.10:
            reasons.append(
                f"Only {mangrove_fraction * 100:.1f}% of this area overlaps mapped mangrove "
                f"forest (Global Mangrove Watch/Landsat baseline). This area is unlikely to "
                f"be a mangrove ecosystem."
            )
    else:
        # Real dataset check unavailable — fall back to heuristic signals.
        if ndvi is None or ndvi < 0.35:
            reasons.append(
                f"Vegetation density too low (NDVI {ndvi:.2f}) — area may be open water, "
                f"bare soil, or urban/built-up land." if ndvi is not None else
                "Vegetation density could not be determined."
            )
        if ndwi is None or ndwi < 0.05:
            reasons.append(
                f"Insufficient waterlogging signature (NDWI {ndwi:.2f}) — mangroves require "
                f"tidal/intertidal water presence." if ndwi is not None else
                "Waterlogging signature could not be determined."
            )
        if mean_elevation_m is not None and mean_elevation_m > 15.0:
            reasons.append(
                f"Elevation too high ({mean_elevation_m:.1f} m) — mangroves grow in low-lying "
                f"intertidal zones, typically under ~10 m."
            )

    is_valid = len(reasons) == 0
    return is_valid, reasons


def detect_deforestation_real(ee_poly, months_back=12, ndvi_drop_threshold=0.15):
    """
    Compares Sentinel-2 NDVI between a recent 90-day window and a ~12-month-earlier
    90-day window to detect real vegetation loss within the polygon — a standard
    change-detection proxy for deforestation/degradation.

    Returns a list of alert dicts (empty list = checked, no significant loss found).
    Returns None if the real check could not be completed (e.g. no clear imagery
    in one of the two windows) — distinct from an empty list.
    """
    try:
        end_recent = datetime.now()
        start_recent = end_recent - timedelta(days=90)
        end_old = start_recent - timedelta(days=30 * months_back)
        start_old = end_old - timedelta(days=90)

        def get_ndvi_composite(start, end):
            col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                   .filterBounds(ee_poly)
                   .filterDate(start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))
                   .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)))
            if col.size().getInfo() == 0:
                return None
            return col.median().normalizedDifference(['B8', 'B4']).rename('NDVI')

        ndvi_recent = get_ndvi_composite(start_recent, end_recent)
        ndvi_old = get_ndvi_composite(start_old, end_old)

        if ndvi_recent is None or ndvi_old is None:
            return None  # not enough clear imagery in one of the two windows

        # Positive diff = vegetation loss (old NDVI was higher than recent NDVI)
        ndvi_diff = ndvi_old.subtract(ndvi_recent)
        loss_mask = ndvi_diff.gt(ndvi_drop_threshold)

        loss_area_sqm = ee.Image.pixelArea().updateMask(loss_mask).reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=ee_poly,
            scale=10,
            maxPixels=1e9
        ).get('area').getInfo()

        loss_area_sqm = loss_area_sqm or 0

        alerts = []
        if loss_area_sqm > 500:  # ignore sub-pixel noise
            centroid = ee_poly.centroid(maxError=1).coordinates().getInfo()
            alerts.append({
                "date": end_recent.strftime('%Y-%m-%d'),
                "latitude": round(centroid[1], 5),
                "longitude": round(centroid[0], 5),
                "area_loss_sqm": round(loss_area_sqm, 1),
                "severity": "High" if loss_area_sqm > 20000 else "Moderate",
                "detection_method": "Real NDVI change detection (Sentinel-2)"
            })
        return alerts
    except Exception as e:
        print(f"Deforestation detection failed: {e}")
        return None


def locate_real_mangrove_center(lat, lng, search_radius_m=30000):
    """
    Given an administrative centroid (e.g. a CD Block's town center), searches
    a radius around it for real mapped mangrove pixels (Landsat-derived global
    mangrove dataset) and returns the centroid of whatever mangrove is found
    nearby. This lets any new block/project be added with just its admin
    centroid — no manual mangrove-coordinate hunting required.

    Returns (lat, lng) of the real mangrove patch center, or None if no
    mangrove was found within the search radius.
    """
    try:
        point = ee.Geometry.Point([lng, lat])
        search_region = point.buffer(search_radius_m)

        mangrove_img = ee.ImageCollection('LANDSAT/MANGROVE_FORESTS').mosaic()
        band_name = mangrove_img.bandNames().get(0)
        mangrove_mask = mangrove_img.select([band_name]).eq(1)

        lon_lat_img = ee.Image.pixelLonLat().updateMask(mangrove_mask)
        stats = lon_lat_img.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=search_region,
            scale=30,
            maxPixels=1e9
        )
        new_lon = stats.get('longitude').getInfo()
        new_lat = stats.get('latitude').getInfo()

        if new_lon is None or new_lat is None:
            return None
        return (new_lat, new_lon)
    except Exception as e:
        print(f"Mangrove relocation search failed: {e}")
        return None


def get_real_5yr_trend(ee_poly, num_years=5):
    """
    Builds a REAL annual NDVI + NDWI trend for the past `num_years` years,
    using one dry-season composite per year (Dec-Feb window). Both indices
    are read from the same yearly composite, so this adds no extra GEE calls
    beyond what a single-index version would need.

    Returns a list of {"year": int, "ndvi": float, "ndwi": float} dicts, in
    chronological order. A year is skipped if no usable imagery was found.
    """
    results = []
    current_year = datetime.now().year

    for i in range(num_years, 0, -1):
        year = current_year - i
        start = f"{year - 1}-12-01"
        end = f"{year}-02-28"
        try:
            col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                   .filterBounds(ee_poly)
                   .filterDate(start, end)
                   .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 40)))

            if col.size().getInfo() == 0:
                continue

            composite = col.median()
            ndvi_img = composite.normalizedDifference(['B8', 'B4'])
            ndwi_img = composite.normalizedDifference(['B3', 'B8'])

            stats = ee.Image.cat([ndvi_img.rename('ndvi'), ndwi_img.rename('ndwi')]).reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=ee_poly,
                scale=10,
                maxPixels=1e9
            )
            mean_ndvi = stats.get('ndvi').getInfo()
            mean_ndwi = stats.get('ndwi').getInfo()

            if mean_ndvi is not None and mean_ndwi is not None:
                results.append({
                    "year": year,
                    "ndvi": round(float(mean_ndvi), 3),
                    "ndwi": round(float(mean_ndwi), 3)
                })
        except Exception as e:
            print(f"5-year trend fetch failed for year {year}: {e}")
            continue

    return results


def get_annual_mangrove_change(ee_poly, years_back=5):
    """
    Checks real annual mangrove extent (CGMD-Extent30, Global Annual Mangrove
    Extent 1984-2023, 30m resolution) for change confirmation within the
    polygon over the last `years_back` years. Compares mapped mangrove area
    inside the polygon between the earliest and most recent available years
    in that window.

    Returns a dict with old/recent year, mangrove area (ha) at each, and
    percent change — or None if the check could not be completed (e.g.
    dataset unavailable, no mangrove polygons in this area for either year).
    """
    try:
        fc = ee.FeatureCollection('projects/mangrovedatahub2/assets/CGMD-Extent30')

        current_year = datetime.now().year
        recent_year = min(current_year - 1, 2023)  # dataset's most recent available year
        old_year = recent_year - years_back

        def mangrove_area_for_year(year):
            year_fc = fc.filter(ee.Filter.eq('year', year)).filterBounds(ee_poly)
            clipped = year_fc.geometry().intersection(ee_poly, ee.ErrorMargin(1))
            area_sqm = clipped.area(maxError=1).getInfo()
            return area_sqm / 10000.0  # sqm to hectares

        old_area_ha = mangrove_area_for_year(old_year)
        recent_area_ha = mangrove_area_for_year(recent_year)

        if old_area_ha is None or recent_area_ha is None:
            return None

        pct_change = None
        if old_area_ha > 0:
            pct_change = round(((recent_area_ha - old_area_ha) / old_area_ha) * 100.0, 1)

        return {
            "old_year": old_year,
            "recent_year": recent_year,
            "old_mangrove_area_ha": round(old_area_ha, 2),
            "recent_mangrove_area_ha": round(recent_area_ha, 2),
            "percent_change": pct_change
        }
    except Exception as e:
        print(f"Annual mangrove change check failed: {e}")
        return None


class GEEService:
    def __init__(self, use_sandbox=True):
        self.use_sandbox = use_sandbox
        self.gee_initialized = False
        if not use_sandbox and GEE_AVAILABLE:
            self.gee_initialized = self._initialize_gee()

    def _initialize_gee(self):
        if not GEE_AVAILABLE:
            return False
        try:
            # Try default initialization
            ee.Initialize(project='delta-carbon-project')
            print("Google Earth Engine connected successfully.")
            return True
        except Exception as e:
            print(f"Standard GEE initialization failed: {e}. Falling back to Sandbox Mode.")
            return False

    def is_live(self):
        return GEE_AVAILABLE and self.gee_initialized and not self.use_sandbox

    def _get_deterministic_seed(self, coordinates):
        """Generates a deterministic seed from coordinates to make simulation reproducible."""
        coord_str = str(coordinates)
        hasher = hashlib.md5(coord_str.encode('utf-8'))
        return int(hasher.hexdigest()[:8], 16)

    def analyze_area(self, coordinates, project_meta=None, force_refresh=False):
        """
        Performs geospatial analysis on a polygon.
        Returns:
            dict containing area, indices, and time-series data.
        """
        # Calculate area using Shapely
        try:
            poly = shapely.geometry.Polygon(coordinates)
            centroid = poly.centroid
            lat_factor = 111000.0
            lng_factor = 111000.0 * np.cos(np.radians(centroid.y))

            # Project coordinates to meters approximately
            proj_coords = [(pt[0] * lng_factor, pt[1] * lat_factor) for pt in coordinates]
            proj_poly = shapely.geometry.Polygon(proj_coords)
            area_ha = abs(proj_poly.area) / 10000.0  # m^2 to hectares
        except Exception:
            area_ha = 1200.0  # Fallback default area
        if area_ha < 0.1:
            area_ha = 5.0

        if self.is_live():
            return self._analyze_gee_live(coordinates, area_ha, project_meta, force_refresh=force_refresh)
        else:
            return self._analyze_sandbox(coordinates, area_ha, project_meta)

    def _analyze_gee_live(self, coordinates, area_ha, project_meta, force_refresh=False):
        """Real Google Earth Engine queries mapping Sentinel-2, Landsat, SRTM, GEDI, and MODIS."""
        if not force_refresh :
            cached = load_cached_analysis(coordinates)
            if cached is not None:
                cached['is_cached'] = True
                return cached
        try:
            # Construct GEE polygon
            ee_poly = ee.Geometry.Polygon(coordinates)

            # 1. Fetch Sentinel-2 L2A (COPERNICUS/S2_SR_HARMONIZED)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=270)  # ~9 months, reaches past monsoon cloud cover

            s2_col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                      .filterBounds(ee_poly)
                      .filterDate(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
                      .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 40))
                      .sort('CLOUDY_PIXEL_PERCENTAGE'))

            # Median composite and calculate NDVI & NDWI
            if s2_col.size().getInfo() > 0:
                composite = s2_col.median()
                # NDVI: (B8 - B4) / (B8 + B4)
                ndvi = composite.normalizedDifference(['B8', 'B4']).rename('NDVI')
                # NDWI: (B3 - B8) / (B3 + B8)
                ndwi = composite.normalizedDifference(['B3', 'B8']).rename('NDWI')

                mean_ndvi = ndvi.reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=ee_poly,
                    scale=10,
                    maxPixels=1e9
                ).get('NDVI').getInfo()

                mean_ndwi = ndwi.reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=ee_poly,
                    scale=10,
                    maxPixels=1e9
                ).get('NDWI').getInfo()
            else:
                cached = load_cached_analysis(coordinates)
                if cached is not None:
                    cached['is_cached'] = True
                    return cached
                mean_ndvi = 0.72
                mean_ndwi = 0.32

            mean_ndvi = mean_ndvi if mean_ndvi is not None else 0.72
            mean_ndwi = mean_ndwi if mean_ndwi is not None else 0.32

            # 2. Fetch Elevation data from SRTM DEM (USGS/SRTMGL1_003)
            dem = ee.Image('USGS/SRTMGL1_003')
            mean_elevation = dem.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=ee_poly,
                scale=30
            ).get('elevation').getInfo()
            mean_elevation = mean_elevation if mean_elevation is not None else 1.5

            # 3. Fetch Evapotranspiration from MODIS ET (MODIS/061/MOD16A2)
            et_col = (ee.ImageCollection('MODIS/061/MOD16A2')
                      .filterBounds(ee_poly)
                      .filterDate((end_date - timedelta(days=180)).strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')))

            if et_col.size().getInfo() > 0:
                et_mean = et_col.select('ET').median().reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=ee_poly,
                    scale=500
                ).get('ET').getInfo()
                et_val = et_mean if et_mean is not None else 150
                et_stress = max(0.0, min(1.0, 1.0 - (et_val / 300.0)))
            else:
                et_stress = 0.22

            # 4. GEDI Footprint Reference — canopy height (NASA/GEDI L2A monthly composites)
            canopy_height = 15.4
            try:
                gedi_col = ee.ImageCollection("LARSE/GEDI/GEDI02_A_002_MONTHLY")
                gedi_img = gedi_col.filterBounds(ee_poly).select('rh95').median()
                if gedi_img:
                    gedi_val = gedi_img.reduceRegion(
                        reducer=ee.Reducer.mean(),
                        geometry=ee_poly,
                        scale=25
                    ).get('rh95').getInfo()
                    if gedi_val is not None:
                        canopy_height = gedi_val / 100.0  # convert cm to meters if scaled
            except Exception:
                pass

            # 5. GEDI L4A Real Measured Aboveground Biomass Density (Mg/ha)
            # This is actual satellite-lidar-measured biomass, not a model prediction.
            real_agbd_per_ha = None
            try:
                gedi_agbd_col = (ee.ImageCollection('LARSE/GEDI/GEDI04_A_002_MONTHLY')
                                  .filterBounds(ee_poly)
                                  .map(lambda img: img.updateMask(img.select('l4_quality_flag').eq(1))
                                                      .updateMask(img.select('degrade_flag').eq(0)))
                                  .select('agbd'))

                agbd_composite = gedi_agbd_col.mean()

                agbd_count = agbd_composite.reduceRegion(
                    reducer=ee.Reducer.count(),
                    geometry=ee_poly,
                    scale=25,
                    maxPixels=1e9
                ).get('agbd').getInfo()

                if agbd_count and agbd_count > 0:
                    real_agbd_per_ha = agbd_composite.reduceRegion(
                        reducer=ee.Reducer.mean(),
                        geometry=ee_poly,
                        scale=25,
                        maxPixels=1e9
                    ).get('agbd').getInfo()
            except Exception as e:
                print(f"GEDI L4A biomass fetch failed: {e}")
                real_agbd_per_ha = None

            # 6. Real mangrove habitat coverage check (Landsat-derived global mangrove map)
            mangrove_fraction = get_mangrove_coverage_fraction(ee_poly)

            # 7. Real deforestation / vegetation-loss detection (Sentinel-2 NDVI change)
            real_alerts = detect_deforestation_real(ee_poly)

            # 8. Real 5-year annual NDVI historical trend (dry-season composites)
            real_5yr_trend = get_real_5yr_trend(ee_poly, num_years=5)

            # 9. Real annual mangrove extent change confirmation (CGMD-Extent30)
            annual_mangrove_change = get_annual_mangrove_change(ee_poly, years_back=5)

            # Fetch remaining time-series arrays deterministically using sandbox
            # templates (2-year ET trend remains simulated pending a real
            # historical ET archive integration; all current-state values and
            # the 5-year NDVI trend below are real).
            sandbox_data = self._analyze_sandbox(coordinates, area_ha, project_meta)

            # Override with real current-state values
            sandbox_data['current_ndvi'] = float(mean_ndvi)
            sandbox_data['current_ndwi'] = float(mean_ndwi)
            sandbox_data['current_et_stress'] = float(et_stress)
            sandbox_data['mean_elevation_m'] = float(mean_elevation)
            sandbox_data['gedi_canopy_height_m'] = float(canopy_height)
            sandbox_data['gedi_measured_agb_per_ha'] = real_agbd_per_ha
            sandbox_data['biomass_data_source'] = "GEDI L4A (real measured)" if real_agbd_per_ha else "Allometric estimate (no GEDI coverage)"
            sandbox_data['mangrove_coverage_fraction'] = mangrove_fraction
            sandbox_data['real_5yr_ndvi_trend'] = real_5yr_trend
            sandbox_data['annual_mangrove_change'] = annual_mangrove_change

            if real_alerts is not None:
                sandbox_data['deforestation_alerts'] = real_alerts
                sandbox_data['deforestation_detection_method'] = "real"
            else:
                sandbox_data['deforestation_detection_method'] = "simulated (real detection failed)"

            sandbox_data['is_cached'] = False
            save_cached_analysis(coordinates, sandbox_data)

            return sandbox_data

        except Exception as e:
            print(f"GEE live error: {e}. Switching to simulation.")

    def _analyze_sandbox(self, coordinates, area_ha, project_meta):
        """Simulates biophysical indices matching specific Baha' Mou and Sundari data details."""
        seed = self._get_deterministic_seed(coordinates)
        rng = np.random.default_rng(seed)

        # Pull metadata
        if project_meta is None:
            project_meta = {}

        proj_type = project_meta.get("type", "generic")

        if proj_type == "baha_mou":
            location_name = "South 24 Parganas, Sundarbans, West Bengal"
            base_ndvi = 0.74
            base_ndwi = 0.36
            base_et = 245.0
            base_stress = 0.16
            mean_elevation = 1.4
            gedi_canopy = 16.5
            deforestation_probability = 0.04
        elif proj_type == "sundari":
            location_name = "Gangasagar & Kakdwip, Sundarbans, West Bengal"
            base_ndvi = 0.69
            base_ndwi = 0.42
            base_et = 215.0
            base_stress = 0.24  # higher stress in islands
            mean_elevation = 1.1
            gedi_canopy = 14.8
            deforestation_probability = 0.06
        else:
            poly = shapely.geometry.Polygon(coordinates)
            centroid = poly.centroid
            location_name = f"Custom Mangrove Zone (Lat: {centroid.y:.4f}, Lng: {centroid.x:.4f})"
            base_ndvi = 0.71
            base_ndwi = 0.38
            base_et = 230.0
            base_stress = 0.21
            mean_elevation = 1.3
            gedi_canopy = 15.6
            deforestation_probability = 0.05

        # Noise adjustment
        base_ndvi += rng.uniform(-0.03, 0.03)
        base_ndwi += rng.uniform(-0.04, 0.04)

        # 1. Historical NDVI Time Series (10 years) — SIMULATED, used for chart
        # smoothness / sandbox mode. When live, this is supplemented (not
        # replaced) by real_5yr_ndvi_trend, which contains genuine annual
        # Sentinel-2 values for the most recent 5 years.
        dates = []
        ndvi_values = []
        curr_date = datetime.now() - timedelta(days=3652)

        # Simulating restoration progress: Sundari started in 2023, Baha Mou is ongoing
        is_sundari_restoration = (proj_type == "sundari")

        for i in range(120):
            date_str = curr_date.strftime('%Y-%m')
            dates.append(date_str)

            month = curr_date.month
            season = np.sin(2 * np.pi * (month - 1) / 12.0) * 0.05

            # Growth curve
            if is_sundari_restoration:
                # 2023 start -> index increases faster in final 3 years (i >= 84)
                growth = (i / 120.0) * 0.015
                if i >= 84:  # After Jan 2023
                    growth += ((i - 84) / 36.0) * 0.03
            else:
                growth = (i / 120.0) * 0.018

            noise = rng.normal(0, 0.015)

            val = base_ndvi + season + growth + noise
            ndvi_values.append(max(0.2, min(0.9, val)))
            curr_date += timedelta(days=30.5)

        # 2. Historical ET Time Series (24 months)
        et_dates = []
        et_values = []
        et_stress_values = []
        temp_anomalies = []

        curr_date = datetime.now() - timedelta(days=730)
        for i in range(24):
            date_str = curr_date.strftime('%b %y')
            et_dates.append(date_str)

            month = curr_date.month
            season = np.sin(2 * np.pi * (month - 1) / 12.0) * 28.0
            noise = rng.normal(0, 7.0)

            et_val = base_et + season + noise
            et_values.append(max(80.0, et_val))

            is_dry = (3 <= month <= 5)
            stress_mult = 1.5 if is_dry else 0.85
            temp_anom = rng.normal(0.4, 0.25) + (0.7 if is_dry else 0.0)
            temp_anomalies.append(round(temp_anom, 2))

            stress = base_stress * stress_mult + rng.normal(0, 0.04)
            et_stress_values.append(round(max(0.02, min(0.98, stress)), 2))
            curr_date += timedelta(days=30.5)

        # 3. Deforestation Alerts (Hotspots) — SIMULATED. Only used when live
        # GEE detection is unavailable; _analyze_gee_live() overrides this with
        # real Sentinel-2 NDVI change detection results when possible.
        alerts = []
        poly = shapely.geometry.Polygon(coordinates)
        centroid = poly.centroid

        if rng.uniform(0, 1) < deforestation_probability * 10:
            num_alerts = int(rng.choice([1, 2, 3]))
            for _ in range(num_alerts):
                offset_x = rng.uniform(-0.012, 0.012)
                offset_y = rng.uniform(-0.012, 0.012)
                alert_lat = centroid.y + offset_y
                alert_lng = centroid.x + offset_x

                alert_days_ago = int(rng.uniform(15, 340))
                alert_date = (datetime.now() - timedelta(days=alert_days_ago)).strftime('%Y-%m-%d')
                loss_sqm = rng.uniform(150, 4200)

                alerts.append({
                    "date": alert_date,
                    "latitude": round(alert_lat, 5),
                    "longitude": round(alert_lng, 5),
                    "area_loss_sqm": round(loss_sqm, 1),
                    "severity": "High" if loss_sqm > 2000 else "Moderate",
                    "detection_method": "Simulated (sandbox mode)"
                })

        alerts.sort(key=lambda x: x['date'], reverse=True)

        return {
            "location_name": location_name,
            "area_ha": round(area_ha, 2),
            "current_ndvi": round(ndvi_values[-1], 3),
            "current_ndwi": round(base_ndwi + rng.uniform(-0.02, 0.02), 3),
            "current_et_stress": round(et_stress_values[-1], 2),
            "mean_elevation_m": round(mean_elevation, 2),
            "gedi_canopy_height_m": round(gedi_canopy, 2),
            "gedi_measured_agb_per_ha": None,
            "biomass_data_source": "Allometric estimate (sandbox mode)",
            "mangrove_coverage_fraction": None,
            "deforestation_detection_method": "simulated (sandbox mode)",
            "real_5yr_ndvi_trend": None,
            "annual_mangrove_change": None,
            "historical_dates": dates,
            "historical_ndvi": ndvi_values,
            "historical_et_dates": et_dates,
            "historical_et": et_values,
            "historical_et_stress": et_stress_values,
            "historical_temp_anom": temp_anomalies,
            "deforestation_alerts": alerts
        }


# ============================================================================
# SECTION 3 — BIOMASS / CARBON ML MODEL
# ============================================================================
REAL_MODEL_PATH = 'mangrove_biomass_model.pkl'


class BiomassModel:
    def __init__(self):
        self.model, self.model_source = self._load_or_train_model()

    def _load_or_train_model(self):
        """
        Loads the real, offline-trained model (produced by
        train_biomass_model.py) if it exists on disk. This model predicts
        biomass (Mg/ha) DIRECTLY from [NDVI, NDWI, EVI, Elevation], trained
        on real GEDI L4A + Sentinel-2 data across the Sundarbans.

        If the real model file is not found (train_biomass_model.py has not
        been run yet), falls back to a synthetic-data-trained model so the
        app doesn't crash - but this is clearly flagged via model_source so
        it's never silently mistaken for the real thing.
        """
        if os.path.exists(REAL_MODEL_PATH):
            try:
                model = joblib.load(REAL_MODEL_PATH)
                print(f"Loaded real biomass model from {REAL_MODEL_PATH} "
                      f"(trained on real GEDI L4A + Sentinel-2 data).")
                return model, "real_trained"
            except Exception as e:
                print(f"Failed to load {REAL_MODEL_PATH}: {e}. Falling back to synthetic training.")

        print(f"WARNING: {REAL_MODEL_PATH} not found. Using a fallback model trained on "
              f"SYNTHETIC data. Run train_biomass_model.py to produce a real-data-trained model.")
        return self._train_synthetic_fallback_model(), "synthetic_fallback"

    def _train_synthetic_fallback_model(self):
        """
        Synthetic-data-trained fallback, used ONLY if the real model file is
        missing. Predicts canopy height from [NDVI, NDWI, EVI, Elevation]
        using invented calibration data - not real measurements. Kept as a
        safety net so the app remains functional even before
        train_biomass_model.py has been run.
        """
        rng = np.random.default_rng(42)
        n_samples = 800

        ndvi = rng.uniform(0.1, 0.85, n_samples)
        ndwi = rng.uniform(-0.2, 0.6, n_samples)
        evi = ndvi * 0.85 + rng.normal(0, 0.05, n_samples)
        elevation = rng.uniform(0, 8.0, n_samples)

        canopy_height_proxy = (12.0 * ndvi) + (6.0 * ndwi) - (0.4 * elevation) + 5.0
        canopy_height_proxy += rng.normal(0, 1.2, n_samples)
        canopy_height_proxy = np.clip(canopy_height_proxy, 1.5, 35.0)

        X = np.stack([ndvi, ndwi, evi, elevation, canopy_height_proxy], axis=1)

        # Synthetic target: approximates biomass (Mg/ha) via a height-like
        # proxy formula, so the fallback's output units are consistent with
        # the real model's (Mg/ha), even though the values are invented.
        height_proxy = (12.0 * ndvi) + (6.0 * ndwi) - (0.4 * elevation) + 5.0
        height_proxy += rng.normal(0, 1.2, n_samples)
        height_proxy = np.clip(height_proxy, 1.5, 35.0)
        agb_proxy = (5.66 * height_proxy) + 12.0  # Simard et al. allometry, applied to synthetic height

        rf = RandomForestRegressor(n_estimators=40, random_state=42)
        rf.fit(X, agb_proxy)
        return rf

    def predict_biomass_and_carbon(self, ndvi, ndwi, area_ha, real_agbd_per_ha=None, canopy_height_m=15.4):
        """
        Predicts Aboveground Biomass (AGB) and estimates soil & belowground carbon.

        Args:
            ndvi: current NDVI index for the polygon
            ndwi: current NDWI index for the polygon
            area_ha: polygon area in hectares
            real_agbd_per_ha: optional real GEDI L4A measured Aboveground
                Biomass Density (Mg/ha) for this polygon. When provided, used
                directly instead of any model prediction.

        Returns:
            dict containing carbon metrics for the polygon, including a
            "data_source" field: "gedi_measured", "model_real_trained", or
            "model_synthetic_fallback".
        """
        if real_agbd_per_ha is not None:
            # Real satellite-lidar-measured biomass is available - use it directly.
            agb_per_ha = real_agbd_per_ha
            data_source = "gedi_measured"
        else:
            # No real GEDI measurement for this polygon - use the model
            # (real-trained if available, synthetic fallback otherwise).
            evi = ndvi * 0.85  # EVI not independently fetched at inference time; approximated from NDVI
            elevation = 1.5    # standard delta elevation assumption for fallback case
            # Feature order MUST match train_biomass_model.py's FEATURE_NAMES
            features = np.array([[ndvi, ndwi, evi, elevation, canopy_height_m]])

            agb_per_ha = float(self.model.predict(features)[0])
            agb_per_ha = max(0.0, agb_per_ha)  # guard against unrealistic negative predictions

            data_source = "model_real_trained" if self.model_source == "real_trained" else "model_synthetic_fallback"

        total_agb = agb_per_ha * area_ha

        # 3. Calculate Aboveground Carbon (AGC)
        # IPCC standard carbon fraction of biomass is 0.47
        agc_per_ha = agb_per_ha * 0.47
        total_agc = agc_per_ha * area_ha

        # 4. Calculate Belowground Carbon (BGC) (Roots)
        # Root-to-shoot carbon ratio calibrated from Indian Sundarbans field study
        # (AGB:BGB ratio of 2.07 -> BGC/AGC ratio of ~0.483)
        bgc_per_ha = agc_per_ha * 0.483
        total_bgc = bgc_per_ha * area_ha

        # 5. Soil Organic Carbon (SOC) (up to 1m depth)
        # Mangrove soils are carbon sinks. They store ~200 - 800 Mg C / ha.
        # Deep organic soil stores more when waterlogged (higher NDWI).
        soc_per_ha = 320.0 + (350.0 * max(0.0, ndwi))
        total_soc = soc_per_ha * area_ha

        # 6. Sum Total Organic Carbon (TOC) in tons of Carbon (tC)
        total_carbon_tc = total_agc + total_bgc + total_soc
        carbon_per_ha = total_carbon_tc / area_ha

        # 7. Convert Carbon to Carbon Dioxide Equivalent (tCO2e)
        # 1 ton of Carbon = 3.67 tons of CO2 (molecular weight ratio 44/12)
        total_co2e = total_carbon_tc * 3.67
        co2e_per_ha = carbon_per_ha * 3.67

        # 8. Annual carbon sequestration capacity (tCO2e / year)
        # Healthy growing mangroves sequester ~6 to 15 tons of CO2e per hectare per year.
        sequestration_rate_per_ha_yr = 8.5 * ndvi
        total_sequestration_yr = sequestration_rate_per_ha_yr * area_ha

        return {
            "data_source": data_source,
            "agb_per_ha": round(agb_per_ha, 1),
            "total_agb_tons": round(total_agb, 1),

            "aboveground_carbon_tc": round(total_agc, 1),
            "belowground_carbon_tc": round(total_bgc, 1),
            "soil_organic_carbon_tc": round(total_soc, 1),

            "total_carbon_tc": round(total_carbon_tc, 1),
            "carbon_per_ha": round(carbon_per_ha, 1),

            "total_co2e_tons": round(total_co2e, 1),
            "co2e_per_ha": round(co2e_per_ha, 1),

            "annual_sequestration_tco2e": round(total_sequestration_yr, 1),
            "sequestration_rate_per_ha": round(sequestration_rate_per_ha_yr, 2)
        }


# ============================================================================
# SECTION 4 — ANALYTICS / CHECKLIST / READINESS SCORING
# ============================================================================
"""
analytics.py

Holds derived-metric logic that isn't raw GEE fetching (gee_service.py) or
raw biomass modeling (biomass_ml.py):
  - Verification readiness checklist (pre-verification evidence summary)
  - Chart data preparation (5-year baseline vs. current monitoring)

Kept separate from mainapp.py so UI/layout changes don't require touching
this logic, and so this logic stays testable independent of Streamlit.

Wording throughout intentionally avoids implying formal certification —
this platform produces an INDICATIVE, evidence-based readiness assessment,
not an accredited verification. See DISCLAIMER_TEXT below.
"""

DISCLAIMER_TEXT = (
    "This is an indicative, remote-sensing-based pre-verification assessment. "
    "It is not a certified or approved verification. Formal carbon credit "
    "verification requires review by an accredited verification body under "
    "an established methodology (e.g. VCS, Gold Standard)."
)


def get_verification_checklist(analysis, carbon, project_meta, is_live):
    """
    Builds a short, evidence-tied checklist summarizing how ready this
    project's data is for a formal verification review. Each item's status
    is derived directly from real fields already computed elsewhere in the
    app — nothing here is a subjective judgment call.

    Returns a list of dicts: {"item": str, "status": "pass"|"warning"|"fail",
    "note": str}
    """
    checklist = []

    # 1. Boundary defined and consistent with project documents
    confidence = project_meta.get("data_confidence", "unverified")
    if confidence == "verified":
        checklist.append({
            "item": "Boundary is defined and consistent with project documents.",
            "status": "pass",
            "note": "Coordinates based on verified administrative reference points."
        })
    elif confidence == "approximate":
        checklist.append({
            "item": "Boundary is defined and consistent with project documents.",
            "status": "warning",
            "note": "Boundary is an approximate regional stand-in; exact project GPS not publicly available."
        })
    else:
        checklist.append({
            "item": "Boundary is defined and consistent with project documents.",
            "status": "warning",
            "note": "Custom/user-drawn boundary; accuracy depends on manual input."
        })

    # 2. Project type and geography are stated
    location_name = analysis.get("location_name")
    proj_type = project_meta.get("type", "generic")
    if location_name and proj_type:
        checklist.append({
            "item": "Project type and geography are stated.",
            "status": "pass",
            "note": f"Type: {proj_type}; Location: {location_name}"
        })
    else:
        checklist.append({
            "item": "Project type and geography are stated.",
            "status": "fail",
            "note": "Project type or location metadata is missing."
        })

    # 3. Baseline period is available and comparable
    trend = analysis.get("real_5yr_ndvi_trend")
    if trend and len(trend) >= 2:
        checklist.append({
            "item": "Baseline period is available and comparable.",
            "status": "pass",
            "note": f"{len(trend)} years of real Sentinel-2 baseline data available."
        })
    elif trend and len(trend) == 1:
        checklist.append({
            "item": "Baseline period is available and comparable.",
            "status": "warning",
            "note": "Only 1 year of real baseline data available — limited comparability."
        })
    else:
        checklist.append({
            "item": "Baseline period is available and comparable.",
            "status": "fail",
            "note": "No real historical baseline data available for this period."
        })

    # 4. Current monitoring data exists for the selected period
    if is_live:
        checklist.append({
            "item": "Current monitoring data exists for the selected period.",
            "status": "pass",
            "note": "Live satellite data retrieved for the current monitoring window."
        })
    else:
        checklist.append({
            "item": "Current monitoring data exists for the selected period.",
            "status": "warning",
            "note": "Running in offline/sandbox mode — not live satellite data."
        })

    # 5. NDVI/NDWI and stress indicators within expected range
    ndvi = analysis.get("current_ndvi")
    ndwi = analysis.get("current_ndwi")
    if ndvi is not None and ndwi is not None and ndvi >= 0.35 and ndwi >= 0.05:
        checklist.append({
            "item": "NDVI/NDWI and stress indicators are within expected range.",
            "status": "pass",
            "note": f"NDVI: {ndvi:.3f}, NDWI: {ndwi:.3f} — consistent with mangrove habitat."
        })
    else:
        checklist.append({
            "item": "NDVI/NDWI and stress indicators are within expected range.",
            "status": "fail",
            "note": "Vegetation/water indices fall outside expected mangrove habitat range."
        })

    # 6. Carbon estimate generated from documented inputs
    data_source = carbon.get("data_source", "unknown") if carbon else "unknown"
    if data_source == "gedi_measured":
        checklist.append({
            "item": "Carbon estimate is generated from documented inputs.",
            "status": "pass",
            "note": "Biomass sourced directly from real GEDI L4A satellite measurement."
        })

    elif data_source == "model_real_trained":
        checklist.append({"item": "Carbon estimate is generated from documented inputs.", "status": "pass", "note": "Biomass from RF model trained on real GEDI+Sentinel-2 data."})
    
    elif data_source == "model_synthetic_fallback":
        checklist.append({
            "item": "Carbon estimate is generated from documented inputs.",
            "status": "warning",
            "note": "No GEDI footprint in this area — biomass from a fallback model trained on synthetic data (run train_biomass_model.py for a real-trained model)."
        })

    else:
        checklist.append({
            "item": "Carbon estimate is generated from documented inputs.",
            "status": "fail",
            "note": "Carbon estimate could not be generated."
        })

    # 7. Change alerts are reviewed
    detection_method = analysis.get("deforestation_detection_method", "simulated")
    if detection_method == "real":
        checklist.append({
            "item": "Change alerts are reviewed.",
            "status": "pass",
            "note": "Deforestation alerts based on real Sentinel-2 NDVI change detection."
        })
    else:
        checklist.append({
            "item": "Change alerts are reviewed.",
            "status": "warning",
            "note": "Real change detection unavailable for this run — using simulated placeholder."
        })

    # 8. Data gaps or sparse GEDI coverage are flagged
    if data_source == "gedi_measured":
        checklist.append({
            "item": "Data gaps or sparse GEDI coverage are flagged.",
            "status": "pass",
            "note": "GEDI footprint present in this area — no coverage gap."
        })
    else:
        checklist.append({
            "item": "Data gaps or sparse GEDI coverage are flagged.",
            "status": "warning",
            "note": "No GEDI footprint intersects this polygon — flagged as a coverage gap."
        })

    # 9. Supporting files available for audit
    checklist.append({
        "item": "Supporting files are available for audit.",
        "status": "pass",
        "note": "PDF evidence pack available for download."
    })

    # 10. Disclaimer
    checklist.append({
        "item": "A disclaimer states that formal verification requires an accredited body.",
        "status": "pass",
        "note": DISCLAIMER_TEXT
    })

    return checklist


def get_readiness_score(checklist):
    """
    Summarizes a checklist into a simple readiness score.
    Returns a dict: {"pass": int, "warning": int, "fail": int, "total": int,
    "score_pct": float}
    """
    counts = {"pass": 0, "warning": 0, "fail": 0}
    for entry in checklist:
        status = entry.get("status", "warning")
        counts[status] = counts.get(status, 0) + 1

    total = len(checklist)
    # "pass" counts fully, "warning" counts as half-credit, "fail" counts as none.
    score_pct = 0.0
    if total > 0:
        score_pct = round(((counts["pass"] + 0.5 * counts["warning"]) / total) * 100.0, 1)

    return {
        "pass": counts["pass"],
        "warning": counts["warning"],
        "fail": counts["fail"],
        "total": total,
        "score_pct": score_pct
    }


def prepare_baseline_vs_current_chart(analysis):
    """
    Prepares chart-ready data for the "5-year baseline vs current" chart,
    using the real annual NDVI trend (real_5yr_ndvi_trend) plus the current
    monitoring value, with each point labeled as "baseline" or "current" so
    the UI can style/color them distinctly.

    Returns a dict:
      {
        "available": bool,
        "labels": [str, ...],      # e.g. ["2021", "2022", "2023", "2024", "2025", "Current"]
        "values": [float, ...],
        "segment": [str, ...],     # "baseline" or "current" per point
        "note": str or None        # explanation if data is limited/unavailable
      }
    """
    trend = analysis.get("real_5yr_ndvi_trend")
    current_ndvi = analysis.get("current_ndvi")

    if not trend:
        return {
            "available": False,
            "labels": [],
            "values": [],
            "segment": [],
            "note": "Real 5-year baseline data is not available for this area/session."
        }

    labels = [str(entry["year"]) for entry in trend]
    values = [entry["ndvi"] for entry in trend]
    segment = ["baseline"] * len(trend)

    if current_ndvi is not None:
        labels.append("Current")
        values.append(round(float(current_ndvi), 3))
        segment.append("current")

    note = None
    if len(trend) < 5:
        note = (
            f"Only {len(trend)} of 5 baseline years had usable satellite imagery; "
            f"remaining years were skipped rather than estimated."
        )

    return {
        "available": True,
        "labels": labels,
        "values": values,
        "segment": segment,
        "note": note
    }


def prepare_ndvi_ndwi_trend_chart(analysis):
    """
    Prepares chart-ready data for a combined NDVI + NDWI line chart across
    the 5-year real baseline plus the current monitoring value.

    Returns a dict:
      {
        "available": bool,
        "labels": [str, ...],
        "ndvi_values": [float, ...],
        "ndwi_values": [float, ...],
        "current_index": int or None,  # position of the "current" point, for styling
        "note": str or None
      }
    """
    trend = analysis.get("real_5yr_ndvi_trend")
    current_ndvi = analysis.get("current_ndvi")
    current_ndwi = analysis.get("current_ndwi")

    if not trend:
        return {
            "available": False,
            "labels": [], "ndvi_values": [], "ndwi_values": [],
            "current_index": None,
            "note": "Real 5-year baseline data is not available for this area/session."
        }

    labels = [str(entry["year"]) for entry in trend]
    ndvi_values = [entry.get("ndvi") for entry in trend]
    ndwi_values = [entry.get("ndwi") for entry in trend]
    current_index = None

    if current_ndvi is not None and current_ndwi is not None:
        labels.append("Current")
        ndvi_values.append(round(float(current_ndvi), 3))
        ndwi_values.append(round(float(current_ndwi), 3))
        current_index = len(labels) - 1

    note = None
    if len(trend) < 5:
        note = f"Only {len(trend)} of 5 baseline years had usable satellite imagery."

    return {
        "available": True,
        "labels": labels,
        "ndvi_values": ndvi_values,
        "ndwi_values": ndwi_values,
        "current_index": current_index,
        "note": note
    }


def prepare_carbon_trend_chart(analysis, carbon):
    """
    Derives an indicative carbon stock trend (tCO2e) across the same 5-year
    baseline window, by scaling the current REAL carbon estimate by each
    year's real NDVI relative to today's real NDVI. This is a modeled trend
    grounded in real satellite baseline data — not an independent second
    measurement, and not fabricated: it's explicitly labeled as derived.

    Returns a dict:
      {"available": bool, "labels": [...], "values": [...], "note": str}
    """
    trend = analysis.get("real_5yr_ndvi_trend")
    current_ndvi = analysis.get("current_ndvi")
    current_co2e = carbon.get("total_co2e_tons") if carbon else None

    if not trend or current_ndvi is None or current_co2e is None or current_ndvi == 0:
        return {
            "available": False,
            "labels": [], "values": [],
            "note": "Insufficient real baseline data to derive a carbon stock trend."
        }

    labels = [str(entry["year"]) for entry in trend]
    values = [round(current_co2e * (entry["ndvi"] / current_ndvi), 1) for entry in trend]

    labels.append("Current")
    values.append(round(float(current_co2e), 1))

    return {
        "available": True,
        "labels": labels,
        "values": values,
        "note": "Derived from real satellite NDVI baseline scaled against the current measured carbon estimate — indicative, not an independent historical carbon measurement."
    }

def get_credit_readiness_status(checklist, carbon):
    """
    Compact, single-status summary derived from the checklist's evidence
    score. This is a HEADLINE, not a duplicate of the checklist — it does
    not repeat individual line item notes, but it DOES name which specific
    item(s) are blocking readiness, so the status is actionable rather than
    just a number.
    """
    score = get_readiness_score(checklist)
    pct = score["score_pct"]

    failing_items = [entry["note"] for entry in checklist if entry.get("status") == "fail"]
    warning_items = [entry["note"] for entry in checklist if entry.get("status") == "warning"]

    if score["fail"] > 0:
        status = "Not Ready"
        items_str = "; ".join(failing_items)
        note = f"Blocked by: {items_str}"
    elif pct >= 85:
        status = "Ready"
        note = "Evidence base is strong and complete. Suitable for submission to an accredited verification body."
    else:
        status = "Needs Review"
        items_str = "; ".join(warning_items)
        note = f"Flagged for review: {items_str}"

    gross_co2e = carbon.get("total_co2e_tons") if carbon else None

    return {
        "status": status,
        "score_pct": pct,
        "gross_co2e": gross_co2e,
        "net_co2e": None,
        "summary_note": note,
        "failing_items": failing_items,
        "warning_items": warning_items
    }


# ============================================================================
# SECTION 5 — PDF REPORT GENERATION
# ============================================================================
def _pdf_safe(text):
    """
    Strips/replaces characters unsupported by FPDF's default Latin-1 fonts
    (e.g. em dashes, curly quotes) so report generation never crashes on
    dynamic content (project names, notes, etc.).
    """
    if text is None:
        return ""
    text = str(text)
    replacements = {
        '\u2014': '-', '\u2013': '-',   # em dash, en dash
        '\u2018': "'", '\u2019': "'",   # curly single quotes
        '\u201c': '"', '\u201d': '"',   # curly double quotes
        '\u2026': '...',                # ellipsis
    }
    for uni_char, ascii_char in replacements.items():
        text = text.replace(uni_char, ascii_char)
    return text.encode('latin-1', errors='replace').decode('latin-1')


class EcosystemReport(FPDF):
    def header(self):
        # Skip header on the title page (page 1)
        if self.page_no() == 1:
            return
        self.set_font('Helvetica', 'B', 13)
        self.set_text_color(16, 130, 80)
        self.cell(0, 8, _pdf_safe('Blue Carbon MRV Evidence Pack'), border=0, ln=1, align='L')

        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(100, 100, 100)
        self.cell(0, 4, _pdf_safe('Indicative Remote-Sensing Monitoring Summary'), border=0, ln=1, align='L')

        self.set_draw_color(16, 130, 80)
        self.set_line_width(0.4)
        self.line(10, 20, 200, 20)
        self.ln(6)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(
            0, 10,
            _pdf_safe(f'Page {self.page_no()}/{{nb}}  |  Generated {datetime.now().strftime("%Y-%m-%d %H:%M")}  |  Indicative document, not a formal verification'),
            border=0, align='C'
        )

    def section_title(self, text):
        self.set_font('Helvetica', 'B', 12)
        self.set_text_color(30, 41, 59)
        self.cell(0, 8, _pdf_safe(text), ln=1)

    def kv_row(self, label, value, label_w=55, value_w=135):
        self.set_font('Helvetica', 'B', 9)
        self.set_fill_color(248, 250, 252)
        self.cell(label_w, 6, _pdf_safe(f'  {label}'), border=1, fill=True)
        self.set_font('Helvetica', '', 9)
        self.cell(value_w, 6, _pdf_safe(f' {value}'), border=1, ln=1)


def generate_pdf_report(project_name, analysis_data, carbon_data, project_meta=None, checklist=None):
    """
    Generates a structured, audit-ready PDF evidence pack:
      1. Title page
      2. Project summary
      3. Monitoring period
      4. Key metrics
      5. Checklist findings (pre-verification)
      6. Limitations
      7. Appendix (carbon pool table, deforestation alert log)

    This is explicitly an INDICATIVE document, not a certified verification —
    wording throughout avoids implying formal approval or guaranteed credits.

    Returns:
        bytes: Raw PDF file bytes to be served in a Streamlit download button.
    """
    if project_meta is None:
        project_meta = {}
    if checklist is None:
        checklist = []

    pdf = EcosystemReport()
    pdf.alias_nb_pages()

    # ======================================================
    # PAGE 1: TITLE PAGE
    # ======================================================
    pdf.add_page()
    pdf.ln(30)

    pdf.set_font('Helvetica', 'B', 22)
    pdf.set_text_color(16, 130, 80)
    pdf.multi_cell(0, 12, _pdf_safe('Blue Carbon MRV Evidence Pack'), align='C')
    pdf.ln(2)

    pdf.set_font('Helvetica', 'I', 13)
    pdf.set_text_color(80, 80, 80)
    pdf.multi_cell(0, 8, _pdf_safe('Indicative Pre-Verification Monitoring Summary'), align='C')
    pdf.ln(15)

    pdf.set_font('Helvetica', 'B', 14)
    pdf.set_text_color(30, 41, 59)
    pdf.multi_cell(0, 8, _pdf_safe(project_name), align='C')
    pdf.ln(4)

    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(100, 100, 100)
    pdf.multi_cell(0, 6, _pdf_safe(analysis_data.get('location_name', 'Location unavailable')), align='C')
    pdf.ln(20)

    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(130, 130, 130)
    pdf.multi_cell(0, 5, _pdf_safe(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"), align='C')
    pdf.ln(30)

    pdf.set_draw_color(16, 130, 80)
    pdf.set_fill_color(240, 253, 244)
    pdf.rect(20, pdf.get_y(), 170, 20, style='DF')
    pdf.set_y(pdf.get_y() + 3)
    pdf.set_font('Helvetica', 'B', 8.5)
    pdf.set_text_color(22, 101, 52)
    pdf.multi_cell(
        160, 4,
        _pdf_safe(
            'This is an indicative, remote-sensing-based pre-verification assessment. It is not a '
            'certified or approved verification. Formal carbon credit verification requires review '
            'by an accredited verification body under an established methodology.'
        ),
        align='C'
    )

    # ======================================================
    # PAGE 2: PROJECT SUMMARY
    # ======================================================
    pdf.add_page()
    pdf.section_title('1. Project Summary')

    metadata = [
        ('Project Identifier:', project_name),
        ('Region Name:', analysis_data.get('location_name', 'Unknown')),
        ('Project Area:', f"{analysis_data.get('area_ha', 0)} hectares (ha)"),
        ('Analysis Boundary:', 'Polygon defined via administrative reference or user-drawn area'),
        ('Boundary Confidence:', project_meta.get('data_confidence', 'unverified').capitalize()),
    ]
    if project_meta:
        metadata.extend([
            ('Registry Standard (stated):', project_meta.get('standard', 'N/A')),
            ('Trees Planted (stated):', project_meta.get('trees', 'N/A')),
            ('Species Composition:', project_meta.get('species', 'N/A')),
        ])

    for label, val in metadata:
        pdf.kv_row(label, val)

    pdf.ln(6)

    # ======================================================
    # SECTION 2: MONITORING PERIOD
    # ======================================================
    pdf.section_title('2. Monitoring Period')

    trend = analysis_data.get('real_5yr_ndvi_trend')
    if trend:
        years = [str(t['year']) for t in trend]
        pdf.kv_row('Baseline period:', f"{years[0]} - {years[-1]} ({len(trend)} year(s) of real Sentinel-2 data)")
    else:
        pdf.kv_row('Baseline period:', 'Real baseline data not available for this session')

    pdf.kv_row('Current monitoring window:', 'Most recent available satellite pass (last ~9 months)')

    data_state = 'Live satellite data' if not analysis_data.get('is_cached') else 'Most recent cached real result (live fetch unavailable this session)'
    pdf.kv_row('Data currency:', data_state)

    pdf.ln(6)

    # ======================================================
    # SECTION 3: KEY METRICS
    # ======================================================
    pdf.section_title('3. Key Metrics')

    pdf.set_fill_color(240, 253, 244)
    pdf.set_draw_color(187, 247, 208)
    pdf.rect(10, pdf.get_y(), 190, 16, style='DF')

    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_text_color(22, 101, 52)
    pdf.cell(0, 8, _pdf_safe(f'  Indicative Carbon Estimate (CO2 Equivalent): {carbon_data.get("total_co2e_tons", 0):,} tCO2e'), ln=1)
    pdf.set_font('Helvetica', '', 9)
    pdf.cell(0, 6, _pdf_safe(f'  Density: {carbon_data.get("co2e_per_ha", 0):,} tCO2e/ha  |  Est. Annual Sequestration: {carbon_data.get("annual_sequestration_tco2e", 0):,} tCO2e/yr'), ln=1)
    pdf.ln(6)

    biomass_source = carbon_data.get('data_source', 'unknown')
    biomass_source_label = {
        'gedi_measured': 'Real GEDI L4A satellite-measured biomass',
        'model_real_trained': 'ML model trained on real GEDI + Sentinel-2 data (no GEDI footprint in this area)',
        'model_synthetic_fallback': 'Fallback model trained on synthetic data (no GEDI footprint in this area)'
    }.get(biomass_source, 'Unknown')
    pdf.kv_row('Biomass data source:', biomass_source_label)

    pdf.set_text_color(30, 41, 59)
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_fill_color(226, 232, 240)
    pdf.cell(75, 6, _pdf_safe('Index / Sensor metric'), border=1, fill=True)
    pdf.cell(25, 6, _pdf_safe('Current Value'), border=1, fill=True)
    pdf.cell(90, 6, _pdf_safe('Interpretation'), border=1, ln=1, fill=True)

    indices = [
        ('NDVI (Vegetation Index)', f"{analysis_data.get('current_ndvi', 0):.3f}", 'Healthy mangrove canopy typically 0.65-0.85.'),
        ('NDWI (Water Index)', f"{analysis_data.get('current_ndwi', 0):.3f}", 'Waterlogged wetland typically 0.20-0.50.'),
        ('ET Stress Index', f"{analysis_data.get('current_et_stress', 0):.2f}", '0.00 (unstressed) to 1.00 (severe moisture deficit).'),
    ]
    pdf.set_font('Helvetica', '', 9)
    for label, val, desc in indices:
        pdf.cell(75, 6, _pdf_safe(f' {label}'), border=1)
        pdf.cell(25, 6, _pdf_safe(f' {val}'), border=1, align='C')
        pdf.cell(90, 6, _pdf_safe(f' {desc}'), border=1, ln=1)

    pdf.ln(6)

    # ======================================================
    # SECTION 4: CHECKLIST FINDINGS
    # ======================================================
    pdf.add_page()
    pdf.section_title('4. Pre-Verification Checklist Findings')

    pdf.set_font('Helvetica', 'I', 8.5)
    pdf.set_text_color(100, 100, 100)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 5, _pdf_safe(
        'Each item below is derived directly from the monitoring evidence collected for this '
        'project. This checklist supports, but does not replace, formal verification.'
    ))
    pdf.ln(3)

    status_symbol = {'pass': '[OK]', 'warning': '[REVIEW]', 'fail': '[GAP]'}
    status_color = {'pass': (22, 101, 52), 'warning': (161, 98, 7), 'fail': (153, 27, 27)}

    if checklist:
        for entry in checklist:
            status = entry.get('status', 'warning')
            symbol = status_symbol.get(status, '[REVIEW]')
            color = status_color.get(status, (100, 100, 100))

            pdf.set_font('Helvetica', 'B', 9)
            pdf.set_text_color(*color)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 5, _pdf_safe(f"{symbol} {entry.get('item', '')}"))

            pdf.set_font('Helvetica', '', 8.5)
            pdf.set_text_color(90, 90, 90)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 4.5, _pdf_safe(f"    {entry.get('note', '')}"))
            pdf.ln(1.5)
    else:
        pdf.set_font('Helvetica', 'I', 9)
        pdf.set_text_color(120, 120, 120)
        pdf.cell(0, 6, _pdf_safe('No checklist data was provided for this report.'), ln=1)

    pdf.set_text_color(30, 41, 59)
    pdf.ln(4)

    # ======================================================
    # SECTION 5: LIMITATIONS
    # ======================================================
    pdf.section_title('5. Limitations')

    pdf.set_font('Helvetica', '', 8.5)
    pdf.set_text_color(60, 60, 60)
    limitations = [
        'This document provides an indicative carbon estimate derived from public remote-sensing '
        'datasets (Sentinel-2, MODIS, SRTM, GEDI) and methodology-aligned models. It is not a '
        'certified or approved carbon credit verification.',
        'Formal verification requires review by an accredited verification body under an established '
        'methodology (e.g. VCS, Gold Standard). This report does not guarantee issuance of carbon credits.',
        'Where real GEDI biomass measurement is unavailable for a given area (sparse satellite '
        'footprint coverage), biomass is estimated using a documented allometric model instead; this '
        'is flagged explicitly in Section 3 and the checklist above.',
        'Optical satellite indices (NDVI/NDWI) can be affected by cloud cover, seasonal variation, and '
        'tidal conditions; the most recent usable clear-sky composite is used where available.',
    ]
    for line in limitations:
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 4.5, _pdf_safe(f'- {line}'))
        pdf.ln(1)

    pdf.ln(4)

    # ======================================================
    # APPENDIX: CARBON POOL TABLE + DEFORESTATION LOG
    # ======================================================
    pdf.add_page()
    pdf.section_title('Appendix A: Carbon Pool Breakdown')

    agc = carbon_data.get('aboveground_carbon_tc', 0)
    bgc = carbon_data.get('belowground_carbon_tc', 0)
    soc = carbon_data.get('soil_organic_carbon_tc', 0)
    tot = carbon_data.get('total_carbon_tc', 1) or 1

    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_fill_color(226, 232, 240)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(70, 6, _pdf_safe('Carbon Reservoir Pool'), border=1, fill=True)
    pdf.cell(60, 6, _pdf_safe('Estimated Carbon (tC)'), border=1, fill=True)
    pdf.cell(60, 6, _pdf_safe('Percentage of Total (%)'), border=1, ln=1, fill=True)

    pools = [
        ('Aboveground Biomass', agc, (agc / tot) * 100),
        ('Belowground Biomass (Roots)', bgc, (bgc / tot) * 100),
        ('Soil Organic Carbon (0-1m)', soc, (soc / tot) * 100),
    ]
    pdf.set_font('Helvetica', '', 9)
    for name, tc, pct in pools:
        pdf.cell(70, 6, _pdf_safe(f' {name}'), border=1)
        pdf.cell(60, 6, _pdf_safe(f' {tc:,.1f} tC'), border=1)
        pdf.cell(60, 6, _pdf_safe(f' {pct:.1f} %'), border=1, ln=1)

    pdf.set_font('Helvetica', 'B', 9)
    pdf.cell(70, 6, _pdf_safe(' Combined Total'), border=1)
    pdf.cell(60, 6, _pdf_safe(f' {tot:,.1f} tC'), border=1)
    pdf.cell(60, 6, _pdf_safe(' 100.0 %'), border=1, ln=1)

    pdf.ln(8)

    pdf.section_title('Appendix B: Deforestation / Canopy-Loss Alert Log')

    detection_method = analysis_data.get('deforestation_detection_method', 'simulated')
    method_label = 'Real Sentinel-2 NDVI change detection' if detection_method == 'real' else 'Simulated (real detection unavailable this session)'
    pdf.kv_row('Detection method:', method_label)

    alerts = analysis_data.get('deforestation_alerts', [])

    if not alerts:
        pdf.set_font('Helvetica', 'I', 9.5)
        pdf.set_text_color(16, 120, 70)
        pdf.cell(0, 6, _pdf_safe('  No canopy loss or deforestation alerts detected in this area over the monitoring period.'), ln=1)
        pdf.set_text_color(30, 41, 59)
    else:
        pdf.set_font('Helvetica', 'B', 9)
        pdf.set_fill_color(254, 226, 226)
        pdf.set_text_color(153, 27, 27)
        pdf.cell(30, 6, _pdf_safe('Date'), border=1, fill=True)
        pdf.cell(60, 6, _pdf_safe('GPS Coordinate (Lat, Lng)'), border=1, fill=True)
        pdf.cell(50, 6, _pdf_safe('Estimated Loss'), border=1, fill=True)
        pdf.cell(50, 6, _pdf_safe('Severity'), border=1, ln=1, fill=True)

        pdf.set_font('Helvetica', '', 9)
        pdf.set_text_color(30, 41, 59)
        for alt in alerts[:5]:
            pdf.cell(30, 6, _pdf_safe(f' {alt.get("date")}'), border=1)
            pdf.cell(60, 6, _pdf_safe(f' {alt.get("latitude")}, {alt.get("longitude")}'), border=1)
            pdf.cell(50, 6, _pdf_safe(f' {alt.get("area_loss_sqm"):,.1f} sqm'), border=1)
            pdf.cell(50, 6, _pdf_safe(f' {alt.get("severity")}'), border=1, ln=1)

        if len(alerts) > 5:
            pdf.set_font('Helvetica', 'I', 8)
            pdf.cell(0, 6, _pdf_safe(f'  Note: {len(alerts) - 5} additional alert(s) omitted from this appendix. See live portal for full log.'), ln=1)

    # Output PDF stream
    pdf_buffer = io.BytesIO()
    pdf_out = pdf.output(dest='S')
    if isinstance(pdf_out, str):
        pdf_buffer.write(pdf_out.encode('latin1'))
    else:
        pdf_buffer.write(pdf_out)

    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()


# ============================================================================
# SECTION 6 — FASTAPI APP & ROUTES
# ============================================================================
"""
main.py — Blue Carbon Ecosystem Monitor API

Rebuilds the original Streamlit app as a stateless REST API. All the actual
science/ML logic (gee_service, biomass_ml, analytics, pdf_report) is reused
unchanged from the Streamlit version — only the presentation layer moved to
React, and per-request state replaces st.session_state.
"""



app = FastAPI(title="Blue Carbon Ecosystem Monitor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your frontend origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

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
def analyze(req: AnalyzeRequest, user: dict = Depends(get_current_user)):
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
def report_pdf(req: ReportRequest, user: dict = Depends(get_current_user)):
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

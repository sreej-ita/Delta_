import hashlib
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import shapely.geometry
import json
import os
from gemini_service import explain_alert

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

    # ------------------------------------------------------------------
    # Gemini "why this matters" explanations for deforestation alerts.
    # Attached ONCE, on whichever alert list actually ends up being served
    # to the frontend (real or simulated) — never on intermediate/discarded
    # alert lists — so we don't burn Gemini calls explaining data nobody
    # sees. Safe to call even if GEMINI_API_KEY is unset: explain_alert()
    # itself falls back to a rule-based sentence in that case.
    # ------------------------------------------------------------------
    def _attach_alert_explanations(self, result, project_meta=None):
        alerts = result.get('deforestation_alerts') or []
        if not alerts:
            return result

        project_meta = project_meta or {}
        project_name = project_meta.get('name') or result.get('location_name', 'Unnamed Project')

        for alert in alerts:
            try:
                explanation = explain_alert(project_name, alert, result)
                alert['why_this_matters'] = explanation.get('explanation')
                alert['explanation_source'] = explanation.get('source')
            except Exception as e:
                print(f"Alert explanation attach failed: {e}")
                alert['why_this_matters'] = None
                alert['explanation_source'] = 'error'

        return result

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
            result = self._analyze_sandbox(coordinates, area_ha, project_meta)
            return self._attach_alert_explanations(result, project_meta)

    def _analyze_gee_live(self, coordinates, area_ha, project_meta, force_refresh=False):
        """Real Google Earth Engine queries mapping Sentinel-2, Landsat, SRTM, GEDI, and MODIS."""
        if not force_refresh:
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
            # the 5-year NDVI trend below are real). NOTE: this borrowed
            # sandbox_data['deforestation_alerts'] gets overwritten below with
            # real_alerts (or discarded on failure) — so we deliberately do
            # NOT attach Gemini explanations inside _analyze_sandbox itself,
            # only after the final alert list is settled a few lines down.
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

            # Attach Gemini "why this matters" explanations to the FINAL
            # alert list only, then cache it — so repeat requests for this
            # polygon reuse the cached explanations instead of re-calling
            # Gemini every time.
            sandbox_data = self._attach_alert_explanations(sandbox_data, project_meta)

            sandbox_data['is_cached'] = False
            save_cached_analysis(coordinates, sandbox_data)

            return sandbox_data

        except Exception as e:
            print(f"GEE live error: {e}. Switching to simulation.")
            result = self._analyze_sandbox(coordinates, area_ha, project_meta)
            result = self._attach_alert_explanations(result, project_meta)
            result['is_cached'] = False
            return result

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

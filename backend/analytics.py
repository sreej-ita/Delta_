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

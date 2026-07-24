import os
import numpy as np
import joblib
from sklearn.ensemble import RandomForestRegressor

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
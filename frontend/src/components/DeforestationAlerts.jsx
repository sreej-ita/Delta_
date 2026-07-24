import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import { ShieldCheck, ShieldAlert } from "lucide-react";

const SEVERITY_COLOR = { High: "#f43f5e", Moderate: "#f59e0b" };

function AlertsMap({ alerts }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);

  useEffect(() => {
    if (!alerts.length) return;
    const lats = alerts.map((a) => a.latitude);
    const lngs = alerts.map((a) => a.longitude);
    const center = [lngs.reduce((a, b) => a + b, 0) / lngs.length, lats.reduce((a, b) => a + b, 0) / lats.length];

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          satellite: {
            type: "raster",
            tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
            tileSize: 256,
          },
        },
        layers: [{ id: "satellite", type: "raster", source: "satellite" }],
      },
      center,
      zoom: 11,
    });
    mapRef.current = map;

    map.on("load", () => {
      alerts.forEach((alt) => {
        const el = document.createElement("div");
        el.style.width = "16px";
        el.style.height = "16px";
        el.style.borderRadius = "50%";
        el.style.background = SEVERITY_COLOR[alt.severity] || "#94a3b8";
        el.style.boxShadow = `0 0 12px ${SEVERITY_COLOR[alt.severity] || "#94a3b8"}`;
        el.style.border = "2px solid white";

        new maplibregl.Marker({ element: el })
          .setLngLat([alt.longitude, alt.latitude])
          .setPopup(
            new maplibregl.Popup({ offset: 14 }).setHTML(
              `<strong>${alt.severity} severity</strong><br/>${alt.area_loss_sqm.toFixed(1)} sqm · ${alt.date}`
            )
          )
          .addTo(map);
      });
    });

    return () => map.remove();
  }, [alerts]);

  return <div ref={containerRef} className="h-[350px] w-full rounded-xl border border-black/10" />;
}

export default function DeforestationAlerts({ analysis }) {
  const method = analysis.deforestation_detection_method || "simulated";
  const alerts = analysis.deforestation_alerts || [];

  return (
    <div>
      <p className="mb-4 text-xs text-muted">
        {method === "real"
          ? "🛰️ Detection method: Real Sentinel-2 NDVI change analysis"
          : "⚠️ Detection method: Simulated (live detection unavailable for this run)"}
      </p>

      {alerts.length === 0 ? (
        <div className="flex items-center gap-3 rounded-lg border border-emerald/25 bg-emerald/10 px-4 py-3 text-sm text-emerald">
          <ShieldCheck size={18} />
          No canopy degradation or deforestation hotspots detected within the boundaries in the last 365 days.
        </div>
      ) : (
        <>
          <div className="mb-4 flex items-center gap-3 rounded-lg border border-amber/25 bg-amber/10 px-4 py-3 text-sm text-amber">
            <ShieldAlert size={18} />
            Detected {alerts.length} canopy loss/deforestation hotspots in the last 365 days.
          </div>

          <AlertsMap alerts={alerts} />

          <div className="mt-5 space-y-3">
            {alerts.map((alt, i) => (
              <div key={i} className="rounded-lg border border-rose/25 bg-rose/10 px-5 py-3">
                <span
                  className="rounded px-2 py-0.5 text-xs font-bold uppercase text-white"
                  style={{ backgroundColor: SEVERITY_COLOR[alt.severity] || "#94a3b8" }}
                >
                  {alt.severity} severity
                </span>
                <span className="ml-3 text-sm text-muted">
                  Detected: <span className="text-ink">{alt.date}</span>
                </span>
                <p className="mt-2 text-sm text-ink">
                  <strong>Location:</strong> {alt.latitude}, {alt.longitude}
                </p>
                <p className="text-sm text-ink">
                  <strong>Ecosystem footprint loss:</strong> {alt.area_loss_sqm} sqm of canopy cover cleared.
                </p>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
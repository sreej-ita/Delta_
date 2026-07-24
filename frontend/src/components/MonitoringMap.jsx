import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import { Pencil } from "lucide-react";

/**
 * Flat satellite monitoring map (Esri World Imagery), matching the same
 * approach used in DeforestationAlerts.jsx. The project boundary is drawn as
 * a highlighted outline + fill, and users can still draw a custom polygon to
 * monitor a new area.
 */
export default function MonitoringMap({ coords, projectName, onDrawPolygon }) {
  const mapContainer = useRef(null);
  const mapRef = useRef(null);
  const [drawing, setDrawing] = useState(false);
  const [drawPoints, setDrawPoints] = useState([]);
  const drawSourceId = "draw-in-progress";

  const style = {
    version: 8,
    sources: {
      satellite: {
        type: "raster",
        tiles: [
          "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        ],
        tileSize: 256,
        attribution: "Esri World Imagery",
      },
    },
    layers: [{ id: "satellite", type: "raster", source: "satellite" }],
  };

  useEffect(() => {
    if (!coords || coords.length === 0) return;

    const lats = coords.map((c) => c[1]);
    const lngs = coords.map((c) => c[0]);
    const centerLat = lats.reduce((a, b) => a + b, 0) / lats.length;
    const centerLng = lngs.reduce((a, b) => a + b, 0) / lngs.length;

    if (!mapRef.current) {
      const map = new maplibregl.Map({
        container: mapContainer.current,
        style,
        center: [centerLng, centerLat],
        zoom: 12,
      });
      map.addControl(new maplibregl.NavigationControl(), "top-right");
      map.on("load", () => addBoundaryLayer(map, coords, projectName));
      mapRef.current = map;
    } else {
      mapRef.current.flyTo({ center: [centerLng, centerLat], zoom: 12, duration: 1000 });
      updateBoundaryLayer(mapRef.current, coords, projectName);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [coords]);

  function addBoundaryLayer(map, polyCoords, name) {
    const geojson = boundaryGeoJson(polyCoords, name);

    if (!map.getSource("boundary")) {
      map.addSource("boundary", { type: "geojson", data: geojson });

      map.addLayer({
        id: "boundary-fill",
        type: "fill",
        source: "boundary",
        paint: { "fill-color": "#10b981", "fill-opacity": 0.18 },
      });

      map.addLayer({
        id: "boundary-outline",
        type: "line",
        source: "boundary",
        paint: { "line-color": "#10b981", "line-width": 2.5 },
      });

      const popup = new maplibregl.Popup({ closeButton: false, offset: 12 });
      map.on("mousemove", "boundary-fill", (e) => {
        map.getCanvas().style.cursor = "pointer";
        popup.setLngLat(e.lngLat).setHTML(`<strong>${name}</strong>`).addTo(map);
      });
      map.on("mouseleave", "boundary-fill", () => {
        map.getCanvas().style.cursor = "";
        popup.remove();
      });
    } else {
      map.getSource("boundary").setData(geojson);
    }
  }

  function updateBoundaryLayer(map, polyCoords, name) {
    const src = map.getSource("boundary");
    if (src) src.setData(boundaryGeoJson(polyCoords, name));
  }

  function boundaryGeoJson(polyCoords, name) {
    return {
      type: "Feature",
      geometry: { type: "Polygon", coordinates: [polyCoords] },
      properties: { name },
    };
  }

  // ---- Free-draw custom polygon mode ----
  function toggleDraw() {
    const map = mapRef.current;
    if (!map) return;

    if (!drawing) {
      setDrawing(true);
      setDrawPoints([]);
      map.getCanvas().style.cursor = "crosshair";
    } else {
      finishDrawing();
    }
  }

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !drawing) return;

    function handleClick(e) {
      setDrawPoints((prev) => {
        const next = [...prev, [e.lngLat.lng, e.lngLat.lat]];
        renderDraftPolygon(map, next);
        return next;
      });
    }
    map.on("click", handleClick);
    return () => map.off("click", handleClick);
  }, [drawing]);

  function renderDraftPolygon(map, points) {
    const data = {
      type: "Feature",
      geometry: { type: "LineString", coordinates: points },
      properties: {},
    };
    if (!map.getSource(drawSourceId)) {
      map.addSource(drawSourceId, { type: "geojson", data });
      map.addLayer({
        id: drawSourceId,
        type: "line",
        source: drawSourceId,
        paint: { "line-color": "#f59e0b", "line-width": 2, "line-dasharray": [2, 1] },
      });
    } else {
      map.getSource(drawSourceId).setData(data);
    }
  }

  function finishDrawing() {
    const map = mapRef.current;
    setDrawing(false);
    if (map) map.getCanvas().style.cursor = "";
    if (drawPoints.length >= 3) {
      const closed = [...drawPoints, drawPoints[0]].map(([lng, lat]) => [
        Math.round(lng * 1e5) / 1e5,
        Math.round(lat * 1e5) / 1e5,
      ]);
      onDrawPolygon?.(closed);
    }
    if (map?.getLayer(drawSourceId)) {
      map.removeLayer(drawSourceId);
      map.removeSource(drawSourceId);
    }
    setDrawPoints([]);
  }

  return (
    <div className="relative h-[520px] w-full overflow-hidden rounded-xl border border-black/10">
      <div ref={mapContainer} className="h-full w-full" />

      <div className="absolute left-3 top-3 flex flex-col gap-2">
        <button
          onClick={toggleDraw}
          className={
            "flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium shadow-lg backdrop-blur transition-colors " +
            (drawing
              ? "border-amber bg-amber/20 text-amber"
              : "border-white/10 bg-black/50 text-ink hover:border-emerald")
          }
        >
          <Pencil size={14} />
          {drawing ? `Drawing (${drawPoints.length} pts) — click to finish` : "Draw custom boundary"}
        </button>
      </div>
    </div>
  );
}
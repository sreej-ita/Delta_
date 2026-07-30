import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";


/**
 * Flat satellite monitoring map (Esri World Imagery + place-name labels).
 * The project boundary is drawn as a highlighted outline + fill on top of
 * the satellite imagery.
 */
export default function MonitoringMap({ coords, projectName }) {
  const mapContainer = useRef(null);
  const mapRef = useRef(null);

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
      // Transparent overlay tiles: place names, roads, borders — rendered on
      // top of the satellite photo so the map reads like a real map.
      labels: {
        type: "raster",
        tiles: [
          "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
        ],
        tileSize: 256,
        attribution: "Esri World Boundaries and Places",
      },
    },
    layers: [
      { id: "satellite", type: "raster", source: "satellite" },
      { id: "labels", type: "raster", source: "labels" },
    ],
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

  return (
    <div className="relative h-[520px] w-full overflow-hidden rounded-xl border border-black/10">
      <div ref={mapContainer} className="h-full w-full" />
    </div>
  );
}

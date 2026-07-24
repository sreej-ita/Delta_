import { useEffect, useState, useCallback } from "react";
import { Map, BarChart3, Activity, ShieldAlert, FileText, LogOut } from "lucide-react";
import { useAuth } from "../lib/auth.jsx";
import { api } from "../lib/api.js";
import Sidebar from "../components/Sidebar.jsx";
import MonitoringMap from "../components/MonitoringMap.jsx";
import CarbonAnalytics from "../components/CarbonAnalytics.jsx";
import VegetationHealth from "../components/VegetationHealth.jsx";
import DeforestationAlerts from "../components/DeforestationAlerts.jsx";
import EcosystemReport from "../components/EcosystemReport.jsx";
import { InfoBox } from "../components/Shared.jsx";

const TABS = [
  { id: "map", label: "Interactive Monitoring Map", icon: Map },
  { id: "carbon", label: "Biomass & Carbon Analytics", icon: BarChart3 },
  { id: "health", label: "Vegetation Stress & Health", icon: Activity },
  { id: "alerts", label: "Deforestation Alerts", icon: ShieldAlert },
  { id: "report", label: "Ecosystem Summary Report", icon: FileText },
];

export default function Dashboard() {
  const { user, logout } = useAuth();
  const [sites, setSites] = useState([]);
  const [siteId, setSiteId] = useState("baha_mou");
  const [blockName, setBlockName] = useState("Sagar");
  const [useSandbox, setUseSandbox] = useState(false);
  const [customCoords, setCustomCoords] = useState(null);

  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState("map");

  useEffect(() => {
    api.listSites().then(setSites).catch(() => {});
  }, []);

  const runAnalysis = useCallback(
    async (forceRefresh = false) => {
      forceRefresh ? setRefreshing(true) : setLoading(true);
      setError("");
      try {
        const payload = {
          site_id: siteId,
          block_name: siteId === "sundari" ? blockName : undefined,
          custom_coords: siteId === "custom" ? customCoords : undefined,
          use_sandbox: useSandbox,
          force_refresh: forceRefresh,
        };
        const data = await api.analyze(payload);
        setResult(data);
      } catch (err) {
        setError(err.message || "Failed to run analysis.");
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [siteId, blockName, customCoords, useSandbox]
  );

  useEffect(() => {
    if (siteId === "custom" && !customCoords) return; // wait for a drawn polygon
    runAnalysis(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteId, blockName, useSandbox, customCoords]);

  function handleDrawPolygon(coords) {
    setCustomCoords(coords);
    setSiteId("custom");
  }

  return (
    <div className="min-h-screen px-4 py-6 sm:px-8">
      <header className="mx-auto mb-6 flex max-w-7xl items-center justify-between">
        <div>
          <h1 className="title-gradient font-display text-3xl font-bold sm:text-4xl">
            Blue Carbon Ecosystem Monitor
          </h1>
          <p className="text-sm text-muted">
            Continuous biophysical tracking & carbon density estimation using remote sensing
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="hidden text-sm text-muted sm:inline">{user?.name}</span>
          <button
            onClick={logout}
            className="flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-2 text-xs text-ink hover:border-rose hover:text-rose"
          >
            <LogOut size={14} /> Sign out
          </button>
        </div>
      </header>

      <div className="mx-auto flex max-w-7xl flex-col gap-6 lg:flex-row">
        <Sidebar
          sites={sites}
          siteId={siteId}
          setSiteId={setSiteId}
          blockName={blockName}
          setBlockName={setBlockName}
          useSandbox={useSandbox}
          setUseSandbox={setUseSandbox}
          isLive={result?.is_live}
          projectMeta={result?.project_meta}
          onRefresh={() => runAnalysis(true)}
          refreshing={refreshing}
        />

        <main className="flex-1">
          {error && (
            <div className="glass-card mb-4 border-rose/30 px-5 py-4 text-sm text-rose">{error}</div>
          )}

          {loading ? (
            <div className="glass-card flex h-96 items-center justify-center text-sm text-muted">
              Compiling Earth Engine collections and running models...
            </div>
          ) : result && !result.habitat_valid ? (
            <div className="glass-card px-6 py-8">
              <p className="mb-2 text-sm font-semibold text-rose">
                🚫 This area does not appear to be viable mangrove/coastal wetland habitat, so carbon
                estimates cannot be reliably generated.
              </p>
              <ul className="mb-3 list-disc pl-5 text-sm text-muted">
                {result.habitat_reasons.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
              <InfoBox>
                Try selecting one of the preset projects/blocks, or draw a polygon over a known coastal
                mangrove/wetland zone.
              </InfoBox>
            </div>
          ) : result ? (
            <>
              <div className="glass-card mb-4 flex gap-1.5 overflow-x-auto p-1.5">
                {TABS.map((tab) => {
                  const Icon = tab.icon;
                  const active = activeTab === tab.id;
                  return (
                    <button
                      key={tab.id}
                      onClick={() => setActiveTab(tab.id)}
                      className={`flex shrink-0 items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors ${
                        active ? "bg-emerald/15 text-emerald" : "text-muted hover:text-ink"
                      }`}
                    >
                      <Icon size={15} />
                      {tab.label}
                    </button>
                  );
                })}
              </div>

              <div className="glass-card p-5 sm:p-6">
                {result.analysis.is_cached && (
                  <p className="mb-3 text-xs text-muted">
                    ℹ️ Showing the most recently available real satellite analysis for this area (cached
                    result).
                  </p>
                )}

                {activeTab === "map" && (
                  <>
                    <InfoBox>
                      Select a preset site from the sidebar, or draw a custom boundary directly on the map
                      below to monitor a new mangrove zone.
                    </InfoBox>
                    <MonitoringMap
                      coords={result.coords}
                      projectName={result.project_name}
                      onDrawPolygon={handleDrawPolygon}
                    />
                  </>
                )}

                {activeTab === "carbon" && (
                  <CarbonAnalytics
                    analysis={result.analysis}
                    carbon={result.carbon}
                    ndviTrend={result.ndvi_ndwi_trend}
                    carbonTrend={result.carbon_trend}
                  />
                )}

                {activeTab === "health" && <VegetationHealth analysis={result.analysis} />}

                {activeTab === "alerts" && <DeforestationAlerts analysis={result.analysis} />}

                {activeTab === "report" && (
                  <EcosystemReport
                    projectName={result.project_name}
                    analysis={result.analysis}
                    carbon={result.carbon}
                    projectMeta={result.project_meta}
                    checklist={result.checklist}
                    readiness={result.readiness}
                  />
                )}
              </div>
            </>
          ) : null}
        </main>
      </div>
    </div>
  );
}

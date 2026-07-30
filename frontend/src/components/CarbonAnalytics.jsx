import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, AreaChart, Area, PieChart, Pie, Cell,
} from "recharts";
import { MetricCard, SectionTitle } from "./Shared.jsx";
const PIE_COLORS = ["#10b981", "#3b82f6", "#8b5cf6"];

export default function CarbonAnalytics({ analysis, carbon, ndviTrend, carbonTrend }) {
  const dataSourceLabel = {
    gedi_measured: "Real GEDI L4A measured data",
    model_real_trained: "ML model (trained on real GEDI + Sentinel-2 data) — no GEDI footprint here",
    model_synthetic_fallback: "Fallback model (synthetic training data)",
  }[carbon.data_source] || "Unknown";

  const pieData = [
    { name: "Aboveground Carbon", value: carbon.aboveground_carbon_tc },
    { name: "Belowground Carbon", value: carbon.belowground_carbon_tc },
    { name: "Soil Organic Carbon", value: carbon.soil_organic_carbon_tc },
  ];

  const trendData =
    ndviTrend?.available &&
    ndviTrend.labels.map((label, i) => ({
      year: label,
      ndvi: ndviTrend.ndvi_values[i],
      ndwi: ndviTrend.ndwi_values[i],
    }));

  const carbonTrendData =
    carbonTrend?.available &&
    carbonTrend.labels.map((label, i) => ({ year: label, value: carbonTrend.values[i] }));

  return (
    <div>
      <p className="mb-4 text-xs text-muted">
        Biomass source: <span className="text-ink">{dataSourceLabel}</span>
      </p>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <MetricCard label="Total Area Monitored" value={`${analysis.area_ha.toLocaleString()} ha`} accent="emerald" />
        <MetricCard label="Estimated Total Carbon" value={`${carbon.total_carbon_tc.toLocaleString()} tC`} accent="blue" />
        <MetricCard label="CO₂ Equivalent" value={`${carbon.total_co2e_tons.toLocaleString()} tCO₂e`} accent="violet" />
        <MetricCard label="Annual Sequestration" value={`${carbon.annual_sequestration_tco2e.toLocaleString()} tCO₂/yr`} accent="emerald" />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="glass-card p-5 lg:col-span-2">
          <SectionTitle>5-Year Baseline vs. Current (NDVI & NDWI)</SectionTitle>
          {trendData ? (
            <>
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={trendData}>
                  <CartesianGrid stroke="rgba(0,0,0,0.06)" />
                  <XAxis dataKey="year" stroke="#94a3b8" fontSize={12} />
                  <YAxis stroke="#94a3b8" fontSize={12} />
                  <Tooltip contentStyle={{ background: "#ffffff", border: "1px solid rgba(0,0,0,0.08)" }} />
                  <Legend />
                  <Line type="monotone" dataKey="ndvi" name="NDVI" stroke="#10b981" strokeWidth={3} dot={{ r: 3 }} />
                  <Line type="monotone" dataKey="ndwi" name="NDWI" stroke="#3b82f6" strokeWidth={3} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
              <p className="mt-2 text-xs text-muted">
                {ndviTrend.note ? `⚠️ ${ndviTrend.note}` : "🛰️ Real Sentinel-2 dry-season composites"}
              </p>
            </>
          ) : (
            <p className="text-sm text-muted">{ndviTrend?.note}</p>
          )}

          <div className="mt-6">
            <SectionTitle>Carbon Stock Trend (Indicative)</SectionTitle>
            {carbonTrendData ? (
              <>
                <ResponsiveContainer width="100%" height={220}>
                  <AreaChart data={carbonTrendData}>
                    <CartesianGrid stroke="rgba(0,0,0,0.06)" />
                    <XAxis dataKey="year" stroke="#94a3b8" fontSize={12} />
                    <YAxis stroke="#94a3b8" fontSize={12} />
                    <Tooltip contentStyle={{ background: "#ffffff", border: "1px solid rgba(0,0,0,0.08)" }} />
                    <Area type="monotone" dataKey="value" stroke="#8b5cf6" fill="rgba(139,92,246,0.15)" strokeWidth={3} />
                  </AreaChart>
                </ResponsiveContainer>
                <p className="mt-2 text-xs text-muted">📈 {carbonTrend.note}</p>
              </>
            ) : (
              <p className="text-sm text-muted">{carbonTrend?.note}</p>
            )}
          </div>
        </div>

        <div className="glass-card p-5">
          <SectionTitle>Carbon Pool Distribution</SectionTitle>
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie data={pieData} dataKey="value" nameKey="name" innerRadius={55} outerRadius={90} paddingAngle={2}>
                {pieData.map((_, i) => (
                  <Cell key={i} fill={PIE_COLORS[i]} />
                ))}
              </Pie>
              <Tooltip contentStyle={{ background: "#ffffff", border: "1px solid rgba(0,0,0,0.08)" }} />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
          <p className="mt-3 text-xs text-muted">
            Soil organic carbon represents up to 75% of mangrove sinks due to slow decomposition rates in
            waterlogged salt soils.
          </p>
        </div>
      </div>
    </div>
  );
}

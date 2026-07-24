import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { MetricCard, SectionTitle } from "./Shared.jsx";

export default function VegetationHealth({ analysis }) {
  const ndvi = analysis.current_ndvi;
  const ndviStatus = ndvi > 0.7 ? "Dense Canopy" : ndvi > 0.55 ? "Moderate Canopy" : "Sparse/Stressed";

  const stress = analysis.current_et_stress;
  const stressStatus =
    stress < 0.2 ? "Stagnant (Unstressed)" :
    stress < 0.4 ? "Low Stress Anomaly" :
    stress < 0.6 ? "Moderate Canopy Stress" : "Severe Moisture Deficit";

  const chartData = (analysis.historical_et_dates || []).map((date, i) => ({
    date,
    et: analysis.historical_et[i],
    tempAnomaly: analysis.historical_temp_anom[i],
  }));

  return (
    <div>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="space-y-4">
          <SectionTitle>Biophysical Canopy Indexes</SectionTitle>
          <MetricCard label="NDVI Index" value={ndvi.toFixed(3)} sub={ndviStatus} accent={ndvi > 0.55 ? "emerald" : "rose"} />
          <MetricCard label="NDWI (Water Index)" value={analysis.current_ndwi.toFixed(3)} sub="Waterlogged Substrate" accent="blue" />
          <MetricCard
            label="Evapotranspiration Stress"
            value={stress.toFixed(2)}
            sub={stressStatus}
            accent={stress > 0.4 ? "rose" : "emerald"}
          />
        </div>

        <div className="glass-card p-5 lg:col-span-2">
          <SectionTitle>2-Year Monthly Evapotranspiration vs Temperature Anomaly</SectionTitle>
          <ResponsiveContainer width="100%" height={340}>
            <ComposedChart data={chartData}>
              <CartesianGrid stroke="rgba(0,0,0,0.06)" />
              <XAxis dataKey="date" stroke="#94a3b8" fontSize={11} />
              <YAxis yAxisId="left" stroke="#3b82f6" fontSize={12} />
              <YAxis yAxisId="right" orientation="right" stroke="#f43f5e" fontSize={12} />
              <Tooltip contentStyle={{ background: "#ffffff", border: "1px solid rgba(0,0,0,0.08)" }} />
              <Legend />
              <Bar yAxisId="left" dataKey="et" name="Evapotranspiration (mm/month)" fill="rgba(59,130,246,0.4)" stroke="#3b82f6" />
              <Line yAxisId="right" type="monotone" dataKey="tempAnomaly" name="LST Temp Anomaly (°C)" stroke="#f43f5e" strokeWidth={2.5} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
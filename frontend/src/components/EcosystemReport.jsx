import { useState } from "react";
import { Download, CheckCircle2, AlertTriangle, XCircle, Info } from "lucide-react";
import { MetricCard, SectionTitle } from "./Shared.jsx";
import { api } from "../lib/api.js";

const STATUS_STYLE = {
  Ready: { icon: CheckCircle2, color: "emerald" },
  "Needs Review": { icon: AlertTriangle, color: "amber" },
  "Not Ready": { icon: XCircle, color: "rose" },
};

const ITEM_ICON = { pass: CheckCircle2, warning: AlertTriangle, fail: XCircle };
const ITEM_COLOR = { pass: "#10b981", warning: "#f59e0b", fail: "#f43f5e" };

export default function EcosystemReport({ projectName, analysis, carbon, projectMeta, checklist, readiness }) {
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");

  const statusInfo = STATUS_STYLE[readiness.status] || STATUS_STYLE["Needs Review"];
  const StatusIcon = statusInfo.icon;

  async function handleDownload() {
    setDownloading(true);
    setError("");
    try {
      const { blob, filename } = await api.downloadReportPdf({
        project_name: projectName,
        analysis,
        carbon,
        project_meta: projectMeta,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message || "Failed to generate report.");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div>
      <SectionTitle>Ecosystem Status Summary</SectionTitle>
      <p className="mb-3 text-sm text-muted">
        Remote-sensing MRV evidence pack — indicative monitoring summary for review by governments, NGOs, and
        carbon marketplace stakeholders.
      </p>
      <div className="mb-5 flex items-start gap-2 rounded-lg border border-black/10 bg-black/[0.05] px-3.5 py-2.5 text-xs text-muted">
        <Info size={14} className="mt-0.5 shrink-0 text-blue" />
        This report is intended as verification support and does not constitute official carbon credit
        accreditation.
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="glass-card flex items-center gap-3 px-5 py-4">
          <StatusIcon size={22} color={`var(--${statusInfo.color})`} className="shrink-0" style={{ color: "#10b981" }} />
          <div>
            <p className="text-[11px] uppercase tracking-wider text-muted">Status</p>
            <p className="font-display text-lg font-semibold text-ink">{readiness.status}</p>
          </div>
        </div>
        <MetricCard label="Evidence Completeness" value={`${readiness.score_pct.toFixed(0)}%`} accent="blue" />
        <MetricCard
          label="Gross Indicative CO₂e"
          value={readiness.gross_co2e ? `${readiness.gross_co2e.toLocaleString()} tCO2e` : "N/A"}
          accent="violet"
        />
      </div>

      <p className="mt-3 rounded-lg border border-black/10 bg-black/[0.05] px-4 py-3 text-sm text-ink">
        {readiness.summary_note}
      </p>
      <p className="mt-2 text-xs text-muted">
        Net tCO2e (post-buffer/deduction) will be added once accredited deduction methodology is applied.
      </p>

      <div className="my-6 h-px bg-black/[0.08]" />

      <SectionTitle>Verification Readiness Checklist</SectionTitle>
      <p className="mb-4 text-xs text-muted">
        Each item below is derived directly from the monitoring evidence collected for this project. This
        checklist supports — but does not replace — formal verification.
      </p>

      <div className="space-y-3">
        {checklist.map((entry, i) => {
          const Icon = ITEM_ICON[entry.status] || AlertTriangle;
          return (
            <div key={i} className="flex items-start gap-3 rounded-lg border border-black/10 bg-black/[0.05] px-4 py-3">
              <Icon size={17} style={{ color: ITEM_COLOR[entry.status] || "#94a3b8" }} className="mt-0.5 shrink-0" />
              <div>
                <p className="text-sm font-semibold text-ink">{entry.item}</p>
                <p className="text-xs text-muted">{entry.note}</p>
              </div>
            </div>
          );
        })}
      </div>

      <div className="my-6 h-px bg-black/[0.08]" />

      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
        <div>
          <SectionTitle>Included in PDF Evidence Pack</SectionTitle>
          <ul className="space-y-1.5 text-sm text-ink">
            {[
              "Bounding box GPS coordinates & area (ha)",
              "GEDI LiDAR canopy heights / measured biomass",
              "Carbon sinks breakdown (AGC, BGC, SOC)",
              "Evapotranspiration (ET) stress indices",
              "Deforestation alert log",
              "Pre-verification checklist findings",
            ].map((item) => (
              <li key={item} className="flex items-start gap-2">
                <CheckCircle2 size={14} className="mt-1 shrink-0 text-emerald" />
                {item}
              </li>
            ))}
          </ul>
        </div>

        <div>
          <SectionTitle>Export Report</SectionTitle>
          <button
            onClick={handleDownload}
            disabled={downloading}
            className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-emerald to-blue px-5 py-3 text-sm font-semibold text-white transition-transform hover:scale-[1.02] disabled:opacity-60"
          >
            <Download size={16} />
            {downloading ? "Compiling PDF..." : "Download MRV Evidence Pack (PDF)"}
          </button>
          {error && <p className="mt-2 text-sm text-rose">{error}</p>}
        </div>
      </div>
    </div>
  );
}
import { Sprout, RefreshCw, Satellite, Dices } from "lucide-react";

export default function Sidebar({ useSandbox, setUseSandbox, isLive, projectMeta, onRefresh, refreshing }) {
  const confidence = projectMeta?.data_confidence || "unverified";
  const confidenceBox = {
    verified: {
      className: "border-emerald/25 bg-emerald/10 text-emerald",
      text: "Site boundary based on verified administrative coordinates.",
    },
    approximate: {
      className: "border-amber/25 bg-amber/10 text-amber",
      text:
        "Approximate boundary — this project's exact GPS footprint is not publicly published. Coordinates are relocated onto real nearby mapped mangrove as a regional stand-in.",
    },
    unverified: {
      className: "border-blue/25 bg-blue/10 text-blue",
      text: "Custom-drawn area — boundary accuracy depends on the user's manual selection.",
    },
  }[confidence];

  return (
    <aside className="glass-card sticky top-4 flex h-fit w-full max-w-xs flex-col gap-5 p-5">
      <div className="flex items-center gap-2">
        <span className="grid h-9 w-9 place-items-center rounded-lg bg-emerald/15 text-emerald">
          <Sprout size={18} />
        </span>
        <p className="font-display text-sm font-semibold text-ink">Monitoring Controls</p>
      </div>

      <label className="flex items-center justify-between text-sm text-ink">
        <span className="flex items-center gap-2">
          <Dices size={15} className="text-muted" />
          Deterministic Sandbox Mode
        </span>
        <button
          onClick={() => setUseSandbox(!useSandbox)}
          className={`h-5 w-9 rounded-full transition-colors ${useSandbox ? "bg-emerald" : "bg-black/[0.08]"}`}
        >
          <span
            className={`block h-4 w-4 translate-y-0.5 rounded-full bg-white transition-transform ${
              useSandbox ? "translate-x-4" : "translate-x-0.5"
            }`}
          />
        </button>
      </label>

      <div className="h-px bg-black/[0.08]" />

      <div
        className={`flex items-center gap-2 rounded-lg px-3 py-2 text-xs ${
          isLive ? "bg-emerald/10 text-emerald" : "bg-blue/10 text-blue"
        }`}
      >
        <Satellite size={14} />
        {isLive ? "Connected to Live Earth Engine" : "Active: Offline Simulation Engine"}
      </div>

      <button
        onClick={onRefresh}
        disabled={refreshing}
        className="flex items-center justify-center gap-2 rounded-lg border border-black/10 bg-black/[0.04] py-2.5 text-sm font-medium text-ink hover:border-emerald disabled:opacity-60"
      >
        <RefreshCw size={15} className={refreshing ? "animate-spin" : ""} />
        {refreshing ? "Refreshing..." : "Refresh Data"}
      </button>

      <div className="h-px bg-black/[0.08]" />

      {projectMeta && (
        <div className="space-y-1.5 text-sm text-ink">
          <p className="text-xs uppercase tracking-wide text-muted">Project Details</p>
          <p>
            <span className="text-muted">Registry Standard:</span> {projectMeta.standard}
          </p>
          <p>
            <span className="text-muted">Trees Planted:</span> {projectMeta.trees}
          </p>
          <p>
            <span className="text-muted">Species:</span> {projectMeta.species}
          </p>
        </div>
      )}

      {confidenceBox && (
        <div className={`rounded-lg border px-3 py-2.5 text-xs ${confidenceBox.className}`}>
          {confidenceBox.text}
        </div>
      )}
    </aside>
  );
}
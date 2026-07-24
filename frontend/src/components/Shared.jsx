import { Leaf } from "lucide-react";

export function MetricCard({ label, value, sub, accent = "emerald" }) {
  const accentColor = { emerald: "#10b981", blue: "#3b82f6", violet: "#8b5cf6", rose: "#f43f5e" }[accent];
  return (
    <div className="glass-card metric-hover px-5 py-4 transition-transform">
      <p className="text-[11px] uppercase tracking-wider text-muted">{label}</p>
      <p className="mt-1 font-display text-2xl font-semibold" style={{ color: accentColor }}>
        {value}
      </p>
      {sub && <p className="mt-1 text-xs text-muted">{sub}</p>}
    </div>
  );
}

export function InfoBox({ children }) {
  return (
    <div className="mb-5 rounded-lg border border-blue/20 bg-blue/10 px-4 py-3 text-sm text-blue-200">
      {children}
    </div>
  );
}

export function SectionTitle({ children }) {
  return <h3 className="mb-3 font-display text-base font-semibold text-ink">{children}</h3>;
}

const STATUS_BADGE_CLASS = {
  Ready: "badge-ready",
  "Needs Review": "badge-review",
  "Not Ready": "badge-notready",
};

export function StatusBadge({ status }) {
  const cls = STATUS_BADGE_CLASS[status] || "badge-review";
  return (
    <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide ${cls}`}>
      {status}
    </span>
  );
}

/**
 * Brand mark. Looks for /logo.png (drop your logo file into frontend/public/logo.png)
 * and falls back to a small leaf glyph so the layout never breaks if it's missing.
 */
export function Logo({ size = 32, showWordmark = true, dark = false }) {
  return (
    <div className="flex items-center gap-2">
      <span
        className="relative grid shrink-0 place-items-center overflow-hidden rounded-lg"
        style={{ width: size, height: size, background: dark ? "rgba(233,223,199,0.1)" : "rgba(16,185,129,0.15)" }}
      >
        <img
          src="/logo.jpeg"
          alt="Delta"
          className="h-full w-full object-contain"
          onError={(e) => {
            e.currentTarget.style.display = "none";
            e.currentTarget.nextSibling.style.display = "grid";
          }}
        />
        <Leaf
          size={size * 0.6}
          className={dark ? "text-sand" : "text-emerald"}
          style={{ display: "none", position: "absolute" }}
        />
      </span>
      {showWordmark && (
        <span className={`font-display text-lg font-semibold ${dark ? "text-sand" : "text-ink"}`}>Delta</span>
      )}
    </div>
  );
}
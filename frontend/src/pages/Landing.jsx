import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Radar, FileCheck2, BellRing, MapPin, ChevronDown } from "lucide-react";
import { api } from "../lib/api.js";
import { Logo, StatusBadge } from "../components/Shared.jsx";

const FEATURES = [
  {
    icon: Radar,
    title: "Continuous monitoring",
    body: "Canopy health and carbon stock tracked from satellite data, year-round.",
  },
  {
    icon: FileCheck2,
    title: "Verification-ready evidence",
    body: "Audit-ready reports built around recognized MRV checklists.",
  },
  {
    icon: BellRing,
    title: "Early loss alerts",
    body: "Canopy loss flagged early, before it threatens project integrity.",
  },
];

function useRevealOnScroll() {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          el.classList.add("is-visible");
          obs.disconnect();
        }
      },
      { threshold: 0.15 }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);
  return ref;
}

function ProjectCard({ project, onOpen }) {
  const ref = useRevealOnScroll();
  return (
    <button
      ref={ref}
      onClick={() => onOpen(project.id)}
      className="earth-card reveal-on-scroll flex flex-col gap-3 p-5 text-left"
    >
      <div className="flex items-start justify-between gap-2">
        <p className="font-display text-lg font-semibold text-forest">{project.name}</p>
        <StatusBadge status={project.status} />
      </div>
      <p className="flex items-center gap-1.5 text-xs text-forestmuted">
        <MapPin size={13} />
        {project.location}
      </p>
      <div className="mt-1 flex items-baseline gap-1.5">
        <span className="font-display text-2xl font-semibold text-moss">
          {project.areaHa != null ? project.areaHa.toLocaleString() : "—"}
        </span>
        <span className="text-xs text-forestmuted">hectares monitored</span>
      </div>
    </button>
  );
}

function CardSkeleton() {
  return <div className="earth-card h-[152px] animate-pulse bg-forest/[0.04]" />;
}

export default function Landing() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState(null);
  const [error, setError] = useState("");
  const cardsRef = useRef(null);

  useEffect(() => {
    api
      .listProjectSummaries()
      .then(setProjects)
      .catch((err) => setError(err.message || "Could not load projects."));
  }, []);

  function scrollToCards() {
    cardsRef.current?.scrollIntoView({ behavior: "smooth" });
  }

  return (
    <div className="earth-root">
      {/* ---------- Hero ---------- */}
      <section className="hero-scene flex flex-col items-center justify-center px-6 text-center">
        <div className="absolute left-6 top-6 z-10">
          <Logo dark size={44} />
        </div>

        <div className="hero-copy relative z-10 flex max-w-2xl flex-col items-center gap-6">
          <h1 className="font-display text-5xl font-bold text-white drop-shadow-sm sm:text-6xl">Delta</h1>
          <p className="text-lg text-white/95 drop-shadow-sm sm:text-xl">
            Satellite-verified monitoring for blue carbon mangrove ecosystems.
          </p>
          <div className="mt-3 grid grid-cols-1 gap-6 sm:grid-cols-3">
            {FEATURES.map((f) => (
              <div key={f.title} className="flex flex-col items-center gap-2 px-2">
                <f.icon size={22} className="text-[#f3d9bd]" />
                <p className="text-sm font-semibold text-white">{f.title}</p>
                <p className="text-xs leading-relaxed text-white/80">{f.body}</p>
              </div>
            ))}
          </div>
        </div>

        <button
          onClick={scrollToCards}
          aria-label="Scroll to projects"
          className="scroll-cue absolute bottom-5 z-10 text-sand/70 hover:text-sand"
        >
          <ChevronDown size={26} />
        </button>
      </section>

      {/* ---------- Project dashboard ---------- */}
      <section ref={cardsRef} className="mx-auto max-w-6xl px-6 py-16 sm:px-10">
        <h2 className="mb-1 font-display text-2xl font-semibold text-forest">Projects</h2>
        <p className="mb-8 text-sm text-forestmuted">Select a project to open its monitoring dashboard.</p>

        {error && (
          <div className="mb-6 rounded-lg border border-clay/30 bg-clay/10 px-4 py-3 text-sm text-clay">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {projects
            ? projects.map((p) => (
                <ProjectCard key={p.id} project={p} onOpen={(id) => navigate(`/projects/${id}`)} />
              ))
            : Array.from({ length: 3 }).map((_, i) => <CardSkeleton key={i} />)}
        </div>
      </section>
    </div>
  );
}
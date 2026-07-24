import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Radar, FileCheck2, BellRing, MapPin, ChevronDown } from "lucide-react";
import { api } from "../lib/api.js";
import { Logo, Modal, AddProjectCard } from "../components/Shared.jsx";
 
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
      <p className="font-display text-lg font-semibold text-forest">{project.name}</p>
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
 
const EMPTY_FORM = {
  name: "",
  latitude: "",
  longitude: "",
  area: "",
  registryStandard: "",
  treesPlanted: "",
  species: "",
};
 
export default function Landing() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState(null);
  const [error, setError] = useState("");
  const cardsRef = useRef(null);
 
  const [showAddModal, setShowAddModal] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);
 
  function loadProjects() {
    return api
      .listProjectSummaries()
      .then(setProjects)
      .catch((err) => setError(err.message || "Could not load projects."));
  }
 
  useEffect(() => {
    loadProjects();
  }, []);
 
  function scrollToCards() {
    cardsRef.current?.scrollIntoView({ behavior: "smooth" });
  }
 
  function openAddModal() {
    setForm(EMPTY_FORM);
    setFormError("");
    setShowAddModal(true);
  }
 
  async function handleAddProject(e) {
    e.preventDefault();
    setFormError("");
 
    const name = form.name.trim();
    const lat = parseFloat(form.latitude);
    const lng = parseFloat(form.longitude);
 
    if (!name) return setFormError("Project name is required.");
    if (Number.isNaN(lat) || lat < -90 || lat > 90) {
      return setFormError("Enter a valid latitude (-90 to 90).");
    }
    if (Number.isNaN(lng) || lng < -180 || lng > 180) {
      return setFormError("Enter a valid longitude (-180 to 180).");
    }
 
    const area = parseFloat(form.area);
    if (Number.isNaN(area) || area <= 0) {
      return setFormError("Enter a valid area in hectares (greater than 0).");
    }
 
    const registryStandard = form.registryStandard.trim();
    const treesPlanted = form.treesPlanted.trim();
    const species = form.species.trim();
 
    if (!registryStandard) return setFormError("Registry Standard is required.");
    if (!treesPlanted) return setFormError("Trees Planted is required.");
    if (!species) return setFormError("Species is required.");
 
    setSubmitting(true);
    try {
      await api.addProject({
        name,
        latitude: lat,
        longitude: lng,
        areaHa: area,
        registryStandard,
        treesPlanted,
        species,
      });
      setShowAddModal(false);
      setForm(EMPTY_FORM);
      setProjects(null); // show skeletons while the new project's summary loads
      await loadProjects();
    } catch (err) {
      setFormError(err.message || "Could not add project.");
    } finally {
      setSubmitting(false);
    }
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
 
          {projects && <AddProjectCard onClick={openAddModal} />}
        </div>
      </section>
 
      {/* ---------- Add Project Modal ---------- */}
      <Modal open={showAddModal} onClose={() => setShowAddModal(false)} title="Add New Project">
        <form onSubmit={handleAddProject} className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-forestmuted">Project Name</label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="e.g. Kultali Restoration Block"
              className="w-full rounded-lg border border-forest/15 bg-white px-3 py-2 text-sm text-ink outline-none focus:border-emerald"
            />
          </div>
 
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-forestmuted">Latitude</label>
              <input
                type="number"
                step="any"
                value={form.latitude}
                onChange={(e) => setForm((f) => ({ ...f, latitude: e.target.value }))}
                placeholder="22.0866"
                className="w-full rounded-lg border border-forest/15 bg-white px-3 py-2 text-sm text-ink outline-none focus:border-emerald"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-forestmuted">Longitude</label>
              <input
                type="number"
                step="any"
                value={form.longitude}
                onChange={(e) => setForm((f) => ({ ...f, longitude: e.target.value }))}
                placeholder="88.5937"
                className="w-full rounded-lg border border-forest/15 bg-white px-3 py-2 text-sm text-ink outline-none focus:border-emerald"
              />
            </div>
          </div>
 
          <div>
            <label className="mb-1 block text-xs font-medium text-forestmuted">Area Covered (hectares)</label>
            <input
              type="number"
              step="any"
              min="0"
              value={form.area}
              onChange={(e) => setForm((f) => ({ ...f, area: e.target.value }))}
              placeholder="e.g. 250"
              className="w-full rounded-lg border border-forest/15 bg-white px-3 py-2 text-sm text-ink outline-none focus:border-emerald"
            />
          </div>
 
          <div>
            <label className="mb-1 block text-xs font-medium text-forestmuted">Registry Standard</label>
            <input
              type="text"
              value={form.registryStandard}
              onChange={(e) => setForm((f) => ({ ...f, registryStandard: e.target.value }))}
              placeholder="e.g. Verified Carbon Standard (VCS)"
              className="w-full rounded-lg border border-forest/15 bg-white px-3 py-2 text-sm text-ink outline-none focus:border-emerald"
            />
          </div>
 
          <div>
            <label className="mb-1 block text-xs font-medium text-forestmuted">Trees Planted</label>
            <input
              type="text"
              value={form.treesPlanted}
              onChange={(e) => setForm((f) => ({ ...f, treesPlanted: e.target.value }))}
              placeholder="e.g. 5 Million"
              className="w-full rounded-lg border border-forest/15 bg-white px-3 py-2 text-sm text-ink outline-none focus:border-emerald"
            />
          </div>
 
          <div>
            <label className="mb-1 block text-xs font-medium text-forestmuted">Species</label>
            <input
              type="text"
              value={form.species}
              onChange={(e) => setForm((f) => ({ ...f, species: e.target.value }))}
              placeholder="e.g. Sundari, Garjan, Kankra"
              className="w-full rounded-lg border border-forest/15 bg-white px-3 py-2 text-sm text-ink outline-none focus:border-emerald"
            />
          </div>
 
          {formError && <p className="text-xs font-medium text-clay">{formError}</p>}
 
          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-lg bg-emerald px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald/90 disabled:opacity-50"
          >
            {submitting ? "Adding…" : "Add Project"}
          </button>
        </form>
      </Modal>
    </div>
  );
}
 

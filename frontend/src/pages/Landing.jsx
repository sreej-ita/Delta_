import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Radar, FileCheck2, BellRing, MapPin, ChevronDown, MoreVertical, Pencil, Trash2, X } from "lucide-react";
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

// Each entry's body is a bit more detailed than a one-line teaser, since
// only one section is shown at a time now — there's room to say more.
const BANNER_SECTIONS = [
  {
    title: "Features",
    body: "Continuous satellite monitoring tracks canopy health and carbon stock year-round, with no manual fieldwork required. Every project gets verification-ready evidence packs built around recognized MRV checklists, plus early deforestation alerts that flag canopy loss before it threatens a project's integrity. Live and simulated (sandbox) data modes let you explore the platform freely before connecting real satellite feeds.",
  },
  {
    title: "How It Works",
    body: "It starts with a project boundary — either drawn directly on the map or entered as coordinates and an area. From there, satellite data (vegetation indices, elevation, canopy height, and biomass signals) is pulled for that exact area and run through a machine learning model trained to estimate carbon stock and vegetation health. The platform continuously re-checks that boundary over time, flagging any canopy loss it detects. Everything the model produces — carbon estimates, health metrics, and a verification readiness checklist — rolls up into a single exportable PDF evidence pack, so the numbers behind every hectare are traceable back to their source.",
  },
  {
    title: "About Us",
    body: "We built Delta to make ecosystem restoration verifiable, not just reported. Too many restoration claims rely on numbers no one outside the project can check. Our goal is to close that gap — giving developers, verifiers, and funders a shared, satellite-grounded view of what's actually happening on the ground, so trust in restoration data doesn't have to be taken on faith.",
  },
];

// ---- Degrees/Minutes/Direction <-> decimal degrees helpers ----
// The backend and all coordinate math still work in plain decimal degrees;
// this conversion only happens at the UI boundary (display + form submit).
function decimalToDM(decimalValue) {
  const abs = Math.abs(decimalValue);
  const degrees = Math.floor(abs);
  const minutes = Math.round((abs - degrees) * 60 * 100) / 100; // 2 decimal places of precision
  return { degrees, minutes };
}

function dmToDecimal(degrees, minutes, negative) {
  const decimal = degrees + minutes / 60;
  return negative ? -decimal : decimal;
}

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

function ProjectCard({ project, onOpen, onEdit, onDelete, menuOpen, onToggleMenu, deleting }) {
  const ref = useRevealOnScroll();

  return (
    <div
      ref={ref}
      role="button"
      tabIndex={0}
      onClick={() => onOpen(project.id)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") onOpen(project.id);
      }}
      className="earth-card reveal-on-scroll relative flex cursor-pointer flex-col gap-3 p-5 text-left"
    >
      {project.editable && (
        <div className="absolute right-3 top-3" onClick={(e) => e.stopPropagation()}>
          <button
            onClick={() => onToggleMenu(project.id)}
            aria-label="Project options"
            className="rounded-full p-1 text-forestmuted transition hover:bg-forest/10 hover:text-forest"
          >
            <MoreVertical size={16} />
          </button>

          {menuOpen && (
            <div className="absolute right-0 top-7 z-10 w-40 overflow-hidden rounded-lg border border-forest/10 bg-white shadow-lg">
              <button
                onClick={() => onEdit(project)}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-medium text-ink hover:bg-forest/5"
              >
                <Pencil size={13} />
                Edit Project
              </button>
              <button
                onClick={() => onDelete(project)}
                disabled={deleting}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-medium text-clay hover:bg-clay/10 disabled:opacity-50"
              >
                <Trash2 size={13} />
                {deleting ? "Deleting…" : "Delete Project"}
              </button>
            </div>
          )}
        </div>
      )}

      <p className="pr-6 font-display text-lg font-semibold text-forest">{project.name}</p>
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
    </div>
  );
}

function CardSkeleton() {
  return <div className="earth-card h-[152px] animate-pulse bg-forest/[0.04]" />;
}

const EMPTY_FORM = {
  name: "",
  latDeg: "",
  latMin: "",
  latDir: "N",
  lngDeg: "",
  lngMin: "",
  lngDir: "E",
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

  // Tracks WHICH banner section is showing — null means the banner is
  // closed. Only one section renders at a time, matching whichever nav
  // link was clicked, instead of always showing all three.
  const [activeSection, setActiveSection] = useState(null);

  const [showAddModal, setShowAddModal] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [editingId, setEditingId] = useState(null); // null = creating new, else editing this project's id
  const [editingKind, setEditingKind] = useState("custom"); // "custom" | "builtin" (Baha' Mou / Sundari)

  const [menuOpenId, setMenuOpenId] = useState(null);
  const [deletingId, setDeletingId] = useState(null);

  const activeBannerContent = BANNER_SECTIONS.find((s) => s.title === activeSection) || null;

  function loadProjects() {
    return api
      .listProjectSummaries()
      .then(setProjects)
      .catch((err) => setError(err.message || "Could not load projects."));
  }

  useEffect(() => {
    loadProjects();
  }, []);

  // Close any open project menu when clicking anywhere else on the page
  useEffect(() => {
    function handleDocClick() {
      setMenuOpenId(null);
    }
    document.addEventListener("click", handleDocClick);
    return () => document.removeEventListener("click", handleDocClick);
  }, []);

  function scrollToCards() {
    cardsRef.current?.scrollIntoView({ behavior: "smooth" });
  }

  function openAddModal() {
    setForm(EMPTY_FORM);
    setFormError("");
    setEditingId(null);
    setEditingKind("custom");
    setShowAddModal(true);
  }

  async function openEditModal(project) {
    setMenuOpenId(null);
    setError("");
    try {
      const detail = await api.getProject(project.id);

      let latDeg = "", latMin = "", latDir = "N";
      if (detail.latitude != null) {
        const dm = decimalToDM(detail.latitude);
        latDeg = String(dm.degrees);
        latMin = String(dm.minutes);
        latDir = detail.latitude < 0 ? "S" : "N";
      }

      let lngDeg = "", lngMin = "", lngDir = "E";
      if (detail.longitude != null) {
        const dm = decimalToDM(detail.longitude);
        lngDeg = String(dm.degrees);
        lngMin = String(dm.minutes);
        lngDir = detail.longitude < 0 ? "W" : "E";
      }

      setForm({
        name: detail.name,
        latDeg,
        latMin,
        latDir,
        lngDeg,
        lngMin,
        lngDir,
        area: detail.area_ha != null ? String(detail.area_ha) : "",
        registryStandard: detail.registry_standard,
        treesPlanted: detail.trees_planted,
        species: detail.species,
      });
      setFormError("");
      setEditingId(project.id);
      setEditingKind(detail.kind); // "custom" | "builtin"
      setShowAddModal(true);
    } catch (err) {
      setError(err.message || "Could not load project details.");
    }
  }

  function closeModal() {
    setShowAddModal(false);
    setEditingId(null);
    setEditingKind("custom");
  }

  async function handleDeleteProject(project) {
    setMenuOpenId(null);
    const confirmed = window.confirm(`Delete "${project.name}"? This cannot be undone.`);
    if (!confirmed) return;

    setDeletingId(project.id);
    try {
      await api.deleteProject(project.id);
      setProjects(null);
      await loadProjects();
    } catch (err) {
      setError(err.message || "Could not delete project.");
    } finally {
      setDeletingId(null);
    }
  }

  async function handleSubmitProject(e) {
    e.preventDefault();
    setFormError("");

    const name = form.name.trim();
    const registryStandard = form.registryStandard.trim();
    const treesPlanted = form.treesPlanted.trim();
    const species = form.species.trim();

    if (!name) return setFormError("Project name is required.");
    if (!registryStandard) return setFormError("Registry Standard is required.");
    if (!treesPlanted) return setFormError("Trees Planted is required.");
    if (!species) return setFormError("Species is required.");

    // Baha' Mou / Sundari: descriptive fields only — no location fields to validate
    if (editingId && editingKind === "builtin") {
      setSubmitting(true);
      try {
        await api.updateProjectMetadata(editingId, { name, registryStandard, treesPlanted, species });
        setShowAddModal(false);
        setForm(EMPTY_FORM);
        setEditingId(null);
        setEditingKind("custom");
        setProjects(null);
        await loadProjects();
      } catch (err) {
        setFormError(err.message || "Could not save project.");
      } finally {
        setSubmitting(false);
      }
      return;
    }

    const latDeg = parseFloat(form.latDeg);
    const latMin = parseFloat(form.latMin);
    const lngDeg = parseFloat(form.lngDeg);
    const lngMin = parseFloat(form.lngMin);

    if (Number.isNaN(latDeg) || latDeg < 0 || latDeg > 90) {
      return setFormError("Enter valid latitude degrees (0 to 90).");
    }
    if (Number.isNaN(latMin) || latMin < 0 || latMin >= 60) {
      return setFormError("Enter valid latitude minutes (0 to 59.99).");
    }
    if (Number.isNaN(lngDeg) || lngDeg < 0 || lngDeg > 180) {
      return setFormError("Enter valid longitude degrees (0 to 180).");
    }
    if (Number.isNaN(lngMin) || lngMin < 0 || lngMin >= 60) {
      return setFormError("Enter valid longitude minutes (0 to 59.99).");
    }

    const lat = dmToDecimal(latDeg, latMin, form.latDir === "S");
    const lng = dmToDecimal(lngDeg, lngMin, form.lngDir === "W");

    if (lat < -90 || lat > 90) return setFormError("Latitude is out of range.");
    if (lng < -180 || lng > 180) return setFormError("Longitude is out of range.");

    const area = parseFloat(form.area);
    if (Number.isNaN(area) || area <= 0) {
      return setFormError("Enter a valid area in hectares (greater than 0).");
    }

    setSubmitting(true);
    try {
      const payload = { name, latitude: lat, longitude: lng, areaHa: area, registryStandard, treesPlanted, species };
      if (editingId) {
        await api.updateProject(editingId, payload);
      } else {
        await api.addProject(payload);
      }
      setShowAddModal(false);
      setForm(EMPTY_FORM);
      setEditingId(null);
      setEditingKind("custom");
      setProjects(null); // show skeletons while the updated summary loads
      await loadProjects();
    } catch (err) {
      setFormError(err.message || "Could not save project.");
    } finally {
      setSubmitting(false);
    }
  }

  const showLocationFields = !(editingId && editingKind === "builtin");

  return (
    <div className="earth-root">
      {/* ---------- Dropdown info banner — shows only the clicked section ---------- */}
      {activeBannerContent && (
        <div className="fixed inset-0 z-40" onClick={() => setActiveSection(null)} />
      )}
      <div
        className={
          "fixed inset-x-0 top-0 z-50 transition-transform duration-500 ease-out " +
          (activeBannerContent ? "translate-y-0" : "-translate-y-full")
        }
        style={{
          backgroundImage: "linear-gradient(to bottom, #faf7f0 0%, #faf7f0 65%, rgba(250,247,240,0) 100%)",
        }}
      >
        <div className="mx-auto max-w-3xl px-6 pb-20 pt-8 sm:px-10">
          <div className="mb-4 flex justify-end">
            <button
              onClick={() => setActiveSection(null)}
              className="flex items-center gap-1 text-xs font-medium text-forestmuted transition hover:text-forest"
            >
              <X size={14} />
              Close
            </button>
          </div>
          {activeBannerContent && (
            <div>
              <p className="mb-2 font-display text-lg font-semibold text-forest">{activeBannerContent.title}</p>
              <p className="text-sm leading-relaxed text-forestmuted">{activeBannerContent.body}</p>
            </div>
          )}
        </div>
      </div>

      {/* ---------- Hero ---------- */}
      <section className="hero-scene flex flex-col items-center justify-center px-6 text-center">
        <div className="absolute left-6 top-6 z-10">
          <Logo dark size={44} />
        </div>

        <div className="absolute right-6 top-6 z-10 flex items-center gap-5">
          <button
            onClick={() => setActiveSection("Features")}
            className="text-xs font-medium text-white/85 transition hover:text-white"
          >
            Features
          </button>
          <button
            onClick={() => setActiveSection("How It Works")}
            className="text-xs font-medium text-white/85 transition hover:text-white"
          >
            How It Works
          </button>
          <button
            onClick={() => setActiveSection("About Us")}
            className="text-xs font-medium text-white/85 transition hover:text-white"
          >
            About Us
          </button>
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
                <ProjectCard
                  key={p.id}
                  project={p}
                  onOpen={(id) => navigate(`/projects/${id}`)}
                  onEdit={openEditModal}
                  onDelete={handleDeleteProject}
                  menuOpen={menuOpenId === p.id}
                  onToggleMenu={() => setMenuOpenId((prev) => (prev === p.id ? null : p.id))}
                  deleting={deletingId === p.id}
                />
              ))
            : Array.from({ length: 3 }).map((_, i) => <CardSkeleton key={i} />)}

          {projects && <AddProjectCard onClick={openAddModal} />}
        </div>
      </section>

      {/* ---------- Add / Edit Project Modal ---------- */}
      <Modal open={showAddModal} onClose={closeModal} title={editingId ? "Edit Project" : "Add New Project"}>
        <form onSubmit={handleSubmitProject} className="space-y-4">
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

          {!showLocationFields && (
            <div className="rounded-lg border border-blue/20 bg-blue/10 px-3 py-2 text-xs text-blue-900">
              Location is managed separately for this project and isn't editable here — only the details below.
            </div>
          )}

          {showLocationFields && (
            <>
              <div>
                <label className="mb-1 block text-xs font-medium text-forestmuted">
                  Latitude <span className="font-normal text-forestmuted/70">(Degrees, Minutes, N/S)</span>
                </label>
                <div className="grid grid-cols-[1fr_1fr_74px] gap-2">
                  <input
                    type="number"
                    step="any"
                    min="0"
                    max="90"
                    value={form.latDeg}
                    onChange={(e) => setForm((f) => ({ ...f, latDeg: e.target.value }))}
                    placeholder="Deg (e.g. 21)"
                    className="w-full rounded-lg border border-forest/15 bg-white px-3 py-2 text-sm text-ink outline-none focus:border-emerald"
                  />
                  <input
                    type="number"
                    step="any"
                    min="0"
                    max="59.99"
                    value={form.latMin}
                    onChange={(e) => setForm((f) => ({ ...f, latMin: e.target.value }))}
                    placeholder="Min (e.g. 50)"
                    className="w-full rounded-lg border border-forest/15 bg-white px-3 py-2 text-sm text-ink outline-none focus:border-emerald"
                  />
                  <select
                    value={form.latDir}
                    onChange={(e) => setForm((f) => ({ ...f, latDir: e.target.value }))}
                    className="w-full rounded-lg border border-forest/15 bg-white px-2 py-2 text-sm text-ink outline-none focus:border-emerald"
                  >
                    <option value="N">N</option>
                    <option value="S">S</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="mb-1 block text-xs font-medium text-forestmuted">
                  Longitude <span className="font-normal text-forestmuted/70">(Degrees, Minutes, E/W)</span>
                </label>
                <div className="grid grid-cols-[1fr_1fr_74px] gap-2">
                  <input
                    type="number"
                    step="any"
                    min="0"
                    max="180"
                    value={form.lngDeg}
                    onChange={(e) => setForm((f) => ({ ...f, lngDeg: e.target.value }))}
                    placeholder="Deg (e.g. 88)"
                    className="w-full rounded-lg border border-forest/15 bg-white px-3 py-2 text-sm text-ink outline-none focus:border-emerald"
                  />
                  <input
                    type="number"
                    step="any"
                    min="0"
                    max="59.99"
                    value={form.lngMin}
                    onChange={(e) => setForm((f) => ({ ...f, lngMin: e.target.value }))}
                    placeholder="Min (e.g. 48)"
                    className="w-full rounded-lg border border-forest/15 bg-white px-3 py-2 text-sm text-ink outline-none focus:border-emerald"
                  />
                  <select
                    value={form.lngDir}
                    onChange={(e) => setForm((f) => ({ ...f, lngDir: e.target.value }))}
                    className="w-full rounded-lg border border-forest/15 bg-white px-2 py-2 text-sm text-ink outline-none focus:border-emerald"
                  >
                    <option value="E">E</option>
                    <option value="W">W</option>
                  </select>
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
            </>
          )}

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
            {submitting ? (editingId ? "Saving…" : "Adding…") : editingId ? "Save Changes" : "Add Project"}
          </button>
        </form>
      </Modal>
    </div>
  );
}

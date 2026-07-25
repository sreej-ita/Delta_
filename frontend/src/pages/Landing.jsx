import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Radar, FileCheck2, BellRing, MapPin, ChevronDown, MoreVertical, Pencil, Trash2 } from "lucide-react";
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

// Converts degrees/minutes/hemisphere into signed decimal degrees.
// e.g. (21, 50, "N") -> 21.8333..., (88, 30, "W") -> -88.5
function dmToDecimal(deg, min, dir) {
  const d = parseFloat(deg);
  const m = parseFloat(min);
  if (Number.isNaN(d) || Number.isNaN(m)) return NaN;
  const magnitude = d + m / 60;
  return dir === "S" || dir === "W" ? -magnitude : magnitude;
}

// Converts a signed decimal degree value into { deg, min, dir } for
// prefilling the degree/minute/direction fields when editing a project.
function decimalToDm(value, positiveDir, negativeDir) {
  if (value == null || Number.isNaN(value)) return { deg: "", min: "", dir: positiveDir };
  const dir = value < 0 ? negativeDir : positiveDir;
  const abs = Math.abs(value);
  const deg = Math.floor(abs);
  const min = (abs - deg) * 60;
  // Round minutes to a reasonable precision to avoid float noise (e.g. 49.999999)
  const minRounded = Math.round(min * 1000) / 1000;
  return { deg: String(deg), min: String(minRounded), dir };
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

// Latitude/longitude are collected as degrees + minutes + hemisphere
// (e.g. 21° 50' N), matching the requested input style, then converted to
// decimal degrees right before being sent to the API.
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

  const [showAddModal, setShowAddModal] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [editingId, setEditingId] = useState(null); // null = creating new, else editing this project's id
  const [editingKind, setEditingKind] = useState("custom"); // "custom" | "builtin" (Baha' Mou / Sundari)

  const [menuOpenId, setMenuOpenId] = useState(null);
  const [deletingId, setDeletingId] = useState(null);

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
      const latParts = decimalToDm(detail.latitude, "N", "S");
      const lngParts = decimalToDm(detail.longitude, "E", "W");
      setForm({
        name: detail.name,
        latDeg: latParts.deg,
        latMin: latParts.min,
        latDir: latParts.dir,
        lngDeg: lngParts.deg,
        lngMin: lngParts.min,
        lngDir: lngParts.dir,
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

    const latDegNum = parseFloat(form.latDeg);
    const latMinNum = parseFloat(form.latMin);
    const lngDegNum = parseFloat(form.lngDeg);
    const lngMinNum = parseFloat(form.lngMin);

    if (Number.isNaN(latDegNum) || latDegNum < 0 || latDegNum > 90) {
      return setFormError("Enter valid latitude degrees (0 to 90).");
    }
    if (Number.isNaN(latMinNum) || latMinNum < 0 || latMinNum >= 60) {
      return setFormError("Enter valid latitude minutes (0 to 59).");
    }
    if (Number.isNaN(lngDegNum) || lngDegNum < 0 || lngDegNum > 180) {
      return setFormError("Enter valid longitude degrees (0 to 180).");
    }
    if (Number.isNaN(lngMinNum) || lngMinNum < 0 || lngMinNum >= 60) {
      return setFormError("Enter valid longitude minutes (0 to 59).");
    }

    const lat = dmToDecimal(form.latDeg, form.latMin, form.latDir);
    const lng = dmToDecimal(form.lngDeg, form.lngMin, form.lngDir);

    if (Number.isNaN(lat) || lat < -90 || lat > 90) {
      return setFormError("Latitude works out to an invalid value.");
    }
    if (Number.isNaN(lng) || lng < -180 || lng > 180) {
      return setFormError("Longitude works out to an invalid value.");
    }

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

          {editingId && editingKind === "builtin" && (
            <div className="rounded-lg border border-blue/20 bg-blue/10 px-3 py-2 text-xs text-blue-900">
              Location is managed separately for this project and isn't editable here — only the details below.
            </div>
          )}

          {!(editingId && editingKind === "builtin") && (
            <>
              <div className="grid grid-cols-2 gap-3">
                {/* ---- Latitude: degrees / minutes / N-S ---- */}
                <div>
                  <label className="mb-1 block text-xs font-medium text-forestmuted">Latitude</label>
                  <div className="flex items-center gap-1">
                    <input
                      type="number"
                      step="any"
                      min="0"
                      max="90"
                      value={form.latDeg}
                      onChange={(e) => setForm((f) => ({ ...f, latDeg: e.target.value }))}
                      placeholder="21"
                      className="w-full min-w-0 rounded-lg border border-forest/15 bg-white px-2 py-2 text-sm text-ink outline-none focus:border-emerald"
                    />
                    <span className="text-sm text-forestmuted">°</span>
                    <input
                      type="number"
                      step="any"
                      min="0"
                      max="59"
                      value={form.latMin}
                      onChange={(e) => setForm((f) => ({ ...f, latMin: e.target.value }))}
                      placeholder="50"
                      className="w-full min-w-0 rounded-lg border border-forest/15 bg-white px-2 py-2 text-sm text-ink outline-none focus:border-emerald"
                    />
                    <span className="text-sm text-forestmuted">'</span>
                    <select
                      value={form.latDir}
                      onChange={(e) => setForm((f) => ({ ...f, latDir: e.target.value }))}
                      className="rounded-lg border border-forest/15 bg-white px-1.5 py-2 text-sm text-ink outline-none focus:border-emerald"
                    >
                      <option value="N">N</option>
                      <option value="S">S</option>
                    </select>
                  </div>
                </div>

                {/* ---- Longitude: degrees / minutes / E-W ---- */}
                <div>
                  <label className="mb-1 block text-xs font-medium text-forestmuted">Longitude</label>
                  <div className="flex items-center gap-1">
                    <input
                      type="number"
                      step="any"
                      min="0"
                      max="180"
                      value={form.lngDeg}
                      onChange={(e) => setForm((f) => ({ ...f, lngDeg: e.target.value }))}
                      placeholder="88"
                      className="w-full min-w-0 rounded-lg border border-forest/15 bg-white px-2 py-2 text-sm text-ink outline-none focus:border-emerald"
                    />
                    <span className="text-sm text-forestmuted">°</span>
                    <input
                      type="number"
                      step="any"
                      min="0"
                      max="59"
                      value={form.lngMin}
                      onChange={(e) => setForm((f) => ({ ...f, lngMin: e.target.value }))}
                      placeholder="30"
                      className="w-full min-w-0 rounded-lg border border-forest/15 bg-white px-2 py-2 text-sm text-ink outline-none focus:border-emerald"
                    />
                    <span className="text-sm text-forestmuted">'</span>
                    <select
                      value={form.lngDir}
                      onChange={(e) => setForm((f) => ({ ...f, lngDir: e.target.value }))}
                      className="rounded-lg border border-forest/15 bg-white px-1.5 py-2 text-sm text-ink outline-none focus:border-emerald"
                    >
                      <option value="E">E</option>
                      <option value="W">W</option>
                    </select>
                  </div>
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

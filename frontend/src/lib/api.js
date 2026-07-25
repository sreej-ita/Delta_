const BASE = "/api";
 
async function handle(res) {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {}
    throw new Error(detail);
  }
  return res;
}
 
export const api = {
  async listSites() {
    const res = await fetch(`${BASE}/sites`);
    await handle(res);
    return res.json();
  },
 
  async analyze(payload) {
    const res = await fetch(`${BASE}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    await handle(res);
    return res.json();
  },
 
  /**
   * Registers a brand-new project by name + coordinates. The backend
   * generates an id and small default boundary around the point, then
   * returns a SiteOption so the frontend can immediately re-fetch summaries.
   */
  async addProject({ name, latitude, longitude, areaHa, registryStandard, treesPlanted, species }) {
    const res = await fetch(`${BASE}/sites`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        latitude,
        longitude,
        area_ha: areaHa,
        registry_standard: registryStandard,
        trees_planted: treesPlanted,
        species,
      }),
    });
    await handle(res);
    return res.json();
  },
 
  /** Fetches the full editable record for a user-added project (used to pre-fill the Edit modal). */
  async getProject(id) {
    const res = await fetch(`${BASE}/sites/${id}`);
    await handle(res);
    return res.json();
  },
 
  /** Edits an existing user-added project in place; the project's id/URL stays the same. */
  async updateProject(id, { name, latitude, longitude, areaHa, registryStandard, treesPlanted, species }) {
    const res = await fetch(`${BASE}/sites/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        latitude,
        longitude,
        area_ha: areaHa,
        registry_standard: registryStandard,
        trees_planted: treesPlanted,
        species,
      }),
    });
    await handle(res);
    return res.json();
  },
 
  /** Edits Baha' Mou / Sundari's descriptive fields only (name, registry info) — their location logic isn't user-editable. */
  async updateProjectMetadata(id, { name, registryStandard, treesPlanted, species }) {
    const res = await fetch(`${BASE}/sites/${id}/metadata`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        registry_standard: registryStandard,
        trees_planted: treesPlanted,
        species,
      }),
    });
    await handle(res);
    return res.json();
  },
 
  /** Permanently deletes a user-added project. */
  async deleteProject(id) {
    const res = await fetch(`${BASE}/sites/${id}`, { method: "DELETE" });
    await handle(res);
    return res.json();
  },
 
  async downloadReportPdf(payload) {
    const res = await fetch(`${BASE}/report/pdf`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    await handle(res);
    const blob = await res.blob();
    const disposition = res.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="(.+)"/);
    return { blob, filename: match ? match[1] : "report.pdf" };
  },
 
  /**
   * Aggregates one lightweight analysis per site so the project dashboard can
   * show a card (name, approximate location, area, status) without the user
   * having to open every project first.
   *
   * NOTE: this calls /analyze once per site under the hood, since /sites only
   * exposes id/label/blocks today. If the backend ever grows a dedicated
   * summary endpoint, swap this out for a single request.
   */
  async listProjectSummaries() {
    const sites = await api.listSites();
    const realProjects = sites.filter((s) => s.id !== "custom");
    const summaries = await Promise.all(
      realProjects.map(async (site) => {
        try {
          const blockName = site.blocks && site.blocks.length ? site.blocks[0] : undefined;
          const data = await api.analyze({
            site_id: site.id,
            block_name: blockName,
            use_sandbox: false,
            force_refresh: false,
          });
          const [lng, lat] = centroid(data.coords || []);
          return {
            id: site.id,
            name: site.label,
            block: blockName,
            location: lat != null ? `${lat.toFixed(2)}°N, ${lng.toFixed(2)}°E` : "Location pending",
            areaHa: data.analysis?.area_ha ?? null,
            status: data.readiness?.status ?? "Needs Review",
            valid: data.habitat_valid !== false,
            editable: site.editable ?? false,
          };
        } catch {
          return {
            id: site.id,
            name: site.label,
            location: "Location pending",
            areaHa: null,
            status: "Needs Review",
            valid: true,
            editable: site.editable ?? false,
          };
        }
      })
    );
    return summaries;
  },
};
 
function centroid(coords) {
  if (!coords || coords.length === 0) return [null, null];
  const lngs = coords.map((c) => c[0]);
  const lats = coords.map((c) => c[1]);
  return [lngs.reduce((a, b) => a + b, 0) / lngs.length, lats.reduce((a, b) => a + b, 0) / lats.length];
}

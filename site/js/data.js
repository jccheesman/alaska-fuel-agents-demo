// Loads every data file the site reads. All files are static JSON built by
// build/build_all.py from the harness repository at a pinned commit.
const FILES = {
  prov: 'data/provenance.json',
  hubs: 'data/hubs.json',
  facilities: 'data/facilities.json',
  corridors: 'data/corridors.geojson',
  geoms: 'data/route_geoms.json',
  reference: 'data/reference_routes.json',
  d2: 'data/disruption_d2.json',
  runs: 'data/agent_runs.json',
  results: 'data/study_results.json',
  text: 'data/text_bundle.json',
  lifecycle: 'data/lifecycle.json',
  land: 'data/land.geojson',
};

export async function loadAll(onProgress) {
  const out = {};
  const names = Object.keys(FILES);
  let done = 0;
  await Promise.all(names.map(async (name) => {
    // 'no-cache' revalidates with the server (GitHub Pages answers 304 when a
    // file is unchanged), so a republished data file is never masked by a
    // stale copy the way 'force-cache' would allow.
    const res = await fetch(FILES[name], { cache: 'no-cache' });
    if (!res.ok) throw new Error(`${FILES[name]}: HTTP ${res.status}`);
    out[name] = await res.json();
    done += 1;
    if (onProgress) onProgress(done, names.length, name);
  }));
  // handy indexes
  out.hubByPid = Object.fromEntries(out.hubs.hubs.map((h) => [h.pid, h]));
  out.facByPid = Object.fromEntries(out.facilities.facilities.map((f) => [f.pid, f]));
  out.reqByDest = Object.fromEntries(out.reference.requests.map((r) => [r.dest, r]));
  out.voidedEdges = new Set(out.d2.voided.edges);
  out.voidedFacilities = new Set(out.d2.voided.facilities);
  out.voidedCorridors = new Set(out.d2.voided.corridors);
  return out;
}

export const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export const MODES = ['road', 'barge', 'plane', 'ice_road', 'transfer'];
export const MODE_LABEL = { road: 'Road', barge: 'Barge', plane: 'Plane', ice_road: 'Ice road', transfer: 'Transfer' };

export function fmtUsd(v, d = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return '–';
  return `$${Number(v).toFixed(d)}`;
}
export function fmtKm(v) {
  if (v === null || v === undefined) return '–';
  return `${Math.round(v).toLocaleString()} km`;
}
export function fmtInt(v) {
  if (v === null || v === undefined) return '–';
  return Number(v).toLocaleString();
}
export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
export function monthSpan(ms) {
  if (!ms) return '–';
  if (ms.start === ms.end) return MONTHS[ms.start - 1];
  return `${MONTHS[ms.start - 1]}–${MONTHS[ms.end - 1]}`;
}

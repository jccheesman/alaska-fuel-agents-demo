import { loadAll } from './data.js';
import { createMap } from './map.js';
import { MapStates, STATES } from './states.js';
import { renderStart, renderParadigms, renderLifecycle, renderResults, renderAbout } from './text.js';

function setupTheme(onChange) {
  const root = document.documentElement;
  const btn = document.getElementById('theme-toggle');
  let saved = null;
  try { saved = localStorage.getItem('demo-theme'); } catch (e) { /* storage may be unavailable */ }
  if (saved === 'dark' || saved === 'light') root.dataset.theme = saved;
  const current = () => root.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  const label = () => { btn.textContent = current() === 'dark' ? 'Light theme' : 'Dark theme'; };
  label();
  btn.addEventListener('click', () => {
    const next = current() === 'dark' ? 'light' : 'dark';
    root.dataset.theme = next;
    try { localStorage.setItem('demo-theme', next); } catch (e) { /* ignore */ }
    label();
    onChange();
  });
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { label(); onChange(); });
}

async function main() {
  const status = document.getElementById('load-status');
  let DATA;
  try {
    DATA = await loadAll((done, total) => { status.textContent = `loading data ${done}/${total}`; });
  } catch (e) {
    status.textContent = `Could not load the data files (${e.message}). Serve the site over HTTP, e.g. python -m http.server from the site folder.`;
    status.classList.add('bad');
    return;
  }
  status.remove();
  window.DEMO = { DATA };

  renderStart(DATA);
  renderParadigms(DATA);
  renderLifecycle(DATA);
  renderResults(DATA);
  renderAbout(DATA);

  const mapApi = createMap('map', DATA);
  const S = new MapStates(DATA, mapApi, {
    controls: document.getElementById('map-controls'),
    panel: document.getElementById('map-panel'),
    legend: document.getElementById('map-legend'),
  });
  window.DEMO.states = S;
  document.querySelectorAll('[data-state-btn]').forEach((b) => b.addEventListener('click', () => {
    const state = b.dataset.stateBtn;
    const patch = { state };
    if (state === 'reassessment' && !STATES.includes(S.s.req) && S.s.req.startsWith('hub:')) patch.req = 'all';
    if (state !== 'reassessment' && S.s.req.startsWith('rt-')) patch.req = 'all';
    S.set(patch, true);
  }));
  document.querySelectorAll('[data-goto]').forEach((a) => a.addEventListener('click', (e) => {
    e.preventDefault();
    const [state, q] = a.dataset.goto.split('?');
    const patch = { state };
    if (q) for (const [k, v] of new URLSearchParams(q)) patch[k] = v;
    S.set(patch, true);
    document.getElementById('map-section').scrollIntoView({ behavior: 'smooth' });
  }));
  setupTheme(() => mapApi.ready(() => mapApi.retheme()));
  mapApi.ready(() => S.apply(true));
  if (location.hash.startsWith('#map')) document.getElementById('map-section').scrollIntoView();
}

main();

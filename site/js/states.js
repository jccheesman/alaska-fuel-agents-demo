// The map's state machine: four states, a month, an objective, a request, a
// topology and a checkpoint, all kept in the URL hash so a view can be linked.
import { MONTHS, MODES, MODE_LABEL, esc, fmtKm, fmtUsd, fmtInt, monthSpan } from './data.js';
import { boundsOf } from './map.js';
import { renderPanel } from './panels.js';

export const STATES = ['baseline', 'disruption', 'after', 'reassessment'];
const DEFAULTS = { state: 'baseline', month: 9, obj: 'cost', req: 'all', topo: 'lin', cp: 'revision', fac: '0', modes: 'all' };

// The default team shown on the fourth state is the run the blind judge
// scored highest; app.js sets it once the results are loaded.
export function setDefaultTopo(topo) { DEFAULTS.topo = topo; }
export function bestTopo(DATA) {
  const rows = DATA.results.rows.filter((r) => r.judge_mean != null && r.topology !== 'fresh');
  rows.sort((a, b) => b.judge_mean - a.judge_mean);
  return rows[0]?.topology || 'lin';
}

export function parseHash() {
  const h = location.hash.replace(/^#/, '');
  if (!h.startsWith('map')) return { ...DEFAULTS };
  const q = h.includes('?') ? h.slice(h.indexOf('?') + 1) : '';
  const s = { ...DEFAULTS };
  for (const [k, v] of new URLSearchParams(q)) if (k in DEFAULTS) s[k] = v;
  s.month = Math.min(12, Math.max(1, parseInt(s.month, 10) || 9));
  if (!STATES.includes(s.state)) s.state = 'baseline';
  return s;
}

export function writeHash(s) {
  const q = new URLSearchParams();
  for (const k of Object.keys(DEFAULTS)) if (String(s[k]) !== String(DEFAULTS[k])) q.set(k, s[k]);
  const str = q.toString();
  history.replaceState(null, '', `#map${str ? '?' + str : ''}`);
}

function geomFeatures(DATA, gid, props) {
  const g = DATA.geoms[gid];
  if (!g) return [];
  return g.parts.map(([mode, flat]) => {
    const coords = [];
    for (let i = 0; i < flat.length; i += 2) coords.push([flat[i], flat[i + 1]]);
    return { type: 'Feature', geometry: { type: 'LineString', coordinates: coords }, properties: { ...props, mode } };
  });
}

export class MapStates {
  constructor(DATA, mapApi, els) {
    this.DATA = DATA;
    this.map = mapApi;
    this.els = els;             // {controls, panel, legend}
    this.s = parseHash();
    this.lastFit = null;
    window.addEventListener('hashchange', () => {
      const next = parseHash();
      if (JSON.stringify(next) !== JSON.stringify(this.s)) { this.s = next; this.apply(true); }
    });
  }

  set(patch, refit = false) {
    Object.assign(this.s, patch);
    writeHash(this.s);
    this.apply(refit);
  }

  activeModes() {
    return this.s.modes === 'all' ? MODES : this.s.modes.split(',').filter((m) => MODES.includes(m));
  }

  // ---- features per state -------------------------------------------------
  // The month the routes are drawn for. States 2 and 3 are the D2 answer key,
  // which the harness computed for September (a fall storm); state 1 follows
  // the slider and uses the per-month cheapest paths.
  routeMonth() { return (this.s.state === 'disruption' || this.s.state === 'after') ? 9 : this.s.month; }

  // Per-month cheapest path to a hub (null when the hub is unreachable that month).
  monthlyRoute(dest) {
    const m = this.DATA.reference.monthly?.[String(this.routeMonth())];
    return m ? m[dest] : undefined;
  }

  referenceFeatures(phase, { tone = 'mode', ghost = false, onlySelected = false } = {}) {
    const { DATA, s } = this;
    const out = [];
    const month = this.routeMonth();
    const useMonthly = s.state === 'baseline' && s.obj === 'cost' && month !== 9 && DATA.reference.monthly;
    for (const req of DATA.reference.requests) {
      const selected = s.req === req.dest;
      if (s.req !== 'all' && !selected && onlySelected) continue;
      let o = req.objectives[s.obj][phase];
      if (useMonthly) {
        o = this.monthlyRoute(req.dest);
        if (!o) continue;                 // unreachable this month: nothing to draw
      }
      const affected = (req.objectives[s.obj].baseline.uses_closed_edges || []).length > 0;
      const t = tone === 'affected' ? (affected ? 'affected' : 'calm') : (s.req !== 'all' && !selected ? 'calm' : 'mode');
      out.push(...geomFeatures(DATA, o.geom, {
        title: `Anchorage → ${req.dest_label} (${phase === 'baseline' ? (useMonthly ? 'cheapest in ' + MONTHS[month - 1] : 'before the storm') : 'after reroute'}, ${s.obj === 'cost' ? 'cheapest' : 'shortest'})`,
        req: req.dest, cost: o.cost_per_gallon, km: o.length_km, n_edges: o.n_edges,
        selected, tone: t, ghost, affected: useMonthly ? false : affected,
        months: MONTHS[month - 1], voided: false, voided_hits: '', closed: false,
        note: !useMonthly && affected && phase === 'baseline' ? `crosses ${o.uses_closed_edges.join(', ')}` : '',
      }));
    }
    // draw the selected request last so it sits on top
    out.sort((a, b) => Number(a.properties.selected) - Number(b.properties.selected));
    return out;
  }

  agentFeatures() {
    const { DATA, s } = this;
    const run = DATA.runs.runs[s.topo];
    const ck = run?.checkpoints[s.cp];
    if (!ck) return [];
    const out = [];
    for (const r of ck.routes) {
      const selected = s.req === r.route_id;
      for (const leg of r.legs) {
        if (!leg.geom) continue;
        const dest = r.facilities_served?.length ? `${r.facilities_served.length} facilities` : 'no facilities listed';
        const active = (leg.month_list || []).includes(s.month);          // scheduled in the slider's month
        const g = DATA.geoms[leg.geom];
        const closed = active && g && !((g.months >> (s.month - 1)) & 1);  // scheduled, but its edges are shut that month
        out.push(...geomFeatures(DATA, leg.geom, {
          title: `${r.route_id} · leg ${leg.i + 1} (${run.label}, ${s.cp})`,
          req: r.route_id, cost: leg.cost_per_gallon, km: leg.length_km, n_edges: leg.n_edges,
          months: monthSpan(leg.months), selected, ghost: false,
          tone: (!active || (s.req !== 'all' && !selected)) ? 'calm' : 'mode',
          active, closed: Boolean(closed),
          voided: leg.voided_hits.length > 0, voided_hits: leg.voided_hits.join(', '),
          note: dest + (active ? '' : ` · not scheduled in ${MONTHS[s.month - 1]}`) + (closed ? ` · edges closed in ${MONTHS[s.month - 1]}` : ''),
        }));
      }
    }
    out.sort((a, b) => Number(a.properties.selected) - Number(b.properties.selected));
    return out;
  }

  facilityStates() {
    const { DATA, s } = this;
    if (s.state !== 'reassessment') return null;
    const ck = DATA.runs.runs[s.topo]?.checkpoints[s.cp];
    if (!ck) return null;
    const st = {};
    for (const f of ck.coverage.served) st[f] = 'served';
    for (const f of ck.coverage.unserved) st[f] = 'unserved';
    for (const r of ck.coverage.remote) st[typeof r === 'string' ? r : r.facility] = 'remote';
    return st;
  }

  // ---- apply ---------------------------------------------------------------
  apply(refit = false) {
    const { s, map } = this;
    map.ready(() => {
      map.setMonth(this.routeMonth(), this.activeModes());
      const dim = s.state === 'disruption' ? 0.22 : (s.state === 'baseline' ? 0.75 : 0.35);
      map.setCorridorOpacity(dim);
      map.showDisruption(s.state !== 'baseline');
      const facOn = s.fac === '1' || s.state === 'reassessment';
      map.showFacilities(facOn);
      map.setFacilityStates(this.facilityStates());

      let feats = [];
      if (s.state === 'baseline') feats = this.referenceFeatures('baseline');
      else if (s.state === 'disruption') feats = this.referenceFeatures('baseline', { tone: 'affected' });
      else if (s.state === 'after') {
        feats = [...this.referenceFeatures('baseline', { ghost: true, onlySelected: true }),
          ...this.referenceFeatures('post_closure')];
      } else feats = this.agentFeatures();
      map.setRoutes(feats);

      const key = `${s.state}|${s.req}|${s.topo}|${s.cp}`;
      if (refit || key !== this.lastFit) {
        this.lastFit = key;
        const sel = feats.filter((f) => f.properties.selected && !f.properties.ghost);
        const b = boundsOf(sel.length ? sel : feats.filter((f) => !f.properties.ghost));
        if (b && s.req !== 'all') map.fitTo(b, 60); else map.fit(s.state === 'reassessment' && s.topo === 'mass' ? 'alaska' : 'bering');
      }
    });
    this.renderControls();
    renderPanel(this.els.panel, this, feats => feats);
    this.renderLegend();
    document.querySelectorAll('[data-state-btn]').forEach((b) => b.classList.toggle('active', b.dataset.stateBtn === s.state));
  }

  renderControls() {
    const { s, DATA, els } = this;
    const pinned = s.state === 'disruption' || s.state === 'after';
    const reqOptions = s.state === 'reassessment'
      ? (DATA.runs.runs[s.topo]?.checkpoints[s.cp]?.routes || []).map((r) => [r.route_id, `${r.route_id} · ${r.legs.length} leg${r.legs.length > 1 ? 's' : ''}${r.legs.some((l) => l.voided_hits.length) ? ' ⚠' : ''}`])
      : DATA.reference.requests.map((r) => [r.dest, `${r.dest_label} (${r.dest.replace('hub:', '')})`]);
    const reqLabel = s.state === 'reassessment' ? 'Route' : 'Delivery';
    const best = bestTopo(DATA);
    const topoOpts = DATA.runs.order.map((t) => [t, DATA.runs.runs[t].label + (t === best ? ' · highest judge score' : '')]);
    els.controls.innerHTML = `
      <div class="ctl">
        <label for="ctl-month">Month <span class="ctl-val">${MONTHS[this.routeMonth() - 1]}</span></label>
        <input id="ctl-month" type="range" min="1" max="12" step="1" value="${this.routeMonth()}" aria-label="Month shown" ${pinned ? 'disabled' : ''}>
        <div class="ctl-hint">${{
          baseline: 'Corridors and the cheapest paths are recomputed for the month you choose (the harness router, cost objective).',
          disruption: 'Pinned to September: D2 is a fall storm and its answer key was computed for September.',
          after: 'Pinned to September: the reroute is the September answer key.',
          reassessment: 'Legs the agents scheduled in this month are drawn solid; the rest are faded.',
        }[s.state]}</div>
      </div>
      ${s.state !== 'reassessment' ? `
      <div class="ctl">
        <span class="ctl-label">Objective</span>
        <div class="seg" role="group" aria-label="Routing objective">
          <button type="button" data-obj="cost" class="${s.obj === 'cost' ? 'active' : ''}">Cheapest $/gal</button>
          <button type="button" data-obj="length" class="${s.obj === 'length' ? 'active' : ''}">Shortest km</button>
        </div>
      </div>` : `
      <div class="ctl">
        <label for="ctl-topo">Team</label>
        <select id="ctl-topo">${topoOpts.map(([v, l]) => `<option value="${v}" ${v === s.topo ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>
      </div>
      <div class="ctl">
        <span class="ctl-label">Checkpoint</span>
        <div class="seg" role="group" aria-label="Checkpoint">
          ${['plan', 'revision', 'reassessment'].map((c) => `<button type="button" data-cp="${c}" class="${s.cp === c ? 'active' : ''}" ${DATA.runs.runs[s.topo]?.checkpoints[c] ? '' : 'disabled'}>${c}</button>`).join('')}
        </div>
      </div>`}
      <div class="ctl">
        <label for="ctl-req">${reqLabel}</label>
        <select id="ctl-req"><option value="all">All</option>${reqOptions.map(([v, l]) => `<option value="${esc(v)}" ${v === s.req ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>
      </div>
      <div class="ctl ctl-row">
        <label class="chk"><input id="ctl-fac" type="checkbox" ${s.fac === '1' || s.state === 'reassessment' ? 'checked' : ''} ${s.state === 'reassessment' ? 'disabled' : ''}> Facilities</label>
        <div class="fit">
          <button type="button" data-fit="bering">Bering Straits</button>
          <button type="button" data-fit="nome">Nome</button>
          <button type="button" data-fit="alaska">Alaska</button>
        </div>
      </div>`;
    els.controls.querySelector('#ctl-month').addEventListener('input', (e) => this.set({ month: parseInt(e.target.value, 10) }));
    els.controls.querySelectorAll('[data-obj]').forEach((b) => b.addEventListener('click', () => this.set({ obj: b.dataset.obj })));
    els.controls.querySelectorAll('[data-cp]').forEach((b) => b.addEventListener('click', () => this.set({ cp: b.dataset.cp, req: 'all' }, true)));
    els.controls.querySelector('#ctl-topo')?.addEventListener('change', (e) => this.set({ topo: e.target.value, req: 'all' }, true));
    els.controls.querySelector('#ctl-req').addEventListener('change', (e) => this.set({ req: e.target.value }, true));
    els.controls.querySelector('#ctl-fac').addEventListener('change', (e) => this.set({ fac: e.target.checked ? '1' : '0' }));
    els.controls.querySelectorAll('[data-fit]').forEach((b) => b.addEventListener('click', () => this.map.fit(b.dataset.fit)));
  }

  renderLegend() {
    const { s } = this;
    const modes = this.activeModes();
    const modeItems = MODES.map((m) => `<button type="button" class="lg-mode ${modes.includes(m) ? '' : 'off'}" data-mode="${m}" aria-pressed="${modes.includes(m)}">
        <i class="sw sw-${m}"></i>${MODE_LABEL[m]}</button>`).join('');
    const extra = {
      baseline: '<span class="lg"><i class="sw sw-route"></i>cheapest path this month, colored by mode</span>',
      disruption: '<span class="lg"><i class="sw sw-voided"></i>voided by D2</span><span class="lg"><i class="sw sw-affected"></i>baseline route through a voided edge</span><span class="lg"><i class="sw sw-calm"></i>unaffected route</span>',
      after: '<span class="lg"><i class="sw sw-route"></i>rerouted (by mode)</span><span class="lg"><i class="sw sw-ghost"></i>old route</span><span class="lg"><i class="sw sw-voided"></i>voided by D2</span>',
      reassessment: '<span class="lg"><i class="sw sw-route"></i>agent leg scheduled this month</span><span class="lg"><i class="sw sw-calm"></i>leg scheduled in another month</span><span class="lg"><i class="sw sw-ring"></i>leg through a voided edge</span><span class="lg"><i class="sw sw-closed"></i>scheduled in a month its edges are closed</span><span class="lg"><i class="sw sw-served"></i>served</span><span class="lg"><i class="sw sw-unserved"></i>unserved</span><span class="lg"><i class="sw sw-remote"></i>remote</span>',
    }[s.state];
    this.els.legend.innerHTML = `<div class="lg-modes" role="group" aria-label="Modes shown (corridors)">${modeItems}</div><div class="lg-extra">${extra}<span class="lg"><i class="sw sw-transfer-pt"></i>transfer point</span><span class="lg"><i class="sw sw-hub"></i>hub · <b>●</b> Anchorage supplier</span></div>`;
    this.els.legend.querySelectorAll('[data-mode]').forEach((b) => b.addEventListener('click', () => {
      const cur = new Set(this.activeModes());
      if (cur.has(b.dataset.mode)) cur.delete(b.dataset.mode); else cur.add(b.dataset.mode);
      const list = MODES.filter((m) => cur.has(m));
      this.set({ modes: list.length === MODES.length ? 'all' : list.join(',') });
    }));
  }
}

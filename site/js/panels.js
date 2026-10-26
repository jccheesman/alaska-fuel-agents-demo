// The side panel beside the map: what the current state means, in plain words,
// with the numbers that back it.
import { MONTHS, MODE_LABEL, esc, fmtKm, fmtUsd, fmtInt, monthSpan } from './data.js';

const SHORT = { lin: 'lin', crew: 'crew', mass: 'mass', self: 'self', fresh: 'your run' };

function id(s) { return `<code>${esc(s)}</code>`; }

function carrier(DATA, gid) {
  const g = DATA.geoms[gid];
  if (!g) return '?';
  const m = g.modes;
  if (m.barge) return 'barge';
  if (m.ice_road) return 'ice road';
  if (m.plane) return 'plane';
  return 'road';
}

function baselinePanel(S) {
  const { DATA, s } = S;
  const ref = DATA.reference;
  const sel = s.req !== 'all' ? DATA.reqByDest[s.req] : null;
  const byMonth = DATA.prov.passable_edges_by_month;
  const m = s.month;
  const mon = MONTHS[m - 1];
  const seasonal = `In ${mon}: ${fmtInt(byMonth.barge[m - 1])} barge edges, ${fmtInt(byMonth.ice_road[m - 1])} ice-road edges, ${fmtInt(byMonth.road[m - 1])} road edges are passable.`;
  const monthly = s.obj === 'cost' ? ref.monthly?.[String(m)] : null;
  // per-month tally: how the cheapest deliveries travel this month
  let tally = '';
  if (monthly) {
    const counts = { barge: 0, 'ice road': 0, plane: 0, road: 0 };
    let reachable = 0;
    const unreachable = [];
    for (const r of ref.requests) {
      const o = monthly[r.dest];
      if (!o) { unreachable.push(r.dest_label); continue; }
      reachable += 1; counts[carrier(DATA, o.geom)] += 1;
    }
    const parts = Object.entries(counts).filter(([, n]) => n).map(([k, n]) => `${n} by ${k}`).join(', ');
    tally = `<p><b>${mon}:</b> ${reachable} of ${ref.n_requests} hubs are reachable from Anchorage; the cheapest delivery goes ${parts}.` +
      `${unreachable.length ? ` Unreachable this month: ${unreachable.map(esc).join(', ')}.` : ''}</p>`;
  }
  let detail = '';
  if (sel) {
    const o = monthly ? monthly[sel.dest] : sel.objectives[s.obj].baseline;
    if (!o) {
      detail = `<p class="callout warn"><b>${esc(sel.dest_label)}</b> cannot be reached from Anchorage in ${mon}: every path needs a corridor that is closed that month.</p>`;
    } else {
      detail = `<div class="kv"><div><span>Delivery</span><b>Anchorage → ${esc(sel.dest_label)}</b> in ${mon}</div>
        <div><span>Hub</span>${id(sel.dest)}</div>
        <div><span>${s.obj === 'cost' ? 'Cost' : 'Cost (shortest path)'}</span><b>${fmtUsd(o.cost_per_gallon, 3)}/gal</b></div>
        <div><span>Length</span>${fmtKm(o.length_km)} · ${fmtInt(o.n_edges)} edges</div>
        <div><span>Modes</span>${modesOf(DATA, o.geom)}</div>
        ${o.last_edge ? `<div><span>Last edge</span>${id(o.last_edge)}</div>` : ''}</div>`;
      if (monthly && m !== 9) {
        const sep = sel.objectives.cost.baseline;
        detail += `<p class="muted small">September, for comparison: ${fmtUsd(sep.cost_per_gallon, 3)}/gal by ${esc(carrier(DATA, sep.geom))}, ${fmtKm(sep.length_km)}.</p>`;
      }
    }
  } else {
    const costs = ref.requests.map((r) => (monthly ? monthly[r.dest] : r.objectives[s.obj].baseline)).filter(Boolean).map((o) => o.cost_per_gallon);
    detail = `<div class="kv"><div><span>Deliveries</span><b>${ref.n_requests}</b> hubs from Anchorage</div>
      <div><span>$/gal range</span>${fmtUsd(Math.min(...costs), 2)} – ${fmtUsd(Math.max(...costs), 2)}</div>
      <div><span>Scope</span>136 facilities in the Bering Straits region</div></div>`;
  }
  const routesNote = monthly
    ? `<p>The colored routes are the <b>cheapest path for ${mon}</b> from the Anchorage supplier to each hub, computed with the harness's own router over that month's passable edges. In summer the cheapest Nome delivery goes by road to a dock, transfers to a barge and sails around the coast; once the barge corridors freeze, the router flies or stays on the road.</p>`
    : `<p>The colored routes are the <b>shortest paths</b> (the diagnostic objective), computed for September. Switch to "Cheapest $/gal" to see the delivery that minimises cost, month by month.</p>`;
  return `<h3>The network the agents can query</h3>
    <p>Every line is a <b>corridor</b>: a run of edges between two hubs with one mode. Barge corridors open in open water, ice roads only January to March, roads and air all year. The straight-looking lines are drawn from node to node; the real geometry lives in shapefiles the agents never see either.</p>
    <p class="muted">${seasonal}</p>
    ${routesNote}
    ${tally}
    ${detail}
    <p class="hint">Hover a corridor, hub or route for its ids. Agents never see a map; they see these ids and the numbers behind them.</p>`;
}

function modesOf(DATA, gid) {
  const g = DATA.geoms[gid];
  if (!g) return '–';
  return Object.entries(g.modes).sort((a, b) => b[1] - a[1]).map(([m, n]) => `${MODE_LABEL[m]} (${n})`).join(', ');
}

function disruptionPanel(S) {
  const { DATA, s } = S;
  const d = DATA.d2;
  const affected = DATA.reference.requests.filter((r) => r.objectives[s.obj].baseline.uses_closed_edges?.length);
  const sel = s.req !== 'all' ? DATA.reqByDest[s.req] : null;
  const selNote = sel ? (sel.objectives[s.obj].baseline.uses_closed_edges?.length
    ? `<p class="callout bad">The ${s.obj === 'cost' ? 'cheapest' : 'shortest'} route to <b>${esc(sel.dest_label)}</b> runs through ${sel.objectives[s.obj].baseline.uses_closed_edges.map(id).join(', ')}, which the notice voids. It has to be re-planned.</p>`
    : `<p class="callout ok">The ${s.obj === 'cost' ? 'cheapest' : 'shortest'} route to <b>${esc(sel.dest_label)}</b> never touched the Nome dock. It is a preserved out: unaffected, and a claim saying so is worth as much as a reroute.</p>`) : '';
  return `<h3>The storm hits: what breaks</h3>
    <p>Partway through a run the harness delivers one <b>operator notice</b> and grants layer L2. Nothing in the database changes; the disruption is a <i>WHERE clause</i>, a set of ids a route may no longer use.</p>
    <details class="notice"><summary>Read the notice the agents received</summary><div class="notice-body">${d.notice_html}</div></details>
    <div class="kv">
      <div><span>Voided</span><b>${d.counts.total_voided}</b> elements</div>
      <div><span>Hub</span>${id('hub:h000493')} Nome</div>
      <div><span>Edges</span>${d.voided.edges.map(id).join(' ')} <span class="muted">(the port's transfer edges)</span></div>
      <div><span>Corridors</span>${d.voided.corridors.map(id).join(' ')}</div>
      <div><span>Facilities</span>${d.voided.facilities.length}: one in Nome, the barge facilities of White Mountain and Golovin</div>
      <div><span>Symbolic</span>${d.voided.symbolic.map(id).join(' ')}</div>
    </div>
    ${selNote}
    <p><b>${affected.length} of ${DATA.reference.n_requests}</b> ${s.obj === 'cost' ? 'cheapest' : 'shortest'} baseline routes cross a voided edge (drawn red); the others are gray. ${s.obj === 'length' ? 'The shortest paths fly, so none of them touched the dock.' : 'Air and direct ocean barge stay open on purpose: a team that voids them too loses precision.'}</p>
    <p class="hint">The impact tool answers only about ids a team asks about. Reading the notice tells you the whole port is closed to fuel transfer; the binding below says how the harness turned those words into ids.</p>
    <details><summary>How words became ids (declared approximations)</summary><ul class="small">${d.declared_approximations.map((a) => `<li>${esc(a)}</li>`).join('')}</ul></details>`;
}

function afterPanel(S) {
  const { DATA, s } = S;
  const reqs = DATA.reference.requests;
  const sel = s.req !== 'all' ? DATA.reqByDest[s.req] : null;
  const rows = (sel ? [sel] : reqs).map((r) => {
    const o = r.objectives[s.obj];
    const aff = o.outcome !== 'unaffected';
    return `<tr class="${aff ? 'aff' : ''}"><td>${esc(r.dest_label)}</td><td class="num">${fmtUsd(o.baseline.cost_per_gallon, 2)}</td><td class="num">${aff ? fmtUsd(o.post_closure.cost_per_gallon, 2) : '<span class="muted">same</span>'}</td><td class="num">${aff ? `+${fmtKm(o.delta_km)}` : '–'}</td></tr>`;
  }).join('');
  const nome = DATA.reqByDest['hub:h000493'].objectives.cost;
  return `<h3>After the disruption: the reference reroute</h3>
    <p>The same router, with the three voided edges removed from the month's graph. Solid lines are the new routes; a dashed gray line is the old route of the delivery you selected.</p>
    <p>For Nome the cheapest delivery rises from <b>${fmtUsd(nome.baseline.cost_per_gallon, 3)}</b> to <b>${fmtUsd(nome.post_closure.cost_per_gallon, 3)}</b> per gallon (+${fmtKm(nome.delta_km)}): the barge now lands at a different dock and the fuel finishes by road. ${DATA.reference.n_affected_cost} of 20 cheapest routes change; the 8 that never used the dock stay as they were.</p>
    <div class="tbl"><table><thead><tr><th>Hub</th><th class="num">before</th><th class="num">after</th><th class="num">extra</th></tr></thead><tbody>${rows}</tbody></table></div>
    <p class="hint">This is the <b>answer key</b> the scorers hold, not an agent's work. The next state shows what the agent teams actually did.</p>`;
}

function reassessmentPanel(S) {
  const { DATA, s } = S;
  const run = DATA.runs.runs[s.topo];
  const ck = run?.checkpoints[s.cp];
  if (!ck) return `<h3>No ${esc(s.cp)} report</h3><p>This run saved no report at this checkpoint.</p>`;
  const cov = ck.coverage;
  const total = DATA.runs.scope_facilities;
  const served = cov.served.length, unserved = cov.unserved.length, remote = cov.remote.length;
  const pct = (n) => `${Math.round(100 * n / total)}%`;
  const sel = s.req !== 'all' ? ck.routes.find((r) => r.route_id === s.req) : null;
  const caveats = (ck.caveats || []).map((c) => `<li>${esc(c)}</li>`).join('');
  const claims = ck.claims.slice(0, 40).map((c) => `<li><span class="tag tag-${esc(c.class)}">${esc(c.class)}</span> <span class="tag">${esc(c.section)}</span> ${esc(c.text)}${c.cites?.length ? ` <span class="muted">cites ${c.cites.map(esc).join(', ')}</span>` : ''}</li>`).join('');
  const log = ck.revision_log.length ? ck.revision_log.map((l) => `<li><b>${esc(l.action)}</b> ${esc(l.claim_id)}${l.rationale_claims?.length ? ` <span class="muted">(because ${l.rationale_claims.map(esc).join(', ')})</span>` : ''}</li>`).join('') : '<li class="muted">empty log</li>';
  const routeRows = (sel ? [sel] : ck.routes).map((r) => `<tr class="${r.legs.some((l) => l.voided_hits.length) ? 'aff' : ''}"><td>${esc(r.route_id)}</td><td>${r.legs.map((l) => `<i class="sw sw-${l.mode}" title="${MODE_LABEL[l.mode]}"></i>`).join('')}</td><td>${esc([...new Set(r.legs.map((l) => monthSpan(l.months)))].join(', '))}</td><td class="num">${fmtUsd(r.cost_per_gallon, 2)}</td><td class="num">${r.facilities_served.length}</td><td>${r.legs.some((l) => l.voided_hits.length) ? '<span class="bad">voided edge</span>' : ''}</td></tr>`).join('');
  const judge = run.judge ? `${run.judge[s.cp] ?? '–'} / 4 (run mean ${run.judge.run_mean ?? '–'})` : '–';
  // seasonality of what the agents scheduled, for the slider's month
  const mon = MONTHS[s.month - 1];
  let scheduled = 0, closed = 0;
  for (const r of ck.routes) for (const l of r.legs) {
    if (!(l.month_list || []).includes(s.month)) continue;
    scheduled += 1;
    const g = l.geom ? DATA.geoms[l.geom] : null;
    if (g && !((g.months >> (s.month - 1)) & 1)) closed += 1;
  }
  const seasonLine = `<div><span>In ${esc(mon)}</span>${scheduled} leg${scheduled === 1 ? '' : 's'} scheduled` +
    (closed ? `, <b class="warn">${closed} on edges that are not passable in ${esc(mon)}</b>` : (scheduled ? ', all on passable edges' : '')) + `</div>`;
  return `<h3>${esc(run.label)} · ${esc(s.cp)} report</h3>
    <p class="verbatim">AI-generated report (${esc(run.model)}), shown exactly as saved on ${s.cp === 'plan' ? 'the first' : s.cp === 'revision' ? 'the second' : 'the third'} checkpoint of ${esc(run.run_id)}. Mistakes are part of the record.</p>
    <div class="kv">
      <div><span>Routes</span><b>${ck.n_routes}</b> · ${ck.n_legs} legs · months ${ck.months_with_service.map((m) => MONTHS[m - 1]).join(', ') || '–'}</div>
      <div><span>Legs through voided edges</span><b class="${ck.routes_through_voided ? 'bad' : 'ok'}">${ck.routes_through_voided}</b>${s.cp === 'plan' ? ' <span class="muted">(notice not yet delivered)</span>' : ''}</div>
      ${seasonLine}
      <div><span>Claims</span>${ck.claims.length} · judge ${judge}</div>
      <div><span>Run</span>${fmtUsd(run.usd)} · ${esc(run.wall)} · ${fmtInt(run.llm_calls)} model calls</div>
    </div>
    <div class="cov" role="img" aria-label="Coverage of ${total} facilities: ${served} served, ${unserved} unserved, ${remote} remote">
      <div class="cov-bar"><span class="c-served" style="width:${pct(served)}"></span><span class="c-unserved" style="width:${pct(unserved)}"></span><span class="c-remote" style="width:${pct(remote)}"></span></div>
      <div class="cov-key"><span><i class="sw sw-served"></i>served ${served}</span><span><i class="sw sw-unserved"></i>unserved ${unserved}</span><span><i class="sw sw-remote"></i>remote ${remote}</span><span class="muted">of ${total}</span></div>
    </div>
    ${caveats ? `<div class="callout warn"><b>What the study's own read-out says about this report</b><ul>${caveats}</ul></div>` : ''}
    <div class="tbl"><table><thead><tr><th>Route</th><th>Legs</th><th>Months</th><th class="num">$/gal</th><th class="num">fac.</th><th></th></tr></thead><tbody>${routeRows}</tbody></table></div>
    <details><summary>Summary written by the agents</summary><blockquote class="small">${esc(ck.summary) || '<i>empty</i>'}</blockquote></details>
    <details><summary>Claims (${ck.claims.length}${ck.claims.length > 40 ? ', first 40 shown' : ''})</summary><ul class="small claims">${claims || '<li class="muted">none</li>'}</ul></details>
    <details><summary>Revision log (${ck.revision_log.length})</summary><ul class="small">${log}</ul></details>
    ${run.l3_documents?.length && s.cp === 'reassessment' ? `<details><summary>Documents the harness pointed to at the unlock</summary><ul class="small">${run.l3_documents.map((d) => `<li>${esc(d)}</li>`).join('')}</ul><p class="muted small">Titles only; the passages themselves are third-party documents and are not reproduced here.</p></details>` : ''}
    ${run.overview_png ? `<details><summary>The harness's own rendered map of this run's revision</summary><img src="${esc(run.overview_png)}" alt="Overview map rendered by the harness for the revision report of ${esc(run.run_id)}" loading="lazy"></details>` : ''}`;
}

export function renderPanel(el, S) {
  const fn = { baseline: baselinePanel, disruption: disruptionPanel, after: afterPanel, reassessment: reassessmentPanel }[S.s.state];
  el.innerHTML = fn(S);
  el.scrollTop = 0;
}

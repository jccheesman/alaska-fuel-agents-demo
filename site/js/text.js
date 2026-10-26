// Fills the reading sections from text_bundle.json, lifecycle.json and
// study_results.json. All harness text is rendered as the harness wrote it.
import { esc, fmtUsd, fmtInt } from './data.js';

const PARADIGM_BLURB = {
  lin: { name: 'lin', title: 'A fixed chain', one: 'Three stages in a fixed order: survey the network, draft the routes, write and submit the report. Each stage reads the previous one\'s output. This is the statistical reference level.', how: 'Direct model calls; tools called in-process.' },
  crew: { name: 'crew', title: 'Named roles', one: 'Five CrewAI roles in sequence: Network Surveyor, Context Researcher, Route Planner, Contrarian, Report Writer. Only the Writer can submit.', how: 'CrewAI; every role reaches the tools through the MCP server, one server process per role.' },
  mass: { name: 'mass', title: 'Peers who vote', one: 'Three identical peers each build a full candidate report in MassGen and vote. A script with no model in it submits the winner unchanged.', how: 'MassGen; tools through a thin shim because MassGen renames MCP tools.' },
  self: { name: 'self', title: 'A team that designs itself', one: 'A planner model designs its own team at run time: positions, briefs, who talks to whom, who submits. The harness checks the briefs for banned wording and loops, then runs the positions in dependency order. The planner may rebuild the team at each later checkpoint.', how: 'Direct model calls; the only topology whose shape is a per-run outcome.' },
};

function h(strings, ...vals) { return strings.map((s, i) => s + (vals[i] ?? '')).join(''); }

export function renderStart(DATA) {
  const t = DATA.text;
  // skills
  document.getElementById('skills-grid').innerHTML = t.skills.map((s) => `
    <details class="card skill">
      <summary><span class="card-title">${esc(s.name.replace(/_/g, ' '))}</span><span class="pill">${esc(s.layer)} · ${esc(s.stages)}</span>
        <span class="card-desc">${esc(s.description)}</span>
        <span class="tools-line">tools: ${s.tools.map((x) => `<code>${esc(x)}</code>`).join(' ')}</span></summary>
      <div class="md">${s.html}</div>
      <p class="src">${esc(s.path)}</p>
    </details>`).join('');
  // tools
  const byName = Object.fromEntries(t.tools.tools.map((x) => [x.name, x]));
  document.getElementById('tools-groups').innerHTML = Object.entries(t.tools.groups).map(([g, names]) => `
    <div class="tool-group"><h4>${esc(g)} <span class="muted">(${names.length})</span></h4>
      <ul class="tool-list">${names.map((n) => { const x = byName[n]; return `<li><details><summary><code>${esc(n)}</code>${x.terminal ? ' <span class="pill">ends the checkpoint</span>' : ''}</summary><p>${esc(x.purpose)}</p><p class="src">${esc(x.module)}</p></details></li>`; }).join('')}</ul></div>`).join('');
  document.getElementById('tools-count').textContent = t.tools.n_tools;
  // mcp
  document.getElementById('mcp-doc').textContent = t.mcp.docstring;
  document.getElementById('mcp-name').textContent = t.mcp.server_name || 'alaska-fuel-harness';
  // okf
  const okf = t.okf;
  document.getElementById('okf-kinds').innerHTML = Object.entries(okf.kinds).map(([k, n]) => `<span class="pill">${esc(k)} ${n}</span>`).join(' ');
  const pageOrder = ['start', 'ontology', 'region:bering-straits', 'hub:h000493', 'corridor:c004896', 'month:09', 'disruption:D2'];
  const tabs = document.getElementById('okf-tabs');
  const body = document.getElementById('okf-page');
  const show = (key) => {
    const p = okf.pages[key];
    tabs.querySelectorAll('button').forEach((b) => b.classList.toggle('active', b.dataset.key === key));
    body.innerHTML = `<div class="okf-head"><span class="pill">${esc(p.kind)} · ${esc(p.layer)}</span> <code>${esc(p.id)}</code> · ${p.n_links} typed links ${Object.entries(p.link_rels).map(([r, n]) => `<span class="pill soft">${esc(r)} ${n}</span>`).join(' ')}</div><div class="md okf-md">${p.html}</div><p class="src">${esc(p.path)} · built_from ${esc(p.built_from)}</p>`;
  };
  tabs.innerHTML = pageOrder.filter((k) => okf.pages[k]).map((k) => `<button type="button" data-key="${esc(k)}">${esc(okf.pages[k].title || k)}</button>`).join('');
  tabs.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => show(b.dataset.key)));
  show('hub:h000493');
  // glossary
  document.getElementById('glossary').innerHTML = t.glossary.map((g) => `<div class="gl"><dt>${esc(g.term)}</dt><dd>${esc(g.meaning)}</dd></div>`).join('');
  // data guide
  document.getElementById('data-guide').innerHTML = t.data_guide_html;
}

export function renderParadigms(DATA) {
  const t = DATA.text;
  const rows = Object.fromEntries(DATA.results.rows.map((r) => [r.topology, r]));
  document.getElementById('paradigm-grid').innerHTML = ['lin', 'crew', 'mass', 'self'].map((k) => {
    const b = PARADIGM_BLURB[k];
    const r = rows[k];
    const pos = t.adapters.rows[k];
    return `<article class="card topo topo-${k}">
      <header><code class="topo-code">${k}</code><h3>${esc(b.title)}</h3></header>
      <p>${esc(b.one)}</p>
      <p class="muted small">${esc(b.how)}</p>
      <details><summary>The only text that differs between the four: the "Position" paragraph</summary><div class="md position">${pos.position_html}</div><p class="src">${esc(pos.path)}</p></details>
      ${r ? `<dl class="mini"><div><dt>wall</dt><dd>${esc(r.wall)}</dd></div><div><dt>cost</dt><dd>${fmtUsd(r.usd)}</dd></div><div><dt>model calls</dt><dd>${fmtInt(r.llm_calls)}</dd></div><div><dt>judge</dt><dd>${r.judge_mean ?? '–'} / 4</dd></div></dl>` : ''}
    </article>`;
  }).join('');
  document.getElementById('spine').innerHTML = t.adapters.spine_html;
}

export function renderLifecycle(DATA) {
  const steps = DATA.lifecycle.steps;
  const d = DATA.text.deliveries;
  const el = document.getElementById('lifecycle');
  el.innerHTML = steps.map((s, i) => `
    <li class="step ${s.layers.length ? 'has-layers' : ''}">
      <div class="step-head"><span class="step-n">${i}</span><h3>${esc(s.title)}</h3>
        <span class="layers">${s.layers.map((l) => `<span class="pill layer-${l}">${l}</span>`).join('')}</span></div>
      <p>${esc(s.plain)}</p>
      <div class="step-meta">
        ${s.tools.length ? `<div><span class="k">tools</span>${s.tools.map((x) => `<code>${esc(x)}</code>`).join(' ')}</div>` : ''}
        ${s.skill ? `<div><span class="k">skill</span><code>${esc(s.skill)}</code></div>` : ''}
        ${s.artifacts.length ? `<div><span class="k">leaves behind</span>${s.artifacts.map((x) => `<code>${esc(x)}</code>`).join(' ')}</div>` : ''}
      </div>
      ${deliveryFor(s.id, d)}
    </li>`).join('');
}

function deliveryFor(id, d) {
  const key = { provision: 'scenario_task_delivery', disruption: 'disruption_delivery', l3: 'socioeconomic_unlock_delivery' }[id];
  if (!key || !d[key]) return '';
  return `<details class="delivery"><summary>The exact words the harness delivers at this step</summary><div class="md">${d[key].html}</div><p class="src">${esc(d[key].path)} · <b>{payload}</b> is where the task specification, the notice or the pushed passages go.</p></details>`;
}

export function renderResults(DATA) {
  const r = DATA.results;
  document.getElementById('results-table').innerHTML = `
    <thead><tr><th>team</th><th>routes<br><span class="muted">plan → rev → reass</span></th><th>claims</th><th>months served</th><th>served / unserved / remote</th><th>legs on voided edges<br><span class="muted">after the notice</span></th><th>sourced share</th><th>citation faith</th><th>cost</th><th>wall</th><th>judge<br><span class="muted">mean / 4</span></th></tr></thead>
    <tbody>${r.rows.map((x) => `<tr><td><code>${esc(x.topology)}</code></td><td>${esc(x.routes)}</td><td>${esc(x.claims)}</td><td>${esc(x.months)}</td><td>${esc(x.served_unserved_remote)}</td><td class="${x.legs_through_voided_after_notice ? 'bad' : 'ok'}">${x.legs_through_voided_after_notice ?? '–'}</td><td>${x.sourced_share ?? '–'}</td><td>${x.citation_faith ?? '–'}</td><td>${fmtUsd(x.usd)}</td><td>${esc(x.wall)}</td><td><b>${x.judge_mean ?? '–'}</b> <span class="muted">(${x.judge.plan ?? '–'} · ${x.judge.revision ?? '–'} · ${x.judge.reassessment ?? '–'})</span></td></tr>`).join('')}</tbody>`;
  document.getElementById('arm-notes').innerHTML = r.arm_notes.map((n) => `<li>${esc(n)}</li>`).join('');
  document.getElementById('arm-name').textContent = r.arm;
  document.getElementById('overview-pngs').innerHTML = DATA.runs.order.filter((t) => DATA.runs.runs[t].overview_png).map((t) => {
    const run = DATA.runs.runs[t];
    return `<figure><img src="${esc(run.overview_png)}" alt="Revision overview map for ${esc(run.label)}" loading="lazy"><figcaption><code>${esc(t)}</code> · ${esc(run.run_id)} · the harness's own rendering of the revision report (voided elements in red)</figcaption></figure>`;
  }).join('');
}

export function renderAbout(DATA) {
  const p = DATA.prov;
  document.getElementById('prov-commit').textContent = p.harness_commit;
  document.getElementById('prov-branch').textContent = p.harness_branch;
  document.getElementById('prov-db').textContent = p.db_sha256;
  document.getElementById('prov-built').textContent = p.built_at;
  document.getElementById('prov-counts').innerHTML = Object.entries(p.counts).map(([k, v]) => `<span class="pill">${esc(k.replace('_', ' '))} ${fmtInt(v)}</span>`).join(' ');
  document.getElementById('key-terms').innerHTML = DATA.text.key_terms.map((g) => `<div class="gl"><dt>${esc(g.term)}</dt><dd>${esc(g.meaning)}</dd></div>`).join('');
}

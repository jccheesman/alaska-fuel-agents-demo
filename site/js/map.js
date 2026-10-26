// The map: MapLibre GL on a blank style with a bundled Natural Earth coastline,
// so the page makes no request to any tile server and needs no key.
import { MODE_LABEL, MONTHS, esc, fmtKm, fmtUsd } from './data.js';

const ALASKA = [[-172, 53.5], [-129.5, 71.6]];
const BERING = [[-171.5, 61.2], [-146.5, 67.2]];
const NOME = [[-168.5, 63.2], [-160.5, 65.6]];

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function modeColors() {
  return {
    road: cssVar('--mode-road'), barge: cssVar('--mode-barge'), plane: cssVar('--mode-plane'),
    ice_road: cssVar('--mode-ice'), transfer: cssVar('--mode-transfer'),
    voided: cssVar('--voided'), warning: cssVar('--warning'),
  };
}

function modeMatch(colors, fallback) {
  return ['match', ['get', 'mode'],
    'road', colors.road, 'barge', colors.barge, 'plane', colors.plane,
    'ice_road', colors.ice_road, 'transfer', colors.transfer, fallback];
}

export function createMap(container, DATA) {
  const colors = modeColors();
  const map = new maplibregl.Map({
    container,
    style: {
      version: 8,
      sources: {},
      layers: [{ id: 'bg', type: 'background', paint: { 'background-color': cssVar('--map-sea') } }],
    },
    bounds: BERING,
    fitBoundsOptions: { padding: 24 },
    attributionControl: false,
    maxBounds: [[-215, 40], [-110, 76]],
    minZoom: 2.3,
    maxZoom: 12,
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-left');
  map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left');
  map.addControl(new maplibregl.AttributionControl({
    compact: true,
    customAttribution: 'Coastline: Natural Earth (public domain). Network: alaska-fuel-spatial-network. MapLibre GL JS.',
  }), 'bottom-right');

  const hubFeatures = {
    type: 'FeatureCollection',
    features: DATA.hubs.hubs.map((h) => ({
      type: 'Feature', geometry: { type: 'Point', coordinates: [h.lon, h.lat] },
      properties: { pid: h.pid, name: h.scenario?.label || h.community || h.name, role: h.role || 'other',
        region: h.region, type: h.hub_type, deliv: h.deliv_meth, cap: h.capacity_gal,
        facilities: h.mapped_facilities, voided: h.voided },
    })),
  };
  const facFeatures = {
    type: 'FeatureCollection',
    features: DATA.facilities.facilities.map((f) => ({
      type: 'Feature', geometry: { type: 'Point', coordinates: [f.lon, f.lat] },
      properties: { pid: f.pid, community: f.community, m1: f.method_1, m2: f.method_2,
        hub: f.hub_pid, last_mile: f.last_mile, voided: f.voided, state: 'none' },
    })),
  };
  const voidedEdgeFeatures = {
    type: 'FeatureCollection',
    features: Object.entries(DATA.d2.edge_geoms).map(([pid, coords]) => ({
      type: 'Feature', geometry: { type: 'LineString', coordinates: coords },
      properties: { pid, mode: DATA.d2.edge_info[pid]?.mode, km: (DATA.d2.edge_info[pid]?.length_m || 0) / 1000 },
    })),
  };
  const voidedEdgePoints = {
    type: 'FeatureCollection',
    features: voidedEdgeFeatures.features.map((f) => ({
      type: 'Feature', properties: f.properties,
      geometry: { type: 'Point', coordinates: f.geometry.coordinates[Math.floor(f.geometry.coordinates.length / 2)] },
    })),
  };
  const nomePoint = { type: 'FeatureCollection', features: [{ type: 'Feature', properties: { pid: 'hub:h000493' },
    geometry: { type: 'Point', coordinates: [DATA.d2.anchor.lon, DATA.d2.anchor.lat] } }] };

  const empty = { type: 'FeatureCollection', features: [] };
  let isReady = false;
  const markers = [];
  let hoverCb = null;
  const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, maxWidth: '320px', offset: 8 });

  function paintTokens() {
    const c = modeColors();
    map.setPaintProperty('bg', 'background-color', cssVar('--map-sea'));
    map.setPaintProperty('land', 'fill-color', cssVar('--map-land'));
    map.setPaintProperty('lakes', 'fill-color', cssVar('--map-sea'));
    map.setPaintProperty('alaska', 'line-color', cssVar('--map-border'));
    map.setPaintProperty('corridors', 'line-color', modeMatch(c, cssVar('--ink-3')));
    map.setPaintProperty('hubs-other', 'circle-color', cssVar('--ink-3'));
    map.setPaintProperty('hubs-other', 'circle-stroke-color', cssVar('--map-sea'));
    map.setPaintProperty('hubs-main', 'circle-stroke-color', cssVar('--surface'));
    map.setPaintProperty('hubs-main', 'circle-color', ['case', ['==', ['get', 'role'], 'origin'], cssVar('--accent'), cssVar('--ink')]);
    map.setPaintProperty('facilities', 'circle-color', ['case', ['==', ['get', 'state'], 'served'], c.plane,
      ['==', ['get', 'state'], 'unserved'], c.warning, ['==', ['get', 'state'], 'remote'], c.ice_road, cssVar('--ink-3')]);
    map.setPaintProperty('facilities', 'circle-stroke-color', cssVar('--surface'));
    map.setPaintProperty('routes-casing', 'line-color', cssVar('--surface'));
    map.setPaintProperty('routes', 'line-color', routeColor(c));
    map.setPaintProperty('routes-ghost', 'line-color', cssVar('--ink-3'));
    map.setPaintProperty('routes-transfer', 'circle-color', c.transfer);
    map.setPaintProperty('routes-transfer', 'circle-stroke-color', cssVar('--surface'));
    for (const id of ['voided-edges', 'voided-corridors']) map.setPaintProperty(id, 'line-color', c.voided);
    map.setPaintProperty('routes-closed-ring', 'line-color', c.warning);
    map.setPaintProperty('voided-edge-points', 'circle-color', c.voided);
    map.setPaintProperty('voided-edge-points', 'circle-stroke-color', cssVar('--surface'));
    map.setPaintProperty('voided-facilities', 'circle-color', c.voided);
    map.setPaintProperty('voided-facilities', 'circle-stroke-color', cssVar('--surface'));
    map.setPaintProperty('nome-halo', 'circle-color', c.voided);
    map.setPaintProperty('nome-halo', 'circle-stroke-color', c.voided);
  }

  function routeColor(c) {
    return ['case',
      ['==', ['get', 'tone'], 'affected'], c.voided,
      ['==', ['get', 'tone'], 'calm'], cssVar('--ink-3'),
      modeMatch(c, cssVar('--ink'))];
  }

  map.on('load', () => {
    map.addSource('land', { type: 'geojson', data: DATA.land });
    map.addSource('corridors', { type: 'geojson', data: DATA.corridors });
    map.addSource('hubs', { type: 'geojson', data: hubFeatures });
    map.addSource('facilities', { type: 'geojson', data: facFeatures });
    map.addSource('routes', { type: 'geojson', data: empty, lineMetrics: false });
    map.addSource('routes-transfer', { type: 'geojson', data: empty });
    map.addSource('voided-edges', { type: 'geojson', data: voidedEdgeFeatures });
    map.addSource('voided-edge-points', { type: 'geojson', data: voidedEdgePoints });
    map.addSource('nome', { type: 'geojson', data: nomePoint });

    map.addLayer({ id: 'land', type: 'fill', source: 'land', filter: ['==', ['get', 'kind'], 'land'], paint: { 'fill-color': '#fff' } });
    map.addLayer({ id: 'lakes', type: 'fill', source: 'land', filter: ['==', ['get', 'kind'], 'lake'], paint: { 'fill-color': '#fff' } });
    map.addLayer({ id: 'alaska', type: 'line', source: 'land', filter: ['==', ['get', 'kind'], 'alaska'],
      paint: { 'line-color': '#999', 'line-width': 0.8, 'line-dasharray': [3, 2] } });
    map.addLayer({ id: 'corridors', type: 'line', source: 'corridors',
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': '#888', 'line-width': ['interpolate', ['linear'], ['zoom'], 3, 0.6, 7, 1.6, 10, 3], 'line-opacity': 0.75 } });
    map.addLayer({ id: 'voided-corridors', type: 'line', source: 'corridors', filter: ['==', ['get', 'voided'], true],
      layout: { visibility: 'none', 'line-cap': 'round' }, paint: { 'line-color': '#d03b3b', 'line-width': 6, 'line-opacity': 0.9 } });
    map.addLayer({ id: 'routes-ghost', type: 'line', source: 'routes', filter: ['==', ['get', 'ghost'], true],
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': '#999', 'line-width': 2, 'line-dasharray': [2, 2], 'line-opacity': 0.9 } });
    map.addLayer({ id: 'routes-casing', type: 'line', source: 'routes', filter: ['!=', ['get', 'ghost'], true],
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': '#fff', 'line-width': ['case', ['==', ['get', 'voided'], true], 9, ['==', ['get', 'selected'], true], 7, 4.5],
        'line-opacity': ['case', ['==', ['get', 'voided'], true], 1, 0.85] } });
    map.addLayer({ id: 'routes-closed-ring', type: 'line', source: 'routes', filter: ['==', ['get', 'closed'], true],
      layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#fab219', 'line-width': 8, 'line-opacity': 0.7, 'line-dasharray': [1, 1.2] } });
    map.addLayer({ id: 'routes-voided-ring', type: 'line', source: 'routes', filter: ['==', ['get', 'voided'], true],
      layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#d03b3b', 'line-width': 7, 'line-opacity': 0.55 } });
    map.addLayer({ id: 'routes', type: 'line', source: 'routes', filter: ['!=', ['get', 'ghost'], true],
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': '#333', 'line-width': ['case', ['==', ['get', 'selected'], true], 3.5, 2.2],
        'line-opacity': ['case', ['==', ['get', 'tone'], 'calm'], 0.7, 1] } });
    map.addLayer({ id: 'routes-transfer', type: 'circle', source: 'routes-transfer',
      paint: { 'circle-radius': 4.5, 'circle-color': '#7a6a58', 'circle-stroke-width': 1.5, 'circle-stroke-color': '#fff' } });
    map.addLayer({ id: 'voided-edges', type: 'line', source: 'voided-edges', layout: { visibility: 'none', 'line-cap': 'round' },
      paint: { 'line-color': '#d03b3b', 'line-width': 7 } });
    map.addLayer({ id: 'voided-edge-points', type: 'circle', source: 'voided-edge-points', layout: { visibility: 'none' },
      paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 5, 9, 9], 'circle-color': '#d03b3b', 'circle-opacity': 0.9,
        'circle-stroke-width': 2, 'circle-stroke-color': '#fff' } });
    map.addLayer({ id: 'facilities', type: 'circle', source: 'facilities', layout: { visibility: 'none' },
      paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 2, 9, 5], 'circle-color': '#888',
        'circle-stroke-width': 0.8, 'circle-stroke-color': '#fff', 'circle-opacity': 0.9 } });
    map.addLayer({ id: 'voided-facilities', type: 'circle', source: 'facilities', filter: ['==', ['get', 'voided'], true],
      layout: { visibility: 'none' },
      paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 4, 9, 8], 'circle-color': '#d03b3b',
        'circle-stroke-width': 1.5, 'circle-stroke-color': '#fff' } });
    map.addLayer({ id: 'nome-halo', type: 'circle', source: 'nome', layout: { visibility: 'none' },
      paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 14, 9, 40], 'circle-color': '#d03b3b', 'circle-opacity': 0.18,
        'circle-stroke-width': 2, 'circle-stroke-color': '#d03b3b', 'circle-stroke-opacity': 0.8 } });
    map.addLayer({ id: 'hubs-other', type: 'circle', source: 'hubs', filter: ['==', ['get', 'role'], 'other'],
      paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 1.8, 8, 4.5], 'circle-color': '#999',
        'circle-stroke-width': 0.8, 'circle-stroke-color': '#fff', 'circle-opacity': 0.9 } });
    map.addLayer({ id: 'hubs-main', type: 'circle', source: 'hubs', filter: ['!=', ['get', 'role'], 'other'],
      paint: { 'circle-radius': ['case', ['==', ['get', 'role'], 'origin'], 7.5, 5.5], 'circle-color': '#222',
        'circle-stroke-width': 2, 'circle-stroke-color': '#fff' } });

    // labels as HTML markers: no glyph server needed. Priority decides who
    // wins when two labels collide: the origin, then Nome, then by facilities.
    const labeled = hubFeatures.features.filter((f) => f.properties.role !== 'other');
    labeled.sort((a, b) => prio(b.properties) - prio(a.properties));
    for (const f of labeled) {
      const el = document.createElement('div');
      el.className = `hub-label ${f.properties.role}${f.properties.voided ? ' voided' : ''}`;
      el.textContent = labelText(f.properties);
      const m = new maplibregl.Marker({ element: el, anchor: 'left', offset: [9, 0] }).setLngLat(f.geometry.coordinates).addTo(map);
      markers.push({ marker: m, pid: f.properties.pid, el });
    }
    declutter();
    map.on('moveend', declutter);
    map.on('zoomend', declutter);
    paintTokens();
    bindHover();
    isReady = true;
    map.fire('demo:ready');
  });

  function prio(p) {
    if (p.role === 'origin') return 1000;
    if (p.pid === 'hub:h000493') return 900;
    return (p.facilities || 0) + (p.name?.startsWith('Bering') ? -50 : 0);
  }
  function labelText(p) {
    if (p.pid === 'hub:h000707') return 'Fairbanks-registered site';
    return p.name;
  }
  function declutter() {
    const taken = [];
    for (const { marker, el } of markers) {
      const pt = map.project(marker.getLngLat());
      const w = el.offsetWidth || 70, h = el.offsetHeight || 16;
      const box = { x1: pt.x + 9, y1: pt.y - h / 2, x2: pt.x + 9 + w, y2: pt.y + h / 2 };
      const hit = taken.some((t) => !(box.x2 < t.x1 || box.x1 > t.x2 || box.y2 < t.y1 || box.y1 > t.y2));
      el.style.visibility = hit ? 'hidden' : '';
      if (!hit) taken.push(box);
    }
  }

  function bindHover() {
    const layers = ['routes', 'routes-transfer', 'voided-edge-points', 'voided-facilities', 'facilities', 'hubs-main', 'hubs-other', 'corridors', 'voided-corridors'];
    map.on('mousemove', (e) => {
      const feats = map.queryRenderedFeatures(e.point, { layers: layers.filter((l) => map.getLayer(l)) });
      if (!feats.length) { popup.remove(); map.getCanvas().style.cursor = ''; return; }
      const f = feats[0];
      map.getCanvas().style.cursor = 'pointer';
      popup.setLngLat(e.lngLat).setHTML(describe(f)).addTo(map);
      if (hoverCb) hoverCb(f);
    });
    map.on('mouseout', () => popup.remove());
    map.on('click', (e) => {
      const feats = map.queryRenderedFeatures(e.point, { layers: ['routes', 'hubs-main'].filter((l) => map.getLayer(l)) });
      if (feats.length && clickCb) clickCb(feats[0]);
    });
  }
  let clickCb = null;

  function describe(f) {
    const p = f.properties;
    const mono = (s) => `<code>${esc(s)}</code>`;
    switch (f.layer.id) {
      case 'routes':
        return `<b>${esc(p.title || 'Route')}</b><br>${esc(MODE_LABEL[p.mode] || p.mode)} leg${p.months ? ` · ${esc(p.months)}` : ''}<br>` +
          `${p.cost != null ? `${fmtUsd(p.cost, 3)}/gal · ` : ''}${p.km != null ? fmtKm(p.km) : ''}` +
          `${p.voided ? `<br><span class="bad">crosses a voided element: ${esc(p.voided_hits)}</span>` : ''}` +
          `${p.closed ? '<br><span class="warn">scheduled in a month when its edges are not passable</span>' : ''}` +
          `${p.note ? `<br><span class="muted">${esc(p.note)}</span>` : ''}`;
      case 'routes-transfer':
        return `<b>Transfer</b> · fuel changes carrier here<br><span class="muted">${esc(p.title || '')}</span>`;
      case 'voided-edge-points':
        return `<b>Voided by D2</b> ${mono(p.pid)}<br>${esc(MODE_LABEL[p.mode] || p.mode)} edge, ${(p.km).toFixed(1)} km`;
      case 'voided-corridors':
        return `<b>Voided corridor</b> ${mono(p.pid)}<br>${esc(MODE_LABEL[p.mode])}, ${p.km} km`;
      case 'voided-facilities':
      case 'facilities':
        return `<b>Facility</b> ${mono(p.pid)}<br>${esc(p.community || '')} · ${esc(p.m1 || '')}${p.m2 ? ' / ' + esc(p.m2) : ''}` +
          `<br>served from ${mono(p.hub || '–')} (${esc(p.last_mile || '?')} last mile)` +
          `${p.voided ? '<br><span class="bad">voided by D2</span>' : ''}` +
          `${p.state && p.state !== 'none' ? `<br>in this report: <b>${esc(p.state)}</b>` : ''}`;
      case 'hubs-main':
      case 'hubs-other':
        return `<b>${esc(p.name)}</b> ${mono(p.pid)}<br>${esc(p.type)} hub · ${esc(p.region)}<br>${esc(p.deliv)}` +
          `${p.cap ? `<br>${Number(p.cap).toLocaleString()} gal capacity` : ''}` +
          `<br>${p.facilities} mapped facilities${p.voided ? '<br><span class="bad">voided by D2</span>' : ''}`;
      case 'corridors': {
        const months = [];
        for (let m = 1; m <= 12; m += 1) if (p[`m${m}`]) months.push(MONTHS[m - 1]);
        return `<b>${esc(MODE_LABEL[p.mode] || p.mode)} corridor</b> ${mono(p.pid)}<br>${p.km} km · ${p.n_edges} edges` +
          `<br><span class="muted">passable: ${months.length === 12 ? 'all year' : esc(months.join(', ')) || 'never'}</span>`;
      }
      default:
        return esc(JSON.stringify(p));
    }
  }

  const api = {
    map,
    ready: (cb) => (isReady ? cb() : map.once('demo:ready', cb)),
    setMonth(month, modes) {
      const modeFilter = modes ? ['in', ['get', 'mode'], ['literal', modes]] : true;
      map.setFilter('corridors', ['all', ['==', ['get', `m${month}`], true], modeFilter]);
    },
    setCorridorOpacity(o) {
      map.setPaintProperty('corridors', 'line-opacity', o);
      map.setPaintProperty('hubs-other', 'circle-opacity', Math.min(1, o + 0.2));
    },
    showFacilities(on) { map.setLayoutProperty('facilities', 'visibility', on ? 'visible' : 'none'); },
    setFacilityStates(stateByPid) {
      for (const f of facFeatures.features) f.properties.state = stateByPid?.[f.properties.pid] || 'none';
      map.getSource('facilities').setData(facFeatures);
    },
    showDisruption(on) {
      for (const id of ['voided-edges', 'voided-edge-points', 'voided-corridors', 'voided-facilities', 'nome-halo']) {
        map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
      }
    },
    setRoutes(features) {
      map.getSource('routes').setData({ type: 'FeatureCollection', features });
      const pts = features.filter((f) => f.properties.mode === 'transfer' && !f.properties.ghost).map((f) => ({
        type: 'Feature', properties: f.properties,
        geometry: { type: 'Point', coordinates: f.geometry.coordinates[0] },
      }));
      map.getSource('routes-transfer').setData({ type: 'FeatureCollection', features: pts });
    },
    fit(name, opts = {}) {
      const b = { alaska: ALASKA, bering: BERING, nome: NOME }[name] || BERING;
      map.fitBounds(b, { padding: opts.padding ?? 28, duration: opts.duration ?? 700 });
    },
    fitTo(bounds, padding = 40) { map.fitBounds(bounds, { padding, duration: 700, maxZoom: 9 }); },
    retheme: paintTokens,
    onHover(cb) { hoverCb = cb; },
    onClick(cb) { clickCb = cb; },
    setLabelMode(mode) { // 'all' | 'destinations'
      for (const { marker } of markers) marker.getElement().style.display = mode === 'none' ? 'none' : '';
    },
  };
  return api;
}

export function boundsOf(features) {
  let minX = 999, minY = 999, maxX = -999, maxY = -999;
  for (const f of features) {
    const cs = f.geometry.type === 'Point' ? [f.geometry.coordinates] : f.geometry.coordinates;
    for (const [x, y] of cs) {
      if (x < minX) minX = x; if (x > maxX) maxX = x; if (y < minY) minY = y; if (y > maxY) maxY = y;
    }
  }
  if (minX > maxX) return null;
  return [[minX, minY], [maxX, maxY]];
}

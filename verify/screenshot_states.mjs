// Load the site in headless Chromium, walk the map states, and save a
// screenshot of each. Fails on any console error, page error, or failed
// request to the site's own files. External hosts (fonts) are blocked so the
// run proves the page works with no network beyond its own files.
//
//   node verify/screenshot_states.mjs [--base http://127.0.0.1:8765] [--out verify/out] [--phone]
import { mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
const { chromium } = createRequire(import.meta.url)('playwright');

const args = Object.fromEntries(process.argv.slice(2).map((a, i, arr) => a.startsWith('--') ? [a.slice(2), arr[i + 1] && !arr[i + 1].startsWith('--') ? arr[i + 1] : true] : []).filter(Boolean));
const BASE = args.base || 'http://127.0.0.1:8765';
const OUT = args.out || 'verify/out';
mkdirSync(OUT, { recursive: true });

const VIEWS = [
  ['baseline', '#map?state=baseline&month=9'],
  ['baseline-feb-nome', '#map?state=baseline&month=2&req=hub:h000493'],
  ['baseline-feb-all', '#map?state=baseline&month=2'],
  ['reassessment-mass-feb', '#map?state=reassessment&topo=mass&cp=reassessment&month=2'],
  ['disruption', '#map?state=disruption'],
  ['disruption-nome', '#map?state=disruption&req=hub:h000493'],
  ['after-nome', '#map?state=after&req=hub:h000493'],
  ['after-all', '#map?state=after'],
  ['reassessment-lin', '#map?state=reassessment&topo=lin&cp=revision'],
  ['reassessment-mass', '#map?state=reassessment&topo=mass&cp=reassessment'],
  ['reassessment-crew-plan', '#map?state=reassessment&topo=crew&cp=plan'],
  ['reassessment-self', '#map?state=reassessment&topo=self&cp=revision&req=rt-001'],
];

const errors = [];
const external = [];
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();
page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push(`console.error: ${m.text()}`); });
page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
page.on('requestfailed', (r) => { if (r.url().startsWith(BASE)) errors.push(`requestfailed: ${r.url()} ${r.failure()?.errorText}`); });
const routeFn = (route) => {
  const url = route.request().url();
  if (url.startsWith(BASE)) return route.continue();
  external.push(url);
  return route.abort();
};
await page.route('**/*', routeFn);

await page.goto(`${BASE}/index.html`, { waitUntil: 'networkidle' });
await page.waitForFunction('window.DEMO && window.DEMO.states', null, { timeout: 30000 });
const settle = async () => {
  await page.waitForTimeout(250);
  await page.evaluate('window.DEMO.states.map.map.stop()');
  await page.waitForFunction('window.DEMO.states.map.map.loaded()', null, { timeout: 20000 });
  await page.waitForTimeout(500);
};
for (const [name, hash] of VIEWS) {
  await page.evaluate((h) => { location.hash = h; }, hash);
  await settle();
  await page.locator('#map-section').scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${OUT}/${name}.png` });
  const panel = (await page.innerText('#map-panel')).slice(0, 90).replace(/\n/g, ' ');
  const n = await page.evaluate("window.DEMO.states.map.map.getSource('routes')._data.features.length");
  const state = await page.evaluate('JSON.stringify(window.DEMO.states.s)');
  console.log(`  ${name.padEnd(24)} features=${String(n).padStart(4)}  ${state}\n${' '.repeat(28)}${panel}`);
}
await page.evaluate("location.hash = ''");
await page.evaluate('window.scrollTo(0,0)');
await page.waitForTimeout(300);
await page.screenshot({ path: `${OUT}/full-page.png`, fullPage: true });
await page.click('#theme-toggle');
await page.evaluate("location.hash = '#map?state=after&req=hub:h000493'");
await settle();
await page.locator('#map-section').scrollIntoViewIfNeeded();
await page.screenshot({ path: `${OUT}/after-dark.png` });
await page.evaluate("location.hash = '#map?state=reassessment&topo=crew&cp=revision'");
await settle();
await page.screenshot({ path: `${OUT}/reassessment-crew-dark.png` });

if (args.phone) {
  const phone = await browser.newContext({ viewport: { width: 400, height: 820 }, deviceScaleFactor: 2 });
  const pp = await phone.newPage();
  await pp.route('**/*', routeFn);
  pp.on('pageerror', (e) => errors.push(`phone pageerror: ${e.message}`));
  await pp.goto(`${BASE}/index.html#map?state=disruption&req=hub:h000493`, { waitUntil: 'networkidle' });
  await pp.waitForFunction('window.DEMO && window.DEMO.states', null, { timeout: 30000 });
  await pp.waitForTimeout(1500);
  const w = await pp.evaluate('document.documentElement.scrollWidth');
  if (w > 400) errors.push(`phone: horizontal overflow, scrollWidth=${w}`);
  await pp.screenshot({ path: `${OUT}/phone-disruption.png` });
  await pp.evaluate('window.scrollTo(0, 0)');
  await pp.screenshot({ path: `${OUT}/phone-top.png` });
}
await browser.close();
console.log(`blocked external requests: ${external.length}${external.length ? ` e.g. ${external[0]}` : ''}`);
if (errors.length) {
  console.log('ERRORS:');
  for (const e of errors) console.log('  ', e);
  process.exit(1);
}
console.log('site ok');

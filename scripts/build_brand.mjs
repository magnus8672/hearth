// Derive current brand exports and application copies from editable SVG masters.
// The supplied v1.0 snapshot under docs/plan is never modified.
import { chromium } from '@playwright/test';
import { readFileSync, writeFileSync, copyFileSync, mkdirSync, readdirSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = name => readFileSync(resolve(root, name), 'utf8').trim();
const write = (name, contents) => writeFileSync(resolve(root, name), contents + '\n');
const inner = svg => svg.replace(/^<svg\b[^>]*>/, '').replace(/<\/svg>$/, '');
const master = read('brand/logos/hearth-mark-light.svg');
const mark = inner(master);
// The fireplace supplies the first h. Only the remaining "earth" paths belong
// in a combined signature; align their baseline and stroke weight to the mark.
const firstH = 'M6 10V80M6 50C6 18 54 18 54 50V80';
const wordmarkSource = inner(read('brand/logos/hearth-wordmark-light.svg'));
if (!wordmarkSource.includes(firstH)) throw new Error('The standalone wordmark master changed; review the integrated signature.');
const wordmark = wordmarkSource.replace(firstH, '').replace('translate(12 8)', 'translate(39 8)');
const svg = (box, content, label = 'hearth') => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${box}" role="img" aria-label="${label}">${content}</svg>`;
const recolor = (content, ink, flame) => content.replaceAll('#29211B', ink).replaceAll('#A94724', flame);
for (const [appearance, ink, flame] of [['light', '#29211B', '#A94724'], ['dark', '#F5EBDF', '#F4A261'], ['mono', 'currentColor', 'currentColor']]) {
  write(`brand/logos/hearth-mark-${appearance}.svg`, recolor(master, ink, flame));
  write(`brand/logos/hearth-lockup-${appearance}.svg`, recolor(svg('0 0 432 124', `<g transform="translate(0 5) scale(.9)">${mark}</g>${wordmark}`), ink, flame));
}
for (const square of [false, true]) {
  write(`brand/logos/hearth-app${square ? '-square' : ''}.svg`, svg('0 0 256 256', `<rect width="256" height="256"${square ? '' : ' rx="57"'} fill="#211D1A"/><g transform="translate(42 34) scale(1.34)">${recolor(mark, '#F5EBDF', '#F4A261')}</g>`, `hearth app icon${square ? ', square source' : ''}`));
}

const glyph = inner(read('brand/icons/hearth.svg'));
write('brand/icons/hearth-icons.svg', read('brand/icons/hearth-icons.svg').replace(/(<symbol id="hearth-hearth"[^>]*>).*?(<\/symbol>)/s, `$1${glyph}$2`));
// The gallery's inline icon map is used when opened as a local file.
const inline = read('brand/previews/icons-inline.js');
const mapStart = inline.indexOf('{');
const mapEnd = inline.lastIndexOf('}');
const icons = JSON.parse(inline.slice(mapStart, mapEnd + 1));
icons.hearth = read('brand/icons/hearth.svg');
write('brand/previews/icons-inline.js', inline.slice(0, mapStart) + JSON.stringify(icons) + inline.slice(mapEnd + 1));
let overview = read('brand/previews/identity-overview.svg');
for (const appearance of ['dark', 'light']) {
  overview = overview.replace(new RegExp(`<svg x="${appearance === 'dark' ? '45' : '685'}"[^>]*>.*?<\\/svg>`, 's'), `<svg x="${appearance === 'dark' ? '45' : '685'}" y="126" width="550" height="123" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 432 124" role="img" aria-label="hearth">${inner(read(`brand/logos/hearth-lockup-${appearance}.svg`))}</svg>`);
}
write('brand/previews/identity-overview.svg', overview);

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ deviceScaleFactor: 1 });
try {
  async function raster(source, size, target) {
    await page.setViewportSize({ width: size, height: size });
    await page.setContent(`<style>html,body{margin:0;background:transparent}svg{display:block;width:${size}px;height:${size}px}</style>${read(source)}`);
    await page.screenshot({ path: resolve(root, target), omitBackground: true });
  }
  for (const size of [16, 24, 32, 48, 64, 128, 256, 512, 1024]) await raster(`brand/logos/hearth-${size <= 32 ? 'favicon' : 'app'}.svg`, size, `brand/logos/hearth-app-${size}.png`);
  for (const size of [512, 1024]) await raster('brand/logos/hearth-app-square.svg', size, `brand/logos/hearth-app-square-${size}.png`);
  for (const appearance of ['light', 'dark']) await raster(`brand/logos/hearth-mark-${appearance}.svg`, 512, `brand/logos/hearth-mark-${appearance}-512.png`);
  const sizes = [16, 24, 32, 48, 64, 128, 256];
  const frames = sizes.map(size => readFileSync(resolve(root, `brand/logos/hearth-app-${size}.png`)));
  const header = Buffer.alloc(6 + 16 * frames.length);
  header.writeUInt16LE(1, 2); header.writeUInt16LE(frames.length, 4);
  let offset = header.length;
  frames.forEach((frame, index) => {
    const entry = 6 + 16 * index;
    header[entry] = sizes[index] % 256; header[entry + 1] = sizes[index] % 256;
    header.writeUInt16LE(1, entry + 4); header.writeUInt16LE(32, entry + 6);
    header.writeUInt32LE(frame.length, entry + 8); header.writeUInt32LE(offset, entry + 12);
    offset += frame.length;
  });
  writeFileSync(resolve(root, 'brand/logos/hearth.ico'), Buffer.concat([header, ...frames]));

  for (const app of ['admin-web', 'user-web']) copyFileSync(resolve(root, 'brand/logos/hearth-favicon.svg'), resolve(root, `apps/${app}/public/favicon.svg`));
  for (const name of ['hearth-lockup-light.svg', 'hearth-lockup-dark.svg', 'hearth-favicon.svg', 'hearth.ico']) copyFileSync(resolve(root, `brand/logos/${name}`), resolve(root, `deploy/identity/themes/hearth/login/resources/img/${name}`));
  copyFileSync(resolve(root, 'brand/logos/hearth-lockup-light.svg'), resolve(root, 'worker/cmd/hearth-setup/hearth-lockup-light.svg'));

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.emulateMedia({ colorScheme: 'dark' });
  const javascriptErrors = [];
  page.on('pageerror', error => javascriptErrors.push(error.message));
  await page.goto(pathToFileURL(resolve(root, 'brand/index.html')).href);
  await page.locator('.signature').waitFor();
  await page.evaluate(() => Promise.all([...document.images].map(image => image.decode())));
  await page.screenshot({ path: resolve(root, 'brand/previews/hearth-gallery-dark.png'), fullPage: true });
  await page.locator('.cover').screenshot({ path: resolve(root, 'brand/previews/hearth-firelight.png') });
  await page.getByRole('button', { name: 'Daylight', exact: true }).click();
  if (await page.locator('html').getAttribute('data-theme') !== 'light') throw new Error('Daylight switch failed');
  await page.evaluate(() => Promise.all([...document.images].map(image => image.decode())));
  await page.locator('.cover').screenshot({ path: resolve(root, 'brand/previews/hearth-daylight.png') });
  await page.getByRole('button', { name: 'Firelight', exact: true }).click();
  if (await page.locator('html').getAttribute('data-theme') !== 'dark') throw new Error('Firelight switch failed');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: resolve(root, 'brand/previews/hearth-mobile.png'), fullPage: true });
  await page.screenshot({ path: resolve(root, 'brand/previews/hearth-mobile-top.png') });
  const layouts = [];
  for (const width of [1440, 960, 640, 390, 320]) {
    await page.setViewportSize({ width, height: 844 });
    layouts.push(await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth, overflow: document.documentElement.scrollWidth > innerWidth })));
  }
  const imageFailures = await page.evaluate(() => [...document.images].filter(image => !image.complete || !image.naturalWidth).map(image => image.getAttribute('src')));
  const sources = ['brand/logos', 'brand/icons', 'brand/previews'].flatMap(folder => readdirSync(resolve(root, folder)).filter(name => name.endsWith('.svg')).map(name => `${folder}/${name}`));
  const svgErrors = await page.evaluate(items => items.filter(([, content]) => new DOMParser().parseFromString(content, 'image/svg+xml').querySelector('parsererror')).map(([name]) => name), sources.map(name => [name, read(name)]));
  write('brand/previews/validation.json', JSON.stringify({ artifact: 'hearth brand kit v1.2', browser: 'Chromium via Playwright', themeSwitch: true, layouts, imageFailures, svgCount: sources.length, svgErrors, javascriptErrors, notes: 'Brand rendering and exports only. Gallery states are illustrative; no inference or release qualification.' }, null, 2));
  if (layouts.some(layout => layout.overflow) || imageFailures.length || svgErrors.length || javascriptErrors.length) throw new Error('Brand rendering validation failed');
  await page.setViewportSize({ width: 1280, height: 810 });
  await page.setContent(`<style>body{margin:0}</style>${read('brand/previews/identity-overview.svg')}`);
  await page.screenshot({ path: resolve(root, 'brand/previews/hearth-identity.png') });

  const evidence = resolve(root, 'evidence/branding/2026-09-13-v1.2');
  mkdirSync(evidence, { recursive: true });
  await page.setViewportSize({ width: 1080, height: 490 });
  await page.setContent(`<style>*{box-sizing:border-box}body{margin:0;font-family:Segoe UI,sans-serif}.sheet{display:flex}.panel{width:540px;height:490px;padding:32px 44px;background:#F5F0E8;color:#29211B}.panel.dark{background:#211D1A;color:#F5EBDF}.label{font-size:12px;letter-spacing:2px;margin-bottom:12px;opacity:.65}.mark{width:200px;height:200px;margin:12px auto 24px}.lockup{width:280px;height:63px;margin:0 auto}.sizes{height:45px;display:flex;gap:18px;align-items:center;justify-content:center;margin-top:24px}.sizes span{font-size:11px;opacity:.65}svg{display:block;width:100%;height:100%}</style><div class="sheet">${['light','dark'].map(appearance => `<section class="panel ${appearance}"><div class="label">${appearance === 'light' ? 'DAYLIGHT' : 'FIRELIGHT'}</div><div class="mark">${read(`brand/logos/hearth-mark-${appearance}.svg`)}</div><div class="lockup">${read(`brand/logos/hearth-lockup-${appearance}.svg`)}</div><div class="sizes">${[16,24,32].map(size => `<div style="width:${size}px;height:${size}px">${read('brand/logos/hearth-favicon.svg')}</div><span>${size}</span>`).join('')}</div></section>`).join('')}</div>`);
  await page.screenshot({ path: resolve(evidence, 'hearth-h-mark.png') });
} finally {
  await browser.close();
}
console.log('Generated logo variants, PNG/ICO exports, application copies and brand previews.');

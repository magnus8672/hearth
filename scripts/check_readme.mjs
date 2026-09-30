import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';
import { access, mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

// Static documentation only: do not start a head or call a model provider.
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const pageURL = pathToFileURL(path.join(root, 'docs/readme.html')).href;
const output = path.join(root, '.hearth/artifacts/readme');
await mkdir(output, { recursive: true });
const browser = await chromium.launch();
const errors = [];
const report = { scope: 'Offline HTML README; no application qualification', viewports: [], checks: [] };
try {
  const context = await browser.newContext({ reducedMotion: 'reduce' });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (/^https?:/.test(request.url())) errors.push(`External request: ${request.url()}`); });
  for (const theme of ['dark', 'light']) {
    for (const width of [320, 390, 768, 1440, 2560]) {
      await page.setViewportSize({ width, height: 1100 });
      await page.goto(pageURL);
      if (await page.locator('html').getAttribute('data-theme') !== theme) await page.locator('#theme-toggle').click();
      const metrics = await page.evaluate(() => ({ width: innerWidth, contentWidth: document.documentElement.scrollWidth, brokenImages: [...document.images].filter(image => !image.complete || !image.naturalWidth).map(image => image.src) }));
      assert(metrics.contentWidth <= width, `Overflow: ${width}px ${theme}`);
      assert.deepEqual(metrics.brokenImages, []);
      assert(await page.locator('.connection-text').getAttribute('d'), 'Tree branches are drawn');
      report.viewports.push({ theme, ...metrics });
      if (width === 1440 || (width === 390 && theme === 'dark')) await page.screenshot({ path: path.join(output, `${theme}-${width}.png`), fullPage: true });
    }
  }
  const links = await page.locator('a, link, script[src], img').evaluateAll(elements => elements.map(element => element.href || element.src).filter(Boolean));
  for (const link of links) {
    const url = new URL(link);
    if (url.protocol !== 'file:') continue;
    await access(fileURLToPath(url));
    if (url.hash && url.pathname === new URL(pageURL).pathname) assert(await page.locator(`[id="${url.hash.slice(1)}"]`).count(), `Missing anchor ${url.hash}`);
  }
  report.checks.push('Every local link, asset and internal navigation target exists');
  for (const [route, expected] of [['chat', 'qualified model target'], ['image', 'One image queue'], ['geometry', 'Choose a 3D backend'], ['all', 'A capability is a destination']]) {
    const button = page.locator(`[data-route="${route}"][type="button"]`);
    await button.focus();
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('.farm-tree').getAttribute('data-route'), route);
    assert.equal(await page.locator('[aria-pressed="true"]').count(), 1);
    assert((await page.locator('#route-title').innerText()).includes(expected));
  }
  report.checks.push('All four illustrative workflows activate by keyboard and update the explanation');
  await page.reload();
  assert.equal(await page.locator('html').getAttribute('data-theme'), 'light');
  await page.keyboard.press('Tab');
  assert.equal(await page.locator(':focus').innerText(), 'Skip to content');
  for (const width of [320, 768, 1440]) {
    await page.setViewportSize({ width, height: 1100 });
    await page.evaluate(() => { document.documentElement.style.fontSize = '200%'; });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `200% text overflow at ${width}px`);
  }
  report.checks.push('Theme persistence, keyboard skip link and 200% text resizing');
  await page.evaluate(() => { document.documentElement.style.fontSize = ''; });
  await page.locator('#theme-toggle').click();
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto(pageURL);
  const cover = { x: 0, y: 0, width: 1440, height: Math.ceil((await page.locator('#farm').boundingBox()).y + (await page.locator('#farm').boundingBox()).height + 35) };
  await page.setViewportSize({ width: cover.width, height: cover.height });
  await page.screenshot({ path: path.join(output, 'cover.png'), clip: cover });
  if (process.argv.includes('--update-preview')) await page.screenshot({ path: path.join(root, 'docs/assets/readme-preview.png'), clip: cover });
  const noJS = await browser.newContext({ javaScriptEnabled: false });
  const staticPage = await noJS.newPage();
  await staticPage.goto(pageURL);
  assert.equal(await staticPage.locator('.capability').count(), 6);
  assert.equal(await staticPage.locator('h1').count(), 1);
  assert.equal(await staticPage.locator('.route-controls').isVisible(), false);
  report.checks.push('Product introduction and static topology remain available without JavaScript');
  const blockedStorage = await browser.newContext();
  await blockedStorage.addInitScript(() => { Object.defineProperty(window, 'localStorage', { get() { throw new DOMException('Blocked', 'SecurityError'); } }); });
  const blockedPage = await blockedStorage.newPage();
  blockedPage.on('pageerror', error => errors.push(error.message));
  await blockedPage.goto(pageURL);
  await blockedPage.locator('#theme-toggle').click();
  assert.equal(await blockedPage.locator('html').getAttribute('data-theme'), 'light');
  report.checks.push('Theme switching works with storage blocked; no external network requests');
  assert.deepEqual(errors, []);
  await writeFile(path.join(output, 'validation.json'), `${JSON.stringify(report, null, 2)}\n`);
  console.log(JSON.stringify(report, null, 2));
} finally {
  await browser.close();
}

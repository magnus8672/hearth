import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// Run against the standalone static preview, never an application or live farm.
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const baseURL = process.env.HEARTH_WEBSITE_URL || 'http://127.0.0.1:8765';
assert(['127.0.0.1', 'localhost', '[::1]'].includes(new URL(baseURL).hostname), 'Use a local static preview');
const output = path.join(root, 'evidence/website/2026-09-13');
await mkdir(output, { recursive: true });
const browser = await chromium.launch();
const report = { checkedAt: new Date().toISOString(), scope: 'Static marketing website only; no product release gates', viewports: [], checks: [], errors: [] };
try {
  const context = await browser.newContext({ reducedMotion: 'reduce' });
  const page = await context.newPage();
  page.on('pageerror', error => report.errors.push(error.message));
  page.on('response', response => { if (response.status() >= 400) report.errors.push(`${response.status()} ${response.url()}`); });
  page.on('request', request => { if (new URL(request.url()).origin !== new URL(baseURL).origin) report.errors.push(`External request: ${request.url()}`); });
  for (const theme of ['light', 'dark']) {
    for (const width of [320, 390, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.emulateMedia({ colorScheme: theme });
      await page.goto(baseURL);
      const metrics = await page.evaluate(() => ({ width: innerWidth, contentWidth: document.documentElement.scrollWidth, brokenImages: [...document.images].filter(img => !img.complete || img.naturalWidth === 0).map(img => img.src) }));
      assert(metrics.contentWidth <= width, `Overflow at ${width}px ${theme}`);
      assert.deepEqual(metrics.brokenImages, []);
      report.viewports.push({ theme, ...metrics });
      if (width === 1440 || (width === 390 && theme === 'dark')) {
        await page.screenshot({ path: path.join(output, `${theme}-${width}.png`), fullPage: true });
        await page.screenshot({ path: path.join(output, `${theme}-${width}-viewport.png`) });
      }
    }
  }
  await page.getByRole('button', { name: 'Code', exact: true }).click();
  assert.equal(await page.locator('.farm').getAttribute('data-route'), 'code');
  assert.match(await page.locator('#route-result').innerText(), /Code specialist.*spare desktop/s);
  const imagine = page.getByRole('button', { name: 'Imagine', exact: true });
  await imagine.focus();
  await page.keyboard.press('Enter');
  assert.equal(await imagine.getAttribute('aria-pressed'), 'true');
  assert.equal(await page.locator('.farm').getAttribute('data-route'), 'image');
  assert.match(await page.locator('#route-result').innerText(), /Image specialist.*creative workstation/s);
  await page.getByRole('button', { name: 'Write', exact: true }).click();
  assert.match(await page.locator('#route-result').innerText(), /Writing specialist.*everyday laptop/s);
  assert.equal(await page.locator('[aria-pressed="true"]').count(), 1);
  report.checks.push('All three routing illustrations, keyboard activation, and exclusive pressed state');
  await page.getByLabel('Appearance').selectOption('light');
  await page.reload();
  assert.equal(await page.locator('html').getAttribute('data-theme'), 'light');
  await page.getByLabel('Appearance').selectOption('dark');
  await page.reload();
  assert.equal(await page.locator('html').getAttribute('data-theme'), 'dark');
  await page.getByLabel('Appearance').selectOption('system');
  await page.emulateMedia({ colorScheme: 'light' });
  assert.equal(await page.locator('html').getAttribute('data-theme'), null);
  assert.equal(await page.locator('.logo-light:visible').count(), 2);
  await page.emulateMedia({ colorScheme: 'dark' });
  assert.equal(await page.locator('.logo-dark:visible').count(), 2);
  report.checks.push('Light/dark persistence, live system preference, and matching logos');
  const brokenAnchors = await page.evaluate(() => [...document.querySelectorAll('a[href^="#"]')].filter(a => a.hash && !document.getElementById(a.hash.slice(1))).map(a => a.hash));
  assert.deepEqual(brokenAnchors, []);
  await page.goto(baseURL);
  await page.keyboard.press('Tab');
  assert.equal(await page.locator(':focus').innerText(), 'Skip to content');
  await page.keyboard.press('Enter');
  assert.equal(new URL(page.url()).hash, '#main');
  report.checks.push('Every navigation target exists; keyboard skip link works');
  for (const width of [320, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.evaluate(() => { document.documentElement.style.fontSize = '200%'; });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `200% text overflow at ${width}px`);
  }
  report.checks.push('200% text enlargement without horizontal overflow at 320, 768, 1440px');
  await context.close();
  const blockedStorage = await browser.newContext();
  await blockedStorage.addInitScript(() => { Object.defineProperty(window, 'localStorage', { get() { throw new DOMException('Blocked', 'SecurityError'); } }); });
  const blockedPage = await blockedStorage.newPage();
  blockedPage.on('pageerror', error => report.errors.push(error.message));
  await blockedPage.goto(baseURL);
  await blockedPage.getByLabel('Appearance').selectOption('dark');
  assert.equal(await blockedPage.locator('html').getAttribute('data-theme'), 'dark');
  report.checks.push('Theme controls work when browser storage is blocked');
  await blockedStorage.close();
  const noJS = await browser.newContext({ javaScriptEnabled: false });
  const staticPage = await noJS.newPage();
  await staticPage.goto(baseURL);
  assert.equal(await staticPage.locator('h1').count(), 1);
  assert.equal(await staticPage.locator('main section').count(), 6);
  assert.equal(await staticPage.locator('[data-enhanced]:visible').count(), 0);
  report.checks.push('All six narrative sections render without JavaScript; enhancement-only controls are hidden');
  await noJS.close();
  for (const [source, copy] of [
    ['brand/tokens/hearth.css', 'hearth.css'], ['brand/icons/hearth-icons.svg', 'hearth-icons.svg'],
    ...['hearth-lockup-dark.svg', 'hearth-lockup-light.svg', 'hearth-mark-dark.svg', 'hearth-favicon.svg'].map(name => [`brand/logos/${name}`, name])
  ]) assert.deepEqual(await readFile(path.join(root, source)), await readFile(path.join(root, 'website/assets', copy)), `Brand drift: ${copy}`);
  report.checks.push('All six copied brand assets exactly match current repository masters');
  const files = await readdir(path.join(root, 'website'), { recursive: true, withFileTypes: true });
  report.payloadBytes = (await Promise.all(files.filter(item => item.isFile()).map(async item => (await readFile(path.join(item.parentPath, item.name))).length))).reduce((a,b) => a+b, 0);
  assert.deepEqual(report.errors, []);
  report.passed = true;
} catch (error) {
  report.passed = false;
  report.errors.push(error.message);
  process.exitCode = 1;
} finally {
  await browser.close();
  await writeFile(path.join(output, 'validation.json'), `${JSON.stringify(report, null, 2)}\n`);
  console.log(JSON.stringify(report, null, 2));
}

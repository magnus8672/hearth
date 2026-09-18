import { test, expect } from '@playwright/test';
import fs from 'node:fs';

test('geometry upload, private preview, cancellation and deletion', async ({ page }) => {
  const origin = process.env.HEARTH_BROWSER_ORIGIN || 'https://hearth.example.invalid';
  let jobs: Record<string, any>[] = [];
  await page.route('**/api/v1/session', route => route.fulfill({ json: { id: 'fixture', display_name: 'Tester', roles: ['Member'], permissions: ['conversation.own'], csrf_token: 'fixture', user_origin: origin, admin_origin: 'https://hearth.example.invalid:8443' } }));
  await page.route('**/api/v1/capabilities', route => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/v1/geometry-targets', route => route.fulfill({ json: { items: [{ id: 'gpu', model_id: 'trellis2/q8', name: 'media-worker fixture', state: 'ready', profile: { resolutions: [512, 1024] } }] } }));
  await page.route('**/api/v1/geometry', async route => {
    if (route.request().method() === 'POST') {
      const data = route.request().postDataJSON();
      expect(data.request.resolution).toBe(512);
      expect(data.request.image_sha256).toHaveLength(64);
      expect(route.request().headers()['x-hearth-csrf']).toBe('fixture');
      jobs.unshift({ id: data.request.id, request: data.request, status: 'queued', cancel_requested: false });
      await route.fulfill({ status: 202, json: { id: data.request.id } });
    } else await route.fulfill({ json: { items: jobs } });
  });
  await page.route('**/api/v1/geometry/*', async route => {
    expect(route.request().method()).toBe('DELETE');
    jobs = []; await route.fulfill({ json: { deleted: true } });
  });
  await page.route('**/api/v1/geometry/*/cancel', async route => {
    jobs[0].status = 'cancelled'; await route.fulfill({ json: { cancel_requested: true } });
  });
  await page.goto(origin + '/#geometry');
  await page.getByLabel('Reference image').setInputFiles({ name: 'fixture.png', mimeType: 'image/png', buffer: Buffer.from('explicit browser upload fixture') });
  await page.getByRole('button', { name: 'Create 3D model' }).click();
  await expect(page.locator('.geometry-card')).toHaveCount(1);
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(page.locator('.geometry-card')).toContainText('cancelled');
  if (process.env.HEARTH_GLB_FIXTURE) {
    jobs[0].status = 'completed'; jobs[0].metadata = { triangles: 144438, textures: 2, bytes: 5364416 };
    await page.route('**/api/v1/geometry/*/model', route => route.fulfill({ contentType: 'model/gltf-binary', body: fs.readFileSync(process.env.HEARTH_GLB_FIXTURE!) }));
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    await page.getByRole('button', { name: 'Preview 3D' }).click();
    await expect(page.locator('.geometry-preview canvas')).toBeVisible();
    await expect(page.getByRole('alert')).toHaveCount(0);
    await page.screenshot({ path: '.hearth/geometry-preview.png', fullPage: true });
    expect(errors).toEqual([]);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  page.on('dialog', dialog => void dialog.accept());
  await page.getByRole('button', { name: 'Delete model' }).click();
  await expect(page.locator('.geometry-card')).toHaveCount(0);
});

test('upload errors preserve HTTP meaning and keep the selected file', async ({ page }) => {
  const origin = process.env.HEARTH_BROWSER_ORIGIN || 'https://hearth.example.invalid';
  await page.route('**/api/v1/session', route => route.fulfill({ json: { id: 'fixture', display_name: 'Tester', roles: ['Member'], permissions: ['conversation.own'], csrf_token: 'fixture', user_origin: origin, admin_origin: 'https://hearth.example.invalid:8443' } }));
  await page.route('**/api/v1/capabilities', route => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/v1/geometry-targets', route => route.fulfill({ json: { items: [{ id: 'gpu', model_id: 'trellis2/q8', name: 'Fixture', state: 'ready', profile: { resolutions: [512] } }] } }));
  let failure = { status: 413, body: '', contentType: 'text/plain' };
  await page.route('**/api/v1/geometry', route => route.fulfill(route.request().method() === 'POST' ? failure : { json: { items: [] } }));
  await page.goto(origin + '/#geometry');
  await page.getByLabel('Reference image').setInputFiles({ name: 'large-fixture.png', mimeType: 'image/png', buffer: Buffer.alloc(1_700_000) });
  for (const scenario of [
    { status: 413, body: '', contentType: 'text/plain', message: 'This upload exceeds the server limit.' },
    { status: 502, body: '<html>Bad gateway</html>', contentType: 'text/html', message: 'hearth is temporarily unavailable.' },
    { status: 409, body: JSON.stringify({ error: { message: 'Choose a verified geometry model.' } }), contentType: 'application/json', message: 'Choose a verified geometry model.' },
    { status: 200, body: '', contentType: 'application/json', message: 'hearth returned an empty or unreadable response.' },
  ]) {
    failure = scenario;
    await page.getByRole('button', { name: 'Create 3D model' }).click();
    await expect(page.getByRole('alert')).toContainText(scenario.message);
    await expect(page.getByRole('alert')).not.toContainText('JSON');
    await expect(page.getByText('large-fixture.png · 1.6 MB')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Create 3D model' })).toBeEnabled();
  }
});

test('live edge admits geometry upload envelopes while retaining other limits', async ({ page }) => {
  test.skip(process.env.HEARTH_LIVE_UPLOAD_EDGE !== '1', 'Opt in against the deployed head; no session or generation is used.');
  const origin = process.env.HEARTH_BROWSER_ORIGIN || 'https://hearth.example.invalid';
  await page.goto(origin + '/health/browser');
  const results = await page.evaluate(async () => {
    const request = { target_id: crypto.randomUUID(), request: { id: crypto.randomUUID(), model: 'unauthenticated-boundary-test', image_sha256: '0'.repeat(64) }, image: '' };
    const results: number[] = [];
    for (const size of [2_300_000, 4 * Math.ceil(8 * 1024 * 1024 / 3)]) {
      request.image = 'A'.repeat(size);
      const response = await fetch('/api/v1/geometry', { method: 'POST', credentials: 'omit', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request) });
      results.push(response.status);
      if (response.status === 401 && !(await response.json()).error?.code) throw new Error('Missing application authentication response.');
    }
    for (const [path, method, size] of [['/api/v1/geometry', 'POST', 12_100_001], ['/api/v1/notes', 'POST', 2_300_000], ['/api/v1/geometry', 'PUT', 2_300_000]] as const) {
      const response = await fetch(path, { method, credentials: 'omit', headers: { 'Content-Type': 'application/json' }, body: ' '.repeat(size) });
      results.push(response.status);
    }
    return results;
  });
  // 401 demonstrates admission through Caddy to the application, without
  // authenticating or creating user content. The other bodies remain bounded.
  expect(results).toEqual([401, 401, 413, 413, 413]);
});

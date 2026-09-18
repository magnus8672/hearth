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

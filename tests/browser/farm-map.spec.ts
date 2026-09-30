import { browserOrigins } from './origins';
import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const origin = browserOrigins.admin;
const node = (id: string, cap = 'chat.general', model = 'fixture-model') => ({ id, capability: cap, name: cap === 'chat.general' ? 'Conversation' : '3D generation', icon: 'cube', residency: 'loaded', verified: true, model, endpoint: 'https://10.1.1.2:1234/v1', pool: 'Fixture pool', priority: 0 });
const initial = () => ({ observed_at: new Date().toISOString(), binding_count: 3,
  machines: [
    { id: 'head', name: 'hearth head', address: 'head.example', kind: 'head', nodes: [{ id: 'memory.retrieve', name: 'Memory retrieval', capability: 'memory.retrieve', icon: 'knowledge', residency: 'builtin', verified: true }], pools: [] },
    { id: 'host:one', name: 'First machine', address: '10.1.1.2', kind: 'external', nodes: [node('chat')], pools: [] },
    { id: 'host:two', name: 'Media machine', address: '10.1.1.3', kind: 'managed', nodes: [node('trellis', 'geometry.generate', 'TRELLIS'), { ...node('hunyuan', 'geometry.generate', 'Hunyuan'), residency: 'on_demand' }], pools: [{ id: 'media', name: 'GPU', state: 'idle', queued: 0, policy: 'shared', desired_service: 'trellis', ready_service: 'trellis' }] },
  ], unassigned: [{ id: 'audio.speak', name: 'Speech', icon: 'speech' }], unbound_targets: [] });

test.beforeEach(async ({ page }) => {
  // Optional pre-deploy static bundle override. All API behavior below is a fixture.
  if (process.env.HEARTH_MAP_PREVIEW_DIR) {
    const root = resolve(process.env.HEARTH_MAP_PREVIEW_DIR);
    await page.route(origin + '/**', async route => {
      const path = new URL(route.request().url()).pathname;
      if (path === '/' || /^\/assets\/[a-zA-Z0-9_.-]+$/.test(path)) {
        const type = path === '/' ? 'text/html' : path.endsWith('.js') ? 'application/javascript' : path.endsWith('.css') ? 'text/css' : 'image/svg+xml';
        await route.fulfill({ body: readFileSync(resolve(root, path === '/' ? 'index.html' : path.slice(1))), contentType: type });
      } else await route.fallback();
    });
  }
  await page.route('**/api/v1/session', route => route.fulfill({ json: { id: 'fixture', display_name: 'Operator', roles: ['Owner'], permissions: ['farm.inspect'], csrf_token: 'fixture', admin_origin: origin, user_origin: browserOrigins.workspace } }));
  await page.route('**/api/v1/farm', route => route.fulfill({ json: { farm: { name: 'Fixture farm' }, members: [] } }));
  await page.route('**/api/v1/capabilities', route => route.fulfill({ json: { items: [] } }));
});

test('live updates reconcile nodes and residency, preserve inspection, and flag stale observations', async ({ page }) => {
  let snapshot = initial(), fail = false, reads = 0;
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/v1/farm-map', route => { reads++; expect(route.request().method()).toBe('GET'); return route.fulfill(fail ? { status: 503, json: {} } : { json: snapshot }); });
  await page.setViewportSize({ width: 1800, height: 1100 });
  await page.goto(origin + '/#farm-map');
  await expect(page.locator('.fm-host')).toHaveCount(3);
  await page.getByRole('button', { name: '3D generation · Hunyuan', exact: true }).click();
  await expect(page.locator('.fm-inspector')).toContainText('On demand');
  snapshot.machines[2].nodes[1].residency = 'service_ready';
  await expect(page.locator('.fm-inspector')).toContainText('Service ready', { timeout: 15000 });
  expect(reads).toBeGreaterThan(1);
  await page.getByRole('button', { name: 'Collapse Media machine' }).click();
  await expect(page.getByRole('button', { name: '3D generation · Hunyuan', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Expand Media machine' }).click();
  snapshot.machines.splice(1, 1); snapshot.binding_count = 2;
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.locator('.fm-host')).toHaveCount(2);
  fail = true;
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('stale');
  await expect(page.locator('.fm-node-state').first()).toHaveText('Observation stale');
  fail = false;
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await page.getByRole('button', { name: 'Unassigned 1' }).click();
  await page.getByRole('button', { name: 'Speech', exact: true }).click();
  await expect(page.locator('.fm-inspector')).toContainText('No dedicated binding');
  await page.getByLabel('Appearance').selectOption('dark');
  await page.getByRole('button', { name: 'hearth head', exact: true }).click();
  await page.screenshot({ path: '.hearth/test-results/farm-map-dark.png', fullPage: true });
  await page.getByLabel('Appearance').selectOption('light');
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const before = await page.locator('.fm-controls span').innerText();
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  await expect(page.locator('.fm-controls span')).not.toHaveText(before);
  expect(errors).toEqual([]);
});

test('empty and growing farms fit arbitrary hosts and repeated capability bindings', async ({ page }) => {
  const snapshot = initial(); snapshot.machines = snapshot.machines.slice(0, 1); snapshot.binding_count = 0;
  await page.route('**/api/v1/farm-map', route => route.fulfill({ json: snapshot }));
  await page.goto(origin + '/#farm-map');
  await expect(page.locator('.fm-host')).toHaveCount(1);
  const template = initial().machines[2];
  snapshot.machines.push(...Array.from({ length: 5 }, (_, i) => ({ ...template, id: 'machine-' + i, name: 'Machine ' + i, nodes: Array.from({ length: 7 }, (_, j) => node(`${i}:${j}`, 'geometry.generate', `Model ${i}:${j}`)) })));
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.locator('.fm-host')).toHaveCount(6);
  await expect(page.locator('.fm-node')).toHaveCount(37);
  await page.getByRole('button', { name: 'Fit map', exact: true }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

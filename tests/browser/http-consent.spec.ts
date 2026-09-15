import { test, expect } from '@playwright/test';

test('admin accepts HTTP on a failed LAN card, re-verifies, revokes and starts new addresses unapproved', async ({ page }) => {
  await page.route('**/api/v1/session', route => route.fulfill({ json: { id: 'fixture', display_name: 'Tester', roles: ['Owner'], permissions: ['farm.inspect', 'provider.configure'], csrf_token: 'fixture-csrf', admin_origin: 'http://127.0.0.1:5173', user_origin: 'http://127.0.0.1:5174' } }));
  for (const endpoint of ['capabilities', 'capability-routes']) await page.route(`**/api/v1/${endpoint}`, route => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/v1/farm', route => route.fulfill({ json: { farm: { name: 'Fixture farm' }, members: [] } }));
  let item = { id: 'lan', connection_id: 'connection', name: 'model-server', base_url: 'http://10.20.30.40:1234/v1', model_id: 'qwen/qwen3.8-27b', protocol: 'openai.chat.v1', revision: 2, state: 'failed', allow_insecure_http: false, expired: false, reason: 'An administrator can accept the risks on this provider card.', features: [] as string[], pool_name: 'model-server', execution_state: 'idle', active_run_id: null };
  let probes = 0;
  let accepted = 0;
  let registered = false;
  await page.route('**/api/v1/providers', async route => {
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON();
      expect(body.allow_insecure_http).toBe(true);
      expect(body.base_url).toBe('http://10.20.30.41:1234');
      registered = true;
      return route.fulfill({ status: 201, json: { id: 'new', revision: 1 } });
    }
    await route.fulfill({ json: { items: [item] } });
  });
  await page.route('**/api/v1/providers/lan/http-consent', async route => {
    const body = route.request().postDataJSON();
    expect(route.request().headers()['x-hearth-csrf']).toBe('fixture-csrf');
    expect(body.revision).toBe(item.revision);
    if (body.allow_insecure_http) accepted++;
    item = { ...item, allow_insecure_http: body.allow_insecure_http, revision: item.revision + 1, state: 'configured', features: [] };
    await route.fulfill({ json: { id: 'lan', revision: item.revision, allow_insecure_http: item.allow_insecure_http } });
  });
  await page.route('**/api/v1/providers/lan/probe', async route => {
    expect(item.allow_insecure_http).toBe(true);
    expect(route.request().postDataJSON().revision).toBe(item.revision);
    probes++;
    item = { ...item, revision: item.revision + 1, state: 'ready', features: ['chat', 'streaming'], reason: '' };
    await route.fulfill({ json: { state: 'ready', reason: null } });
  });
  await page.route('**/api/v1/providers/new/probe', route => route.fulfill({ json: { state: 'ready', reason: null } }));
  await page.goto('/#providers');
  await expect(page.getByText('HTTP is unencrypted.', { exact: false })).toBeVisible();
  expect(accepted).toBe(0); expect(probes).toBe(0);
  await page.getByRole('button', { name: 'I understand the risks. Use HTTP' }).click();
  await expect(page.getByText('HTTP · admin accepted risks', { exact: true })).toBeVisible();
  expect(accepted).toBe(1); expect(probes).toBe(1);
  await page.reload();
  await expect(page.getByRole('button', { name: 'I understand the risks. Use HTTP' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Edit connection' }).click();
  await expect(page.getByLabel('I’m the administrator', { exact: false })).toBeChecked();
  await page.getByLabel('Server address').fill('http://10.20.30.41:1234');
  await expect(page.getByLabel('I’m the administrator', { exact: false })).not.toBeChecked();
  await page.getByRole('button', { name: 'Add server', exact: true }).click();
  await page.getByLabel('Connection name').fill('Another machine');
  await page.getByLabel('Server address').fill('http://10.20.30.41:1234');
  await page.getByLabel('Model identifier').fill('fixture');
  await page.getByLabel('Resource group', { exact: true }).fill('Another GPU');
  await page.getByLabel('I trust this local server', { exact: false }).check();
  await expect(page.getByRole('button', { name: 'Connect & verify chat' })).toBeDisabled();
  await page.getByLabel('I’m the administrator', { exact: false }).check();
  await page.getByRole('button', { name: 'Connect & verify chat' }).click();
  await expect(page.getByLabel('Server address')).toHaveValue('');
  expect(registered).toBe(true);
  await page.getByRole('button', { name: 'Revoke HTTP approval' }).click();
  await expect(page.getByRole('button', { name: 'I understand the risks. Use HTTP' })).toBeVisible();
  expect(probes).toBe(1);
  await page.getByLabel('Appearance').selectOption('dark');
  await page.screenshot({ path: 'evidence/http-consent/2026-09-13/admin-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'evidence/http-consent/2026-09-13/admin-mobile.png', fullPage: true });
});

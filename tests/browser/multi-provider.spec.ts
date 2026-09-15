import { test, expect } from '@playwright/test';

test('add four same-type servers, keep edit separate, share one server, and add two image providers', async ({ page }) => {
  await page.route('**/api/v1/session', route => route.fulfill({ json: { id: 'fixture', display_name: 'Tester', roles: ['Owner'], permissions: ['farm.inspect', 'provider.configure'], csrf_token: 'fixture-csrf', admin_origin: 'http://127.0.0.1:5173', user_origin: 'http://127.0.0.1:5174' } }));
  for (const endpoint of ['capabilities', 'capability-routes']) await page.route(`**/api/v1/${endpoint}`, route => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/v1/farm', route => route.fulfill({ json: { farm: { name: 'Fixture farm' }, members: [] } }));
  type Model = { id: string; name: string; base_url: string; model_id: string; protocol: string; pool_name: string; revision: number; state: string; features: string[]; expired: boolean; active_run_id: null; execution_state: string; residency_policy: string };
  const models: Model[] = [];
  let edits = 0;
  await page.route('**/api/v1/providers', async route => {
    if (route.request().method() === 'GET') return route.fulfill({ json: { items: models } });
    const data = route.request().postDataJSON();
    expect(data.local_only).toBe(true);
    expect(data.resource_pool.length).toBeGreaterThan(0);
    if (models.some(item => item.base_url === data.base_url && item.model_id === data.model_id)) return route.fulfill({ status: 409, json: { detail: 'That model is already registered.' } });
    const item = { ...data, id: String(models.length + 1), pool_name: data.resource_pool, revision: 1, state: 'configured', features: [], expired: false, active_run_id: null, execution_state: 'idle' };
    models.push(item);
    await route.fulfill({ status: 201, json: item });
  });
  await page.route('**/api/v1/providers/*', async route => { edits++; await route.fulfill({ status: 500, json: { detail: 'Adding must never edit an existing target.' } }); });
  await page.route('**/api/v1/providers/*/probe', async route => {
    const id = route.request().url().split('/').at(-2);
    const model = models.find(item => item.id === id)!;
    model.revision++; model.state = 'ready'; model.features = [model.protocol === 'hearth.image.v1' ? 'image.text_to_image' : 'chat'];
    await route.fulfill({ json: { state: 'ready', reason: null } });
  });
  await page.goto('/#providers');
  for (let index = 0; index < 4; index++) {
    await page.getByRole('button', { name: 'Add server', exact: true }).click();
    for (const label of ['Connection name', 'Server address', 'Model identifier', 'Resource group']) await expect(page.getByLabel(label, { exact: true })).toHaveValue('');
    await page.getByLabel('Connection name').fill(`Machine ${index + 1}`);
    await page.getByLabel('Server address').fill(`https://192.168.1.${40 + index}:1240`);
    await page.getByLabel('Model identifier').fill(index === 3 ? 'resident-0' : `resident-${index}`);
    await page.getByLabel('Resource group', { exact: true }).fill(`Machine ${index + 1} GPU`);
    await page.getByLabel('Loaded-model check').selectOption('lmstudio_loaded');
    await page.getByLabel('I have disabled automatic model loading').check();
    await page.getByLabel('I trust this local server', { exact: false }).check();
    await page.getByRole('button', { name: 'Connect & verify chat' }).click();
    await expect(page.locator('.target-card')).toHaveCount(index + 1);
    await expect(page.getByText('Text and streaming verified.', { exact: false })).toBeVisible();
    await expect(page.getByLabel('Connection name')).toHaveValue('');
  }
  await page.reload();
  await expect(page.locator('.target-card')).toHaveCount(4);
  const first = page.locator('.target-card').filter({ has: page.getByRole('heading', { name: 'Machine 1', exact: true }) }).first();
  await first.getByRole('button', { name: 'Edit connection' }).click();
  await expect(page.getByRole('heading', { name: 'Editing this model' })).toBeVisible();
  await page.getByRole('textbox', { name: 'API key', exact: false }).fill('must-be-cleared');
  await page.getByRole('button', { name: 'Add server', exact: true }).click();
  await expect(page.getByLabel('API key', { exact: false })).toHaveValue('');
  await expect(page.getByLabel('Server address')).toHaveValue('');
  await expect(page.getByLabel('I trust this local server', { exact: false })).not.toBeChecked();
  await first.getByRole('button', { name: 'Add model to this server' }).click();
  await expect(page.getByLabel('Server address')).toBeDisabled();
  await expect(page.getByLabel('Server address')).toHaveValue('https://192.168.1.40:1240');
  await expect(page.getByLabel('API key', { exact: false })).toBeDisabled();
  await expect(page.getByLabel('Model identifier')).toHaveValue('');
  await expect(page.getByText('This group already exists.', { exact: false })).toBeVisible();
  await page.getByLabel('Model identifier').fill('second-resident');
  await page.getByLabel('I have disabled automatic model loading').check();
  await page.getByLabel('I trust this local server', { exact: false }).check();
  await page.getByRole('button', { name: 'Connect & verify chat' }).click();
  await expect(page.locator('.target-card')).toHaveCount(5);
  expect(models[0].model_id).toBe('resident-0');
  expect(models[4].base_url).toBe(models[0].base_url);
  expect(models[4].pool_name).toBe(models[0].pool_name);
  expect(edits).toBe(0);
  for (let index = 0; index < 2; index++) {
    await page.getByRole('button', { name: 'Add server', exact: true }).click();
    await page.getByLabel('Provider type').selectOption('hearth.image.v1');
    await page.getByLabel('Connection name').fill(`Image machine ${index + 1}`);
    await page.getByLabel('Server address').fill(`https://192.168.1.${50 + index}:1240`);
    await page.getByLabel('Model identifier').fill('same-image-model');
    await page.getByLabel('Resource group', { exact: true }).fill(`Image GPU ${index + 1}`);
    await page.getByLabel('I trust this local server', { exact: false }).check();
    await page.getByRole('button', { name: 'Connect & verify images' }).click();
    await expect(page.locator('.target-card')).toHaveCount(index + 6);
    await expect(page.getByText('Image generation verified.', { exact: false })).toBeVisible();
  }
  await page.reload();
  await expect(page.locator('.target-card')).toHaveCount(7);
  await page.getByLabel('Appearance').selectOption('dark');
  await page.screenshot({ path: 'evidence/multi-provider/2026-09-13/admin-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'evidence/multi-provider/2026-09-13/admin-mobile.png', fullPage: true });
});

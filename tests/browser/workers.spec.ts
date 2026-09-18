import { test, expect } from '@playwright/test';

test('worker controls separate pause from service switching and forbid busy unloads', async ({ page }) => {
  const origin = process.env.HEARTH_ADMIN_BROWSER_ORIGIN || 'https://hearth.example.invalid:8443';
  let worker = { id: 'fixture', name: 'media-worker fixture', pool_name: 'GPU fixture', online: true, state: 'ready', reason: '', policy: 'resident', paused: false, revoked: false, revision: 1, desired_service: 'fooocus', ready_service: 'fooocus', active_run_id: null as string | null, execution_state: 'idle', queued: 2, services: { fooocus: { name: 'Fooocus', connection_id: 'fixture' } } };
  await page.route('**/api/v1/session', route => route.fulfill({ json: { id: 'worker-fixture', display_name: 'Operator', roles: ['Owner'], permissions: ['farm.inspect', 'node.operate', 'node.assign'], csrf_token: 'fixture-csrf', admin_origin: origin, user_origin: 'https://hearth.example.invalid' } }));
  await page.route('**/api/v1/farm', route => route.fulfill({ json: { farm: { name: 'Fixture' }, members: [] } }));
  await page.route('**/api/v1/capabilities', route => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/v1/workers', route => route.fulfill({ json: { items: [worker] } }));
  await page.route('**/api/v1/workers/fixture', async route => {
    expect(route.request().method()).toBe('PUT');
    expect(route.request().headers()['x-hearth-csrf']).toBe('fixture-csrf');
    const update = route.request().postDataJSON();
    expect(update.revision).toBe(worker.revision);
    worker = { ...worker, ...update, revision: worker.revision + 1 };
    await route.fulfill({ json: { saved: true } });
  });
  await page.goto(origin + '/#workers');
  await expect(page.getByRole('heading', { name: 'media-worker fixture' })).toBeVisible();
  await page.getByRole('button', { name: 'Pause queue' }).click();
  await expect(page.getByRole('button', { name: 'Resume queue' })).toBeVisible();
  expect(worker.desired_service).toBe('fooocus');
  page.on('dialog', dialog => void dialog.accept());
  await page.getByLabel('GPU policy').selectOption('shared');
  await expect(page.getByLabel('GPU policy')).toHaveValue('shared');
  await page.getByLabel('Selected service').selectOption('');
  expect(worker.paused).toBe(true);
  await expect(page.getByRole('button', { name: 'Resume queue' })).toBeDisabled();
  worker = { ...worker, desired_service: 'fooocus', paused: false, active_run_id: 'active', execution_state: 'running' };
  await expect(page.getByLabel('Selected service')).toBeDisabled({ timeout: 5000 });
  await expect(page.getByRole('button', { name: 'Pause queue' })).toBeEnabled();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('gallery accepts another image while one is queued and supports cancellation', async ({ page }) => {
  const origin = process.env.HEARTH_BROWSER_ORIGIN || 'https://hearth.example.invalid';
  const jobs: Record<string, any>[] = [];
  await page.route('**/api/v1/session', route => route.fulfill({ json: { id: 'fixture', display_name: 'Tester', roles: ['Member'], permissions: ['conversation.own'], csrf_token: 'fixture', admin_origin: 'https://hearth.example.invalid:8443', user_origin: origin } }));
  await page.route('**/api/v1/capabilities', route => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/v1/image-targets', route => route.fulfill({ json: { items: [{ id: 'gpu', model_id: 'fixture', name: 'Local GPU', ready: true }] } }));
  await page.route('**/api/v1/images', async route => {
    if (route.request().method() === 'POST') {
      const data = route.request().postDataJSON();
      jobs.unshift({ id: data.request.id, target_id: data.target_id, request: data.request, status: 'queued', progress: 0, cancel_requested: false });
      await route.fulfill({ status: 202, json: { id: data.request.id, status: 'queued' } });
    } else await route.fulfill({ json: { items: jobs } });
  });
  await page.route('**/api/v1/images/*/cancel', async route => {
    jobs.find(job => route.request().url().includes(job.id))!.status = 'cancelled';
    await route.fulfill({ json: { cancel_requested: true } });
  });
  await page.goto(origin + '/#images');
  await page.getByLabel('Describe your image').fill('First picture');
  await page.getByRole('button', { name: 'Create image', exact: true }).click();
  await expect(page.locator('.image-card')).toHaveCount(1);
  await page.getByLabel('Describe your image').fill('Second picture');
  await page.getByRole('button', { name: 'Add to queue', exact: true }).click();
  await expect(page.locator('.image-card')).toHaveCount(2);
  await page.getByRole('button', { name: 'Cancel queued image' }).first().click();
  await expect(page.getByRole('button', { name: 'Cancel queued image' })).toHaveCount(1);
});

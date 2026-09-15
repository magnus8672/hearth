import { test, expect } from '@playwright/test';

test('provider cards show lasting verification and actual errors without an hourly expiry', async ({ page }) => {
  await page.route('**/api/v1/session', route => route.fulfill({ json: { id: 'fixture', display_name: 'Tester', roles: ['Owner'], permissions: ['farm.inspect', 'provider.configure'], csrf_token: 'fixture', admin_origin: 'http://127.0.0.1:5173', user_origin: 'http://127.0.0.1:5174' } }));
  for (const endpoint of ['capabilities', 'capability-routes']) await page.route(`**/api/v1/${endpoint}`, route => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/v1/farm', route => route.fulfill({ json: { farm: { name: 'Fixture farm' }, members: [] } }));
  let state = 'configured';
  await page.route('**/api/v1/providers', route => route.fulfill({ json: { items: [{ id: 'qwen', name: 'Office model', model_id: 'resident-qwen', base_url: 'https://192.168.1.10:1234/v1', protocol: 'openai.chat.v1', revision: 2, state, features: ['chat', 'streaming', 'vision'], probed_at: '2026-01-01T12:00:00Z', verified_until: '2026-01-01T13:00:00Z', expired: true, pool_name: 'Office GPU', execution_state: 'idle', reason: state === 'failed' ? 'The model server is unreachable.' : state === 'configured' ? 'Checking the saved provider connection after startup.' : null }] } }));
  await page.goto('/#providers');
  await expect(page.getByText('Checking the saved provider connection after startup.')).toBeVisible();
  state = 'ready';
  await expect(page.getByText('Stays verified until a provider error', { exact: false })).toBeVisible();
  await expect(page.getByText('Verification expires', { exact: false })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Verify chat & vision' })).toBeVisible();
  state = 'failed';
  await page.reload();
  await expect(page.getByText('The model server is unreachable.')).toBeVisible();
  await expect(page.getByText('Stays verified until a provider error', { exact: false })).toHaveCount(0);
});

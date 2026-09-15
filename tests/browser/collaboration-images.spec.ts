// Interaction fixtures. Database isolation and real model transport are tested separately.
import { test, expect, type Page } from '@playwright/test';
import { resolve } from 'node:path';

async function workspace(page: Page) {
  await page.route('**/api/v1/session', route => route.fulfill({ json: { id: 'features-fixture', display_name: 'Local tester', roles: ['Owner'], permissions: ['conversation.own'], csrf_token: 'fixture-csrf', admin_origin: 'http://127.0.0.1:5173', user_origin: 'http://127.0.0.1:5174' } }));
  for (const endpoint of ['capabilities', 'chats', 'side-notes']) await page.route(`**/api/v1/${endpoint}`, route => route.fulfill({ json: { items: [] } }));
  await page.goto('http://127.0.0.1:5174');
  await page.getByLabel('Appearance').selectOption('dark');
}

test('channel join, keyboard posting, explicit mention and leave', async ({ page }) => {
  let joined = false;
  const messages = [{ id: 'earlier', role: 'user', display_name: 'A friend', content: 'How about a spaceship?', status: 'completed', reason: null }];
  await page.route('**/api/v1/channels', route => route.fulfill({ json: { items: [{ id: 'kitchen', name: 'Kitchen table', joined }] } }));
  await page.route('**/api/v1/channels/kitchen/join', async route => { joined = true; await route.fulfill({ json: { joined } }); });
  await page.route('**/api/v1/channels/kitchen/leave', async route => { joined = false; await route.fulfill({ json: { joined } }); });
  await page.route('**/api/v1/channels/kitchen', route => route.fulfill({ json: { id: 'kitchen', name: 'Kitchen table', revision: 1, messages } }));
  await page.route('**/api/v1/channels/kitchen/messages', async route => {
    const data = route.request().postDataJSON();
    expect(route.request().headers()['x-hearth-csrf']).toBe('fixture-csrf');
    messages.push({ id: data.request_id, role: 'user', display_name: 'Local tester', content: data.content, status: 'completed', reason: null });
    if (data.content.includes('@hearth')) messages.push({ id: 'reply', role: 'assistant', display_name: 'hearth', content: 'A little forest scout called Ember would fit right in.', status: 'completed', reason: null });
    await route.fulfill({ status: 201, json: { saved: true } });
  });
  await workspace(page);
  await page.getByRole('button', { name: 'Channels', exact: true }).click();
  await expect(page.getByText('How about a spaceship?', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: '# Kitchen table Join', exact: true }).click();
  await expect(page.getByLabel('Channel messages')).toContainText('How about a spaceship?');
  await page.getByLabel('Channel message', { exact: true }).fill('Something small and friendly.');
  await page.getByLabel('Channel message', { exact: true }).press('Enter');
  await expect(page.locator('.chat-message.assistant')).toHaveCount(0);
  await page.getByLabel('Channel message', { exact: true }).fill('@hearth what should we call it?');
  await page.getByLabel('Channel message', { exact: true }).press('Enter');
  await expect(page.locator('.chat-message.assistant')).toContainText('Ember');
  await page.screenshot({ path: 'evidence/inference/2026-09-13/channels-ui-fixture.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('button', { name: 'Leave channel', exact: true }).click();
  await expect(page.getByLabel('Channel messages')).toHaveCount(0);
});

test('image gallery progress, saved PNG and repeatable settings', async ({ page }) => {
  const jobs: Record<string, unknown>[] = [];
  let completed = false;
  await page.route('**/api/v1/image-targets', route => route.fulfill({ json: { items: [{ id: 'sdxl', name: 'hearth image provider', model_id: 'stabilityai/stable-diffusion-xl-base-1.0', ready: true }] } }));
  await page.route('**/api/v1/images', async route => {
    if (route.request().method() === 'POST') {
      const data = route.request().postDataJSON();
      expect(data.target_id).toBe('sdxl');
      expect(data.request.seed).toBe(451);
      expect(route.request().headers()['x-hearth-csrf']).toBe('fixture-csrf');
      jobs.push({ id: data.request.id, target_id: 'sdxl', request: data.request, status: 'running', progress: 8, cancel_requested: false, reason: null, metadata: null });
      await route.fulfill({ status: 202, json: { id: data.request.id, status: 'running' } });
    } else await route.fulfill({ json: { items: jobs.map(job => ({ ...job, status: completed ? 'completed' : 'running' })) } });
  });
  await page.route('**/api/v1/images/*/image', route => route.fulfill({ path: resolve('evidence/images/2026-09-13/sdxl-local-proof.png'), contentType: 'image/png' }));
  await workspace(page);
  await page.getByRole('button', { name: 'Images', exact: true }).click();
  await page.getByLabel('Describe your image').fill('A cozy stone cottage beneath the pines, warm windows, storybook illustration');
  await page.getByLabel('Seed', { exact: false }).fill('451');
  await page.getByRole('button', { name: 'Create image', exact: true }).click();
  await expect(page.getByRole('progressbar')).toHaveAttribute('value', '8');
  await expect(page.getByRole('button', { name: 'Stop image' })).toBeVisible();
  completed = true;
  await expect(page.getByRole('link', { name: 'Save PNG' })).toBeVisible({ timeout: 10000 });
  expect(jobs.length).toBe(1);
  await expect(page.locator('.image-card img')).toBeVisible();
  await page.getByRole('button', { name: 'Use settings' }).click();
  await expect(page.getByLabel('Seed', { exact: false })).toHaveValue('451');
  await expect(page.getByLabel('Describe your image')).toHaveValue('A cozy stone cottage beneath the pines, warm windows, storybook illustration');
  await page.screenshot({ path: 'evidence/images/2026-09-13/images-ui-fixture.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'evidence/images/2026-09-13/images-mobile-ui-fixture.png', fullPage: true });
});

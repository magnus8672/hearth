// Production-bundle UI fixtures; artifact erasure and authorization use VM PostgreSQL tests.
import { test, expect } from '@playwright/test';

const origin = process.env.HEARTH_BROWSER_ORIGIN || 'http://127.0.0.1:5174';
const request = { id: '00000000-0000-4000-8000-000000000091', model: 'fixture-image', prompt: 'A synthetic orange square', negative_prompt: '', seed: 42, steps: 20, shape: 'square' };

test('gallery deletion confirms, handles failures, removes the card and restores a chat tombstone', async ({ page }) => {
  let deleted = false, fail = true, deletes = 0;
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/v1/session', route => route.fulfill({ json: { id: 'deletion-fixture', display_name: 'Gallery tester', roles: ['Owner'], permissions: ['conversation.own', 'capability.image.generate'], csrf_token: 'fixture-csrf', admin_origin: origin, user_origin: origin } }));
  for (const name of ['capabilities', 'side-notes', 'chat-targets']) await page.route(`**/api/v1/${name}`, route => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/v1/image-targets', route => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/v1/chats', route => route.fulfill({ json: { items: [{ id: 'deletion-chat', title: 'Image deletion test', revision: 2 }] } }));
  await page.route('**/api/v1/chats/deletion-chat', route => route.fulfill({ json: {
    id: 'deletion-chat', title: 'Image deletion test', revision: 2, runs: [], pending: [], messages: [
      { id: 'human', role: 'user', content: 'Make an image of an orange square', status: 'completed' },
      { id: 'assistant', role: 'assistant', content: 'Generated image', status: 'completed', image: { request, status: deleted ? 'deleted' : 'completed', progress: 20, reason: deleted ? 'Image deleted.' : null } },
    ],
  } }));
  await page.route('**/api/v1/images', route => route.fulfill({ json: { items: deleted ? [] : [{ id: request.id, target_id: 'fixture', request, status: 'completed', progress: 20 }] } }));
  // The fixture is deliberately an innocuous one-pixel PNG, never a user's image.
  await page.route('**/api/v1/images/*/image', route => route.fulfill({ contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a1ioAAAAASUVORK5CYII=', 'base64') }));
  await page.route(`**/api/v1/images/${request.id}`, async route => {
    expect(route.request().method()).toBe('DELETE');
    expect(route.request().headers()['x-hearth-csrf']).toBe('fixture-csrf');
    deletes++;
    if (fail) await route.fulfill({ status: 409, json: { error: { message: 'Explicit deletion failure fixture.' } } });
    else { deleted = true; await route.fulfill({ json: { deleted: true } }); }
  });
  await page.goto(origin);
  await page.getByRole('button', { name: 'Images', exact: true }).click();
  const remove = page.getByRole('button', { name: 'Delete image', exact: true });
  await expect(remove).toBeVisible();
  page.once('dialog', async dialog => { expect(dialog.message()).toContain('cannot be undone'); await dialog.dismiss(); });
  await remove.click();
  expect(deletes).toBe(0);
  page.once('dialog', dialog => dialog.accept());
  await remove.click();
  await expect(page.getByRole('alert')).toContainText('Explicit deletion failure');
  await expect(remove).toBeEnabled();
  fail = false;
  page.once('dialog', dialog => dialog.accept());
  await remove.click();
  await expect(page.getByRole('status')).toHaveText('Image deleted.');
  await expect(page.locator('.image-card')).toHaveCount(0);
  expect(deletes).toBe(2);
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.locator('.image-card')).toHaveCount(0);
  await page.getByRole('button', { name: 'Private chat', exact: true }).click();
  await page.getByRole('button', { name: 'Image deletion test', exact: true }).click();
  await expect(page.locator('.conversation-image')).toHaveText('Image deleted.');
  await expect(page.locator('.conversation-image img')).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Save PNG' })).toHaveCount(0);
  await page.reload();
  await page.getByRole('button', { name: 'Image deletion test', exact: true }).click();
  await expect(page.locator('.conversation-image')).toHaveText('Image deleted.');
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

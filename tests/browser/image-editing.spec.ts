import { test, expect } from '@playwright/test';
import { createHash } from 'node:crypto';

const origin = process.env.HEARTH_BROWSER_ORIGIN || 'http://127.0.0.1:5174';
const picture = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a1ioAAAAASUVORK5CYII=', 'base64');

test('uploaded image edits keep pixels and request identity across retries and reject legacy providers', async ({ page }) => {
  const jobs: Record<string, any>[] = [];
  const submissions: Record<string, any>[] = [];
  await page.route('**/api/v1/session', route => route.fulfill({ json: { id: 'edit-fixture', display_name: 'Image tester', roles: ['Owner'], permissions: ['conversation.own', 'capability.image.generate'], csrf_token: 'fixture', admin_origin: origin, user_origin: origin } }));
  for (const name of ['chats', 'capabilities', 'side-notes']) await page.route(`**/api/v1/${name}`, route => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/v1/image-targets', route => route.fulfill({ json: { items: [
    { id: 'fooocus', name: 'Fooocus', model_id: 'fooocus/fixture', ready: true, profile: { shapes: ['square', 'landscape'], steps: [20], editing: 'fooocus-vary-v1' } },
    { id: 'legacy', name: 'Original provider', model_id: 'legacy', ready: true },
  ] } }));
  await page.route('**/api/v1/images', async route => {
    if (route.request().method() !== 'POST') return route.fulfill({ json: { items: jobs } });
    const data = route.request().postDataJSON(); submissions.push(data);
    expect(route.request().headers()['x-hearth-csrf']).toBe('fixture');
    expect(data.image).toBe(picture.toString('base64'));
    expect(data.request.edit).toEqual({ image_sha256: createHash('sha256').update(picture).digest('hex'), strength: 0.55 });
    if (submissions.length === 1) return route.fulfill({ status: 503, json: { error: { message: 'Temporary connection failure. Please retry.' } } });
    expect(data.request.id).toBe(submissions[0].request.id);
    jobs.push({ id: data.request.id, target_id: 'fooocus', request: data.request, status: 'queued', progress: 0 });
    return route.fulfill({ status: 202, json: { id: data.request.id } });
  });
  await page.goto(origin + '/#images');
  await page.getByRole('combobox', { name: 'Image task', exact: true }).selectOption('edit');
  await expect(page.getByRole('button', { name: 'Modify image', exact: true })).toBeDisabled();
  await page.getByLabel('Image to modify', { exact: true }).setInputFiles({ name: 'reference.png', mimeType: 'image/png', buffer: picture });
  await expect(page.getByAltText('Image selected for editing')).toBeVisible();
  await expect(page.getByText('reference.png', { exact: true })).toBeVisible();
  await page.getByLabel('Describe the result you want').fill('A blue ceramic toy on a white background');
  await page.getByRole('slider', { name: 'Edit strength' }).press('ArrowRight');
  await page.getByRole('combobox', { name: 'Image model', exact: true }).selectOption('legacy');
  await expect(page.getByText('Choose a Fooocus provider with image editing enabled.', { exact: false })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Modify image', exact: true })).toBeDisabled();
  await page.getByRole('combobox', { name: 'Image model', exact: true }).selectOption('fooocus');
  await page.getByRole('button', { name: 'Modify image', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Temporary connection failure');
  await expect(page.getByAltText('Image selected for editing')).toBeVisible();
  await page.getByRole('button', { name: 'Modify image', exact: true }).click();
  await expect(page.getByAltText('Image selected for editing')).toHaveCount(0);
  await expect(page.locator('.image-card')).toContainText('Edited from an upload · 55% strength');
  await page.getByRole('button', { name: 'Use settings', exact: true }).click();
  await expect(page.getByText('Settings restored. Choose an image to modify before sending.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Add to queue', exact: true })).toBeDisabled();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

import { test, expect } from '@playwright/test';

const origin = process.env.HEARTH_BROWSER_ORIGIN || 'http://127.0.0.1:5174';

test('advertised image settings submit, restore, and reset when switching to a legacy provider', async ({ page }) => {
  const jobs: Record<string, any>[] = [];
  const profile = { shapes: ['square', 'landscape', 'portrait', 'widescreen', 'tall'], steps: [20, 30, 40, 60], options: {
    resolutions: ['native', '2k', '4k'], styles: ['Fooocus V2', 'Fooocus Sharp', 'SAI Photographic'],
    default_styles: ['Fooocus V2', 'Fooocus Sharp'], guidance_scale: 4, sharpness: 2,
  } };
  await page.route('**/api/v1/session', route => route.fulfill({ json: { id: 'options-fixture', display_name: 'Image tester', roles: ['Owner'], permissions: ['conversation.own', 'capability.image.generate'], csrf_token: 'fixture-csrf', admin_origin: origin, user_origin: origin } }));
  for (const name of ['chats', 'capabilities', 'side-notes']) await page.route(`**/api/v1/${name}`, route => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/v1/image-targets', route => route.fulfill({ json: { items: [
    { id: 'fooocus', name: 'Fooocus', model_id: 'fooocus/fixture', ready: true, profile },
    { id: 'legacy', name: 'Original provider', model_id: 'legacy', ready: true, profile: { shapes: ['square', 'landscape', 'portrait'], steps: [20, 30, 40] } },
  ] } }));
  await page.route('**/api/v1/images', async route => {
    if (route.request().method() === 'POST') {
      const data = route.request().postDataJSON();
      expect(route.request().headers()['x-hearth-csrf']).toBe('fixture-csrf');
      expect(data.request.shape).toBe('widescreen');
      expect(data.request.steps).toBe(60);
      expect(data.request.options).toEqual({ resolution: '4k', styles: ['SAI Photographic'], guidance_scale: 5.5, sharpness: 0 });
      jobs.push({ id: data.request.id, target_id: 'fooocus', request: data.request, status: 'completed', metadata: { width: 3840, height: 2160 } });
      await route.fulfill({ status: 202, json: { id: data.request.id } });
    } else await route.fulfill({ json: { items: jobs } });
  });
  await page.route('**/api/v1/images/*/image', route => route.fulfill({ contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a1ioAAAAASUVORK5CYII=', 'base64') }));
  await page.goto(origin);
  await page.getByRole('button', { name: 'Images', exact: true }).click();
  await page.getByRole('combobox', { name: 'Shape', exact: true }).selectOption('widescreen');
  await page.getByRole('combobox', { name: 'Output resolution', exact: true }).selectOption('4k');
  await expect(page.getByRole('combobox', { name: 'Output resolution', exact: true }).locator('option:checked')).toContainText('3840 × 2160');
  await page.getByRole('combobox', { name: 'Detail passes', exact: true }).selectOption('60');
  await page.getByText('Style and advanced settings', { exact: true }).click();
  await page.getByLabel('Use provider default styles').uncheck();
  await page.getByRole('listbox', { name: 'Styles', exact: true }).selectOption(['SAI Photographic']);
  await page.getByLabel('Guidance scale').fill('5.5');
  await page.getByLabel('Sharpness', { exact: true }).fill('0');
  await page.getByLabel('Describe your image').fill('A red pickup in a pine forest');
  await page.getByRole('button', { name: 'Create image', exact: true }).click();
  await expect(page.locator('.image-card')).toContainText('3840 × 2160');
  await page.getByRole('button', { name: 'Use settings', exact: true }).click();
  await expect(page.getByRole('combobox', { name: 'Output resolution', exact: true })).toHaveValue('4k');
  await expect(page.getByRole('listbox', { name: 'Styles', exact: true })).toHaveValues(['SAI Photographic']);
  await expect(page.getByLabel('Sharpness', { exact: true })).toHaveValue('0');
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  if (process.env.HEARTH_IMAGE_OPTIONS_SCREENSHOT) await page.screenshot({ path: process.env.HEARTH_IMAGE_OPTIONS_SCREENSHOT, fullPage: true });
  await page.getByRole('combobox', { name: 'Image model', exact: true }).selectOption('legacy');
  await expect(page.getByRole('combobox', { name: 'Output resolution', exact: true })).toHaveCount(0);
  await expect(page.getByRole('combobox', { name: 'Shape', exact: true })).toHaveValue('square');
  await expect(page.getByRole('combobox', { name: 'Detail passes', exact: true })).toHaveValue('20');
});

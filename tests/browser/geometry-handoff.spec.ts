import { test, expect } from '@playwright/test';
import { createHash } from 'node:crypto';

const origin = process.env.HEARTH_BROWSER_ORIGIN || 'https://hearth.example.invalid';
const imageId = '00000000-0000-4000-8000-000000000091';
const request = { id: imageId, model: 'image-fixture', prompt: 'An original reference fixture', negative_prompt: '', shape: 'square', steps: 20, seed: 42 };

for (const surface of ['gallery', 'chat', 'channel'] as const) {
  test(`${surface} Make a model selects the image and submits its prepared reference`, async ({ page }) => {
    let submitted = 0;
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    // An original 4K-wide PNG over 8 MiB proves handoff prepares a smaller
    // reference copy instead of sending the original past the upload limit.
    await page.goto(origin + '/health/browser');
    const encoded = await page.evaluate(large => {
      const canvas = document.createElement('canvas'); canvas.width = large ? 4096 : 64; canvas.height = large ? 768 : 64;
      const context = canvas.getContext('2d')!; const pixels = context.createImageData(canvas.width, canvas.height);
      for (let offset = 0; offset < pixels.data.length; offset += 65536) crypto.getRandomValues(pixels.data.subarray(offset, offset + 65536));
      context.putImageData(pixels, 0, 0); return canvas.toDataURL('image/png').split(',')[1];
    }, surface === 'gallery');
    const artifact = Buffer.from(encoded, 'base64');
    if (surface === 'gallery') expect(artifact.length).toBeGreaterThan(8 * 1024 * 1024);
    await page.route('**/api/v1/session', route => route.fulfill({ json: { id: 'handoff-fixture', display_name: 'Tester', roles: ['Member'], permissions: ['conversation.own'], csrf_token: 'fixture', user_origin: origin, admin_origin: origin } }));
    for (const endpoint of ['capabilities', 'side-notes', 'image-targets']) await page.route(`**/api/v1/${endpoint}`, route => route.fulfill({ json: { items: [] } }));
    await page.route('**/api/v1/geometry-targets', route => route.fulfill({ json: { items: [{ id: 'gpu', model_id: 'trellis2/q8', name: 'Fixture', state: 'ready', profile: { resolutions: [512] } }] } }));
    await page.route('**/api/v1/geometry', async route => {
      if (route.request().method() === 'POST') {
        submitted++;
        const data = route.request().postDataJSON(); const bytes = Buffer.from(data.image, 'base64');
        expect(bytes.length).toBeLessThan(8 * 1024 * 1024);
        expect(bytes.subarray(0, 2).toString('hex')).toBe('ffd8');
        expect(data.request.image_sha256).toBe(createHash('sha256').update(bytes).digest('hex'));
        expect(route.request().headers()['x-hearth-csrf']).toBe('fixture');
        await route.fulfill({ status: 202, json: { id: data.request.id } });
      } else await route.fulfill({ json: { items: [] } });
    });
    const image = { request, status: 'completed', progress: 20, reason: null };
    await page.route('**/api/v1/images', route => route.fulfill({ json: { items: [{ ...image, id: imageId, target_id: 'image-fixture' }] } }));
    await page.route(`**/api/v1/images/${imageId}/image`, route => route.fulfill({ contentType: 'image/png', body: artifact }));
    await page.route(`**/api/v1/conversation-images/${imageId}/image`, route => route.fulfill({ contentType: 'image/png', body: artifact }));
    await page.route('**/api/v1/chats', route => route.fulfill({ json: { items: [{ id: 'chat', title: 'Reference test', revision: 1 }] } }));
    await page.route('**/api/v1/chats/chat', route => route.fulfill({ json: { id: 'chat', title: 'Reference test', revision: 1, runs: [], pending: [], messages: [{ id: 'reply', role: 'assistant', content: '', status: 'completed', image }] } }));
    await page.route('**/api/v1/channels', route => route.fulfill({ json: { items: [{ id: 'room', name: 'Reference room', joined: true }] } }));
    await page.route('**/api/v1/channels/room', route => route.fulfill({ json: { id: 'room', name: 'Reference room', revision: 1, messages: [{ id: 'reply', role: 'assistant', display_name: 'hearth', content: '', status: 'completed', image }] } }));
    await page.goto(origin + (surface === 'gallery' ? '/#images' : surface === 'chat' ? '/#chat' : '/#channels'));
    if (surface === 'chat') await page.getByRole('button', { name: 'Reference test' }).click();
    if (surface === 'channel') await page.getByRole('button', { name: '# Reference room Joined' }).click();
    const link = page.getByRole('link', { name: 'Make a model', exact: true });
    if (surface === 'chat') {
      await page.getByLabel('Your message', { exact: true }).fill('Keep this unsent thought');
      page.once('dialog', dialog => dialog.dismiss()); await link.click();
      await expect(page.getByLabel('Your message', { exact: true })).toHaveValue('Keep this unsent thought');
      page.once('dialog', dialog => dialog.accept());
    }
    await link.click();
    await expect(page).toHaveURL(origin + `/#geometry/${surface === 'gallery' ? 'gallery' : 'conversation'}/${imageId}`);
    const reference = page.getByRole('img', { name: 'Reference for your 3D model' });
    await expect(reference).toBeVisible();
    await expect(page.getByText('Your selected image is ready.', { exact: false })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Create 3D model' })).toBeEnabled();
    expect(submitted).toBe(0); // Navigation alone never starts GPU work.
    if (surface === 'gallery') await expect.poll(() => reference.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBe(1600);
    if (surface === 'chat') {
      await page.screenshot({ path: '.hearth/geometry-handoff.png', fullPage: true });
      await page.setViewportSize({ width: 390, height: 844 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    }
    await page.getByRole('button', { name: 'Create 3D model' }).click();
    await expect.poll(() => submitted).toBe(1);
    if (surface === 'chat') {
      await page.route('**/api/v1/conversation-images/*/image', route => route.fulfill({ status: 404, json: { error: { message: 'Unavailable fixture.' } } }));
      await page.evaluate(() => { window.location.hash = '#geometry/conversation/00000000-0000-4000-8000-000000000092'; });
      await expect(page.getByRole('alert')).toContainText('The selected image is no longer available to you.');
      await expect(page.getByRole('button', { name: 'Create 3D model' })).toBeDisabled();
    }
    expect(errors).toEqual([]);
  });
}

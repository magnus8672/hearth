import { browserOrigins } from './origins';
import { test, expect } from '@playwright/test';
import path from 'node:path';

const origin = browserOrigins.workspace;
const channel = '00000000-0000-4000-8000-000000000051';

test('live HTTPS edge permits channel image bodies up to the dedicated upload limit', async ({ page }) => {
  test.skip(process.env.HEARTH_BROWSER_LIVE_EDGE !== '1', 'Opt-in anonymous live edge checks; no account or stored data.');
  await page.goto(origin + '/health/browser');
  // No credentials: an accepted body must reach authentication and then fail.
  const statuses = await page.evaluate(async id => {
    const results = [];
    for (const [endpoint, size] of [['attachments', 2], ['attachments', 9], ['messages', 2]] as const) {
      const response = await fetch(`/api/v1/channels/${id}/${endpoint}`, { method: 'POST', credentials: 'omit', headers: { 'Content-Type': 'image/png' }, body: new Uint8Array(size * 1024 * 1024) });
      results.push(response.status);
    }
    return results;
  }, channel);
  expect([401, 403]).toContain(statuses[0]);
  expect(statuses.slice(1)).toEqual([413, 413]);
});
test.beforeEach(async ({ page }) => {
  if (process.env.HEARTH_BROWSER_LOCAL_BUILD !== '1') return;
  await page.route(origin + '/**', async route => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname !== '/' && !pathname.startsWith('/assets/')) return route.fallback();
    const file = path.resolve('apps/user-web/dist', '.' + (pathname === '/' ? '/index.html' : pathname));
    if (!file.startsWith(path.resolve('apps/user-web/dist') + path.sep)) return route.abort();
    await route.fulfill({ path: file });
  });
});

test('channel paste, file and drop drafts publish with model handoff; Enter retains focus and retry identity', async ({ page }) => {
  await page.goto(origin + '/health/browser');
  const png = await page.evaluate(() => {
    const canvas = document.createElement('canvas'); canvas.width = 64; canvas.height = 64;
    const ctx = canvas.getContext('2d')!; ctx.fillStyle = 'red'; ctx.fillRect(0, 0, 64, 64);
    return canvas.toDataURL('image/png').split(',')[1];
  });
  let draft: any[] = [], messages: any[] = [];
  let serial = 90, deny = false, posts = 0, geometryPosts = 0;
  const bodies: any[] = [];
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url()).pathname;
    const method = route.request().method();
    if (url.endsWith('/session')) return route.fulfill({ json: { id: 'fixture', display_name: 'Tester', roles: ['Member'], permissions: ['channel.use', 'capability.geometry.generate'], csrf_token: 'fixture', user_origin: origin, admin_origin: origin + ':8443' } });
    if (url === '/api/v1/channels') return route.fulfill({ json: { items: [{ id: channel, name: 'Pictures', joined: true }] } });
    if (url.endsWith('/attachments') && method === 'POST') {
      expect(route.request().headers()['x-hearth-csrf']).toBe('fixture');
      const item = { id: `00000000-0000-4000-8000-${String(serial++).padStart(12, '0')}`, width: 1, height: 1, byte_count: 68, media_type: 'image/png' };
      draft.push(item); return route.fulfill({ status: 201, json: item });
    }
    if (url.includes('/attachments/')) {
      if (method === 'DELETE') { draft = draft.filter(item => !url.endsWith(item.id)); return route.fulfill({ json: { deleted: true } }); }
      return route.fulfill({ contentType: 'image/png', body: Buffer.from(png, 'base64') });
    }
    if (url.endsWith('/messages') && method === 'POST') {
      posts++; const body = route.request().postDataJSON(); bodies.push(body);
      // Exercise a real pending render, rather than a synchronous fixture response.
      await new Promise(resolve => setTimeout(resolve, 150));
      if (deny) return route.fulfill({ status: 503, json: { error: { message: 'Try again fixture' } } });
      const attachments = draft.filter(item => body.attachment_ids.includes(item.id));
      messages.push({ id: String(posts), role: 'user', display_name: 'Tester', content: body.content, status: 'completed', attachments });
      draft = draft.filter(item => !body.attachment_ids.includes(item.id));
      return route.fulfill({ status: 201, json: { saved: true } });
    }
    if (url === `/api/v1/channels/${channel}`) return route.fulfill({ json: { id: channel, name: 'Pictures', revision: 1, unused_attachments: draft, messages } });
    if (url.endsWith('/geometry-targets')) return route.fulfill({ json: { items: [{ id: 'gpu', model_id: 'trellis2/q8', name: 'Fixture', state: 'ready', profile: { resolutions: [512] } }] } });
    if (url.endsWith('/geometry') && method === 'POST') { geometryPosts++; return route.fulfill({ status: 202, json: {} }); }
    return route.fulfill({ json: { items: [] } });
  });
  await page.goto(origin + '/#channels');
  await page.getByRole('button', { name: '# Pictures Joined' }).click();
  const composer = page.getByLabel('Channel message', { exact: true });
  await composer.fill('First message'); await composer.press('Enter');
  await expect(composer).toBeFocused();
  await expect(composer).toHaveValue('');
  await expect(page.getByRole('button', { name: 'Send to channel', exact: true })).toBeVisible();
  await expect(composer).toBeFocused();
  await page.keyboard.type('Second message'); await page.keyboard.press('Enter');
  await expect(composer).toHaveValue(''); await expect(composer).toBeFocused();
  await expect.poll(() => posts).toBe(2);
  await composer.evaluate((element, base64) => {
    const transfer = new DataTransfer(); transfer.items.add(new File([Uint8Array.from(atob(base64), c => c.charCodeAt(0))], 'pasted.png', { type: 'image/png' }));
    element.dispatchEvent(new ClipboardEvent('paste', { bubbles: true, cancelable: true, clipboardData: transfer }));
  }, png);
  await expect(page.getByRole('button', { name: 'Remove attached image 1' })).toBeEnabled();
  await page.getByLabel('Attach channel images').setInputFiles({ name: 'attached.png', mimeType: 'image/png', buffer: Buffer.from(png, 'base64') });
  await expect(page.getByRole('button', { name: 'Remove attached image 2' })).toBeEnabled();
  await page.locator('.chat-composer').evaluate((element, base64) => {
    const transfer = new DataTransfer(); transfer.items.add(new File([Uint8Array.from(atob(base64), c => c.charCodeAt(0))], 'dropped.png', { type: 'image/png' }));
    element.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: transfer }));
  }, png);
  await expect(page.getByRole('button', { name: 'Remove attached image 3' })).toBeEnabled();
  await page.getByRole('button', { name: 'Remove attached image 3' }).click();
  await expect(page.getByRole('button', { name: 'Remove attached image 3' })).toHaveCount(0);
  // Reload restores only this person's saved, unpublished drafts.
  page.once('dialog', dialog => dialog.accept()); await page.reload();
  await page.getByRole('button', { name: '# Pictures Joined' }).click();
  await expect(page.getByRole('button', { name: 'Remove attached image 2' })).toBeEnabled();
  deny = true;
  await composer.focus(); await composer.press('Enter');
  await expect(page.getByRole('alert')).toContainText('Try again');
  await expect(composer).toBeFocused();
  await expect(page.getByRole('button', { name: 'Remove attached image 2' })).toBeEnabled();
  deny = false; await composer.press('Enter');
  await expect(page.getByRole('link', { name: 'Generate model', exact: true })).toHaveCount(2);
  expect(bodies[2]).toEqual(bodies[3]);
  expect(bodies[3].content).toBe(''); expect(bodies[3].attachment_ids).toHaveLength(2);
  await expect(composer).toBeFocused();
  await composer.fill('Keep this draft');
  page.once('dialog', dialog => dialog.dismiss());
  await page.getByRole('link', { name: 'Generate model', exact: true }).first().click();
  await expect(composer).toHaveValue('Keep this draft');
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('link', { name: 'Generate model', exact: true }).first().click();
  await expect(page.getByRole('img', { name: 'Reference for your 3D model' })).toBeVisible();
  expect(geometryPosts).toBe(0);
  await page.getByLabel('Model name', { exact: true }).fill('Channel picture model');
  await page.getByRole('button', { name: 'Create 3D model' }).click();
  await expect.poll(() => geometryPosts).toBe(1);
});

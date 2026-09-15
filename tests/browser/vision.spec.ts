// Explicit UI fixtures. Real uploaded-pixel evidence is in the integration suite.
import { test, expect, type Page } from '@playwright/test';
import { resolve } from 'node:path';

async function identity(page: Page) {
  await page.route('**/api/v1/session', route => route.fulfill({ json: { id: 'vision-fixture', display_name: 'Tester', roles: ['Owner'], permissions: ['farm.inspect', 'conversation.own', 'provider.configure'], csrf_token: 'fixture-csrf', admin_origin: 'http://127.0.0.1:5173', user_origin: 'http://127.0.0.1:5174' } }));
  await page.route('**/api/v1/farm', route => route.fulfill({ json: { farm: { name: 'Fixture farm' }, members: [] } }));
  for (const name of ['capabilities', 'side-notes', 'capability-routes']) await page.route(`**/api/v1/${name}`, route => route.fulfill({ json: { items: [] } }));
}

test('upload, restore unsent pictures, remove, send to vision and restore saved pixels', async ({ page }) => {
  await identity(page);
  let created = false, uploads = 0, sends = 0, firstRead = true;
  let unused: Record<string, unknown>[] = [];
  const messages: Record<string, unknown>[] = [], runs: Record<string, unknown>[] = [];
  const result = () => ({ id: 'vision-chat', title: 'Look together', revision: sends ? 2 : 1, messages, runs, unused_attachments: unused });
  await page.route('**/api/v1/chats', async route => {
    if (route.request().method() === 'POST') { created = true; await route.fulfill({ status: 201, json: result() }); }
    else await route.fulfill({ json: { items: created ? [result()] : [] } });
  });
  await page.route('**/api/v1/chats/vision-chat', async route => {
    const snapshot = JSON.stringify(result());
    if (firstRead) { firstRead = false; await new Promise(resolve => setTimeout(resolve, 300)); }
    await route.fulfill({ contentType: 'application/json', body: snapshot });
  });
  await page.route('**/api/v1/chats/vision-chat/attachments', async route => {
    expect(route.request().headers()['x-hearth-csrf']).toBe('fixture-csrf');
    expect(route.request().postDataBuffer()!.byteLength).toBeGreaterThan(0);
    uploads++;
    const item = { id: `picture-${uploads}`, width: 480, height: 300, media_type: 'image/jpeg', byte_count: 1000 };
    unused.push(item);
    await route.fulfill({ status: 201, json: item });
  });
  await page.route('**/api/v1/chats/vision-chat/attachments/*', async route => {
    if (route.request().method() === 'DELETE') { unused = []; await route.fulfill({ json: { deleted: true } }); }
    else await route.fulfill({ path: resolve('evidence/vision/2026-09-13/vision-fixture.png'), contentType: 'image/png' });
  });
  await page.route('**/api/v1/chats/vision-chat/turns', async route => {
    const body = route.request().postDataJSON();
    expect(body.attachment_ids).toEqual(['picture-2']);
    expect(body.capability).toBe('auto');
    sends++;
    messages.push({ id: 'human', role: 'user', content: body.content, status: 'completed', attachments: [...unused] }, { id: 'answer', role: 'assistant', content: 'A red rectangle on the left and a blue circle on the right.', status: 'completed' });
    runs.push({ id: body.request_id, assistant_message_id: 'answer', capability_id: 'vision.describe', model_id: 'qwen/qwen3.8-27b', status: 'completed', finish_reason: 'stop' });
    unused = [];
    await route.fulfill({ status: 202, json: { id: body.request_id, status: 'running' } });
  });
  await page.goto('http://127.0.0.1:5174');
  await page.getByLabel('Attach images', { exact: true }).setInputFiles(resolve('evidence/vision/2026-09-13/vision-fixture.png'));
  await expect(page.locator('.chat-composer img')).toHaveCount(1);
  await page.reload();
  await expect(page.locator('.chat-composer img')).toHaveCount(1);
  await page.getByRole('button', { name: 'Remove attached image 1' }).click();
  await expect(page.locator('.chat-composer img')).toHaveCount(0);
  await page.getByLabel('Attach images', { exact: true }).setInputFiles(resolve('evidence/vision/2026-09-13/vision-fixture.png'));
  await expect(page.locator('.chat-composer img')).toHaveCount(1);
  await page.getByLabel('Your message', { exact: true }).fill('What shapes are in this image?');
  await page.getByLabel('Your message', { exact: true }).press('Enter');
  await expect(page.locator('.chat-message.assistant .reply-model')).toHaveText('qwen/qwen3.8-27b');
  await expect(page.locator('.chat-message.user img')).toBeVisible();
  await expect(page.locator('.chat-composer img')).toHaveCount(0);
  await page.reload();
  await expect(page.locator('.chat-message.user img')).toBeVisible();
  await expect(page.locator('.chat-message.assistant')).toContainText('blue circle');
  expect(sends).toBe(1);
  await page.getByLabel('Appearance').selectOption('dark');
  await page.screenshot({ path: 'evidence/vision/2026-09-13/chat-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'evidence/vision/2026-09-13/chat-mobile.png', fullPage: true });
});

test('vision provider verification sends the actual vision probe request', async ({ page }) => {
  await identity(page);
  let verified = false;
  await page.route('**/api/v1/providers', route => route.fulfill({ json: { items: [{ id: 'qwen', name: 'model-server', protocol: 'openai.chat.v1', model_id: 'qwen/qwen3.8-27b', base_url: 'http://10.20.30.40:1234/v1', allow_insecure_http: true, revision: verified ? 3 : 2, state: 'ready', expired: false, features: verified ? ['chat', 'streaming', 'vision'] : ['chat', 'streaming'], pool_name: 'Remote GPU', execution_state: 'idle' }] } }));
  await page.route('**/api/v1/providers/qwen/probe', async route => {
    expect(route.request().postDataJSON()).toEqual({ revision: 2, vision: true });
    verified = true;
    await route.fulfill({ json: { state: 'ready', reason: null, features: ['chat', 'streaming', 'vision'] } });
  });
  await page.goto('http://127.0.0.1:5173/#providers');
  await page.getByRole('button', { name: 'Verify vision', exact: true }).click();
  await expect(page.getByText('Vision, text and streaming verified.', { exact: false })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Verify chat & vision' })).toBeVisible();
});

// Explicit UI fixtures. Real stream/SQL evidence is recorded separately.
import { test, expect, type Page } from '@playwright/test';

async function identity(page: Page) {
  await page.route('**/api/v1/session', route => route.fulfill({ json: { id: 'reply-fixture', display_name: 'Tester', roles: ['Owner'], permissions: ['conversation.own'], csrf_token: 'fixture-csrf', admin_origin: 'http://127.0.0.1:5173', user_origin: 'http://127.0.0.1:5174' } }));
  for (const endpoint of ['capabilities', 'side-notes']) await page.route(`**/api/v1/${endpoint}`, route => route.fulfill({ json: { items: [] } }));
}

test('each reply keeps its model on reload and continuation keeps the specialist', async ({ page }) => {
  await identity(page);
  let continued = false;
  const conversation = { id: 'reply-history', title: 'Fibonacci', revision: 3,
    messages: [
      { id: 'old', role: 'assistant', content: 'Older reply without a receipt.', status: 'completed' },
      { id: 'greeting', role: 'assistant', content: 'Good afternoon!', status: 'completed' },
      { id: 'question', role: 'user', content: 'Write a Fibonacci script.', status: 'completed' },
      { id: 'code', role: 'assistant', content: 'Here is a Python script for the first', status: 'completed' },
    ],
    runs: [
      { id: 'gpt-run', assistant_message_id: 'greeting', model_id: 'openai/gpt-oss-20b', capability_id: 'chat.general', status: 'completed', finish_reason: 'stop' },
      { id: 'qwen-run', assistant_message_id: 'code', model_id: 'qwen/qwen3.8-27b', capability_id: 'code.implement', status: 'completed', finish_reason: 'length' },
    ],
  };
  await page.route('**/api/v1/chats', route => route.fulfill({ json: { items: [conversation] } }));
  await page.route('**/api/v1/chats/reply-history', route => route.fulfill({ json: conversation }));
  await page.route('**/api/v1/chats/reply-history/turns', async route => {
    const data = route.request().postDataJSON();
    expect(data.capability).toBe('code.implement');
    expect(data.content).toContain('Continue your previous reply');
    expect(data.revision).toBe(3);
    expect(data.request_id).toBeTruthy();
    continued = true;
    await route.fulfill({ status: 202, json: { id: data.request_id, status: 'running' } });
  });
  await page.goto('http://127.0.0.1:5174');
  await page.getByRole('button', { name: 'Fibonacci', exact: true }).click();
  const replies = page.locator('.chat-message.assistant');
  await expect(replies.nth(0).locator('.reply-model')).toHaveText('Model not recorded');
  await expect(replies.nth(1).locator('.reply-model')).toHaveText('openai/gpt-oss-20b');
  await expect(replies.nth(2).locator('.reply-model')).toHaveText('qwen/qwen3.8-27b');
  await expect(replies.nth(2)).toContainText('may be incomplete');
  await expect(page.locator('.chat-message.user .reply-model')).toHaveCount(0);
  await page.reload();
  await expect(replies.nth(1).locator('.reply-model')).toHaveText('openai/gpt-oss-20b');
  await page.getByLabel('Appearance').selectOption('dark');
  await page.screenshot({ path: 'evidence/replies/2026-09-13/desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'evidence/replies/2026-09-13/mobile.png', fullPage: true });
  await page.getByLabel('Your message', { exact: true }).fill('Unsent draft');
  await expect(page.getByRole('button', { name: 'Continue reply' })).toBeDisabled();
  await page.getByLabel('Your message', { exact: true }).fill('');
  await page.getByRole('button', { name: 'Continue reply' }).click();
  expect(continued).toBe(true);
});

test('channel replies show the shared model identity and image model', async ({ page }) => {
  await identity(page);
  await page.route('**/api/v1/chats', route => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/v1/channels', route => route.fulfill({ json: { items: [{ id: 'room', name: 'Workshop', joined: true }] } }));
  const image = { request: { id: 'picture', model: 'sdxl-fixture', prompt: 'A red Jeep', seed: 42, shape: 'square', steps: 20 }, status: 'running', progress: 2 };
  await page.route('**/api/v1/channels/room', route => route.fulfill({ json: { id: 'room', name: 'Workshop', revision: 1, messages: [
    { id: 'answer', role: 'assistant', display_name: 'hearth', model_id: 'qwen/qwen3.8-27b', content: 'A useful answer.', status: 'completed' },
    { id: 'image', role: 'assistant', display_name: 'hearth', model_id: 'planner-fixture', content: '', status: 'running', images: [image] },
  ] } }));
  await page.goto('http://127.0.0.1:5174');
  await page.getByRole('button', { name: 'Channels', exact: true }).click();
  await page.getByRole('button', { name: '# Workshop Joined', exact: true }).click();
  await expect(page.locator('.reply-model').nth(0)).toHaveText('qwen/qwen3.8-27b');
  await expect(page.locator('.reply-model').nth(1)).toHaveText('sdxl-fixture');
});

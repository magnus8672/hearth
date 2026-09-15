import { test, expect, type Page } from '@playwright/test';

async function setup(page: Page, thinking = 'Let me consider the garden layout.') {
  const conversation = { id: 'thinking-chat', title: 'Garden project', revision: 2,
    messages: [{ id: 'question', role: 'user', content: 'Help plan my garden.', status: 'completed' }, { id: 'reply', role: 'assistant', content: '', status: 'running' }],
    runs: [{ id: 'thinking-run', assistant_message_id: 'reply', status: 'running', cancel_requested: false, model_id: 'local-qwen', reasoning_text: thinking, reasoning_truncated: false, stream_phase: thinking ? 'reasoning' : 'waiting' }],
    pending: [] as { id: string; content: string; state: string; reason: null }[] };
  let notes: { id: string; content: string; revision: number }[] = [];
  await page.route('**/api/v1/session', route => route.fulfill({ json: { id: 'fixture', display_name: 'Tester', roles: ['Member'], permissions: ['conversation.own'], csrf_token: 'fixture', admin_origin: 'http://127.0.0.1:5173', user_origin: 'http://127.0.0.1:5174' } }));
  await page.route('**/api/v1/capabilities', route => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/v1/chats', route => route.fulfill({ json: { items: [conversation] } }));
  await page.route('**/api/v1/chats/thinking-chat', route => route.fulfill({ json: conversation }));
  await page.route('**/api/v1/chats/thinking-chat/transcriptions', route => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/v1/side-notes', async route => {
    if (route.request().method() === 'POST') { notes.push({ ...route.request().postDataJSON(), revision: 1 }); await route.fulfill({ status: 201, json: notes.at(-1) }); }
    else await route.fulfill({ json: { items: notes } });
  });
  await page.goto('http://127.0.0.1:5174');
  await page.getByRole('button', { name: 'Garden project', exact: true }).click();
  return { conversation, notes: () => notes, clearNotes: () => { notes = []; } };
}

test('thinking expands live, renders plain text, preserves reading position and restores separately', async ({ page }) => {
  const hostile = '<img src=x onerror="document.body.dataset.injected=\'yes\'">';
  const { conversation } = await setup(page, hostile+'\nInitial thinking.');
  const panel = page.locator('.thinking-panel');
  await expect(panel).toBeVisible();
  await expect(panel).not.toHaveAttribute('open');
  await panel.locator('summary').focus();
  await page.keyboard.press('Enter');
  await expect(panel).toHaveAttribute('open');
  await expect(page.getByLabel('Model thinking')).toContainText(hostile);
  await expect(panel.locator('img')).toHaveCount(0);
  await expect(page.locator('body')).not.toHaveAttribute('data-injected');
  const composer = page.locator('#chat-message');
  await composer.fill('Leave room for tomatoes.');
  conversation.runs[0].reasoning_text += '\n'+Array.from({ length: 40 }, (_, i) => `Considering garden row ${i}.`).join('\n');
  await expect(page.getByLabel('Model thinking')).toContainText('row 39.');
  await expect(panel).toHaveAttribute('open');
  await expect(composer).toHaveValue('Leave room for tomatoes.');
  const text = page.getByLabel('Model thinking');
  await expect.poll(() => text.evaluate(element => element.scrollHeight-element.scrollTop-element.clientHeight)).toBeLessThan(5);
  await text.evaluate(element => { element.scrollTop = 0; element.dispatchEvent(new Event('scroll', { bubbles: true })); });
  conversation.runs[0].reasoning_text += '\nA later thought arrives.';
  await expect(text).toContainText('A later thought arrives.');
  expect(await text.evaluate(element => element.scrollTop)).toBe(0);
  conversation.messages[1].content = 'Put tomatoes along the south side.';
  conversation.messages[1].status = 'completed';
  conversation.runs[0].status = 'completed';
  conversation.runs[0].stream_phase = 'answer';
  conversation.runs[0].reasoning_truncated = true;
  await expect(page.locator('.message-text').last()).toHaveText('Put tomatoes along the south side.');
  await expect(panel.locator('summary')).toHaveText('Thinking');
  await expect(panel).toHaveAttribute('open');
  await expect(panel).toContainText('Only the first part');
  await composer.fill('');
  await page.reload();
  await expect(panel).not.toHaveAttribute('open');
  await panel.locator('summary').click();
  await expect(text).toContainText('Initial thinking.');
  await expect(page.getByRole('alert')).toHaveCount(0);
  conversation.runs[0].reasoning_text = 'The garden needs sunny space for vegetables.\nI should leave a clear path and place the tomatoes along the south side.';
  conversation.runs[0].reasoning_truncated = false;
  await expect(text).toContainText('The garden needs sunny space');
  await page.getByLabel('Appearance').selectOption('dark');
  await page.getByLabel('Conversation messages').evaluate(element => { element.scrollTop = element.scrollHeight; });
  await page.screenshot({ path: 'evidence/thinking/2026-09-13/desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(panel.locator('summary')).toBeVisible();
  await page.screenshot({ path: 'evidence/thinking/2026-09-13/mobile.png', fullPage: true });
});

for (const source of ['composer', 'note'] as const) {
  test(`steer from ${source} while thinking is expanded`, async ({ page }) => {
    const fixture = await setup(page);
    const { conversation } = fixture;
    let sends = 0;
    await page.route('**/api/v1/chats/thinking-chat/turns', async route => {
      sends++;
      const data = route.request().postDataJSON();
      expect(data.interrupt_run_id).toBe('thinking-run');
      expect(data.content).toBe('Make it a vegetable garden.');
      expect(route.request().headers()['x-hearth-csrf']).toBe('fixture');
      if (source === 'note') { expect(data.note_id).toBe(fixture.notes()[0].id); expect(data.note_revision).toBe(1); fixture.clearNotes(); }
      conversation.runs[0].cancel_requested = true;
      conversation.pending = [{ id: data.request_id, content: data.content, state: 'queued', reason: null }];
      await route.fulfill({ status: 202, json: { id: data.request_id, status: 'queued' } });
    });
    await page.locator('.thinking-panel summary').click();
    await expect(page.getByLabel('Model thinking')).toBeVisible();
    if (source === 'composer') {
      await page.getByPlaceholder('Give a new direction…').fill('Make it a vegetable garden.');
      await page.getByPlaceholder('Give a new direction…').press('Enter');
    } else {
      await page.getByLabel('New side note').fill('Make it a vegetable garden.');
      await page.getByLabel('New side note').press('Enter');
      await page.getByRole('button', { name: 'Steer with this' }).click();
    }
    await expect(page.locator('.queued-message')).toContainText('Make it a vegetable garden.');
    await expect(page.locator('.thinking-panel summary')).toContainText('stopped');
    await expect(page.getByLabel('Model thinking')).toBeVisible();
    expect(sends).toBe(1);
  });
}

test('providers without reasoning show honest waiting text and no invented thinking', async ({ page }) => {
  const { conversation } = await setup(page, '');
  await expect(page.getByText('Waiting for the model…', { exact: true })).toBeVisible();
  await expect(page.locator('.thinking-panel')).toHaveCount(0);
  conversation.messages[1].content = 'A direct answer.';
  conversation.messages[1].status = 'completed';
  conversation.runs[0].status = 'completed';
  await expect(page.getByText('A direct answer.', { exact: true })).toBeVisible();
  await expect(page.locator('.thinking-panel')).toHaveCount(0);
});

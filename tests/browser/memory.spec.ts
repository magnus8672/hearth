import { test, expect } from '@playwright/test';

test('private memory can be edited, imported, paused, and opened from a reply source', async ({ page }) => {
  const id = '8c4dfc6a-9721-415f-a841-c192b1d5da7b';
  let note = { id, title: 'Workshop telescope', body: 'My telescope is named Juniper.', kind: 'note', enabled: true, revision: 1 };
  let settings = { enabled: true, revision: 1, generation: 3, projected_generation: 3, projected_at: '2026-09-13T12:00:00Z', projection_error: null };
  let imported = false;
  await page.route('**/api/v1/session', route => route.fulfill({ json: { id: 'explicit-memory-fixture', display_name: 'Local tester', roles: ['Member'], permissions: ['conversation.own'], csrf_token: 'fixture-csrf', admin_origin: 'http://127.0.0.1:5173', user_origin: 'http://127.0.0.1:5174' } }));
  await page.route('**/api/v1/capabilities', route => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/v1/memory', route => route.fulfill({ json: { settings, notes: [note], counts: { messages: 47, conversations: 2 }, vault_projection: true } }));
  await page.route('**/api/v1/memory/history?*', route => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/v1/memory/search?*', route => route.fulfill({ json: { items: [{ ...note, content: note.body, type: 'note' }] } }));
  await page.route(`**/api/v1/memory/notes/${id}`, async route => {
    if (route.request().method() === 'PUT') {
      expect(route.request().headers()['x-hearth-csrf']).toBe('fixture-csrf');
      const body = route.request().postDataJSON();
      expect(body.revision).toBe(note.revision);
      note = { ...note, ...body, revision: note.revision+1 };
    }
    await route.fulfill({ json: { ...note, revisions: [{ revision: note.revision, body: note.body, origin: 'workspace' }] } });
  });
  await page.route('**/api/v1/memory/settings', async route => {
    const body = route.request().postDataJSON();
    expect(body.revision).toBe(settings.revision);
    settings = { ...settings, enabled: body.enabled, revision: settings.revision+1 };
    await route.fulfill({ json: { saved: true } });
  });
  await page.route('**/api/v1/memory/import', async route => {
    expect(route.request().postDataJSON().markdown).toContain('Maple');
    imported = true; note = { ...note, body: 'My telescope is named Maple.', revision: note.revision+1 };
    await route.fulfill({ json: { type: 'note', source: note } });
  });
  await page.goto(`http://127.0.0.1:5174/#memory/note/${id}`);
  await expect(page.getByRole('heading', { name: 'Keep what matters.' })).toBeVisible();
  await expect(page.getByLabel('Memory text', { exact: true })).toHaveValue(note.body);
  await page.getByLabel('Memory text', { exact: true }).fill('My telescope is named Juniper and has a 200mm mirror.');
  await page.getByRole('button', { name: 'Save memory', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Saved.' })).toBeVisible();
  expect(note.revision).toBe(2);
  await page.getByLabel('Use memory across private chats').uncheck();
  await expect(page.getByLabel('Use memory across private chats')).not.toBeChecked();
  expect(settings.enabled).toBe(false);
  await expect(page.getByRole('link', { name: 'Download Obsidian vault' })).toHaveAttribute('href', '/api/v1/memory/vault.zip');
  await page.getByLabel('Import edited Markdown').setInputFiles({ name: 'note.md', mimeType: 'text/markdown', buffer: Buffer.from('My telescope is named Maple.') });
  await expect(page.getByLabel('Review the file before importing')).toHaveValue('My telescope is named Maple.');
  expect(imported).toBe(false);
  await page.getByRole('button', { name: 'Apply Markdown edit' }).click();
  await expect(page.getByLabel('Memory text', { exact: true })).toHaveValue('My telescope is named Maple.');
  expect(imported).toBe(true);
  await page.getByLabel('Appearance').selectOption('dark');
  await page.screenshot({ path: 'evidence/memory/2026-09-13/memory-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByLabel('Memory text', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'evidence/memory/2026-09-13/memory-mobile.png', fullPage: true });
});

test('memory receipt is attached to the reply and opens its authenticated source', async ({ page }) => {
  const note = '34d6bd0c-9b7e-4327-9e44-2d6600e0c416';
  await page.route('**/api/v1/session', route => route.fulfill({ json: { id: 'fixture', display_name: 'Tester', roles: ['Member'], permissions: ['conversation.own'], csrf_token: 'fixture', admin_origin: 'http://127.0.0.1:5173', user_origin: 'http://127.0.0.1:5174' } }));
  await page.route('**/api/v1/capabilities', route => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/v1/chats', route => route.fulfill({ json: { items: [{ id: 'chat', title: 'My telescope', revision: 2 }] } }));
  await page.route('**/api/v1/chats/chat', route => route.fulfill({ json: { id: 'chat', title: 'My telescope', revision: 2, messages: [{ id: 'answer', role: 'assistant', content: 'Your telescope is Juniper.', status: 'completed' }], runs: [{ id: 'run', assistant_message_id: 'answer', status: 'completed', model_id: 'local-model', memory_receipt: { sources: [{ id: note, type: 'note', title: 'Workshop', revision: 2 }], older_messages: 34, enabled: true } }] } }));
  await page.route('**/api/v1/side-notes', route => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/v1/memory', route => route.fulfill({ json: { settings: { enabled: true, revision: 1 }, counts: { messages: 36, conversations: 1 }, notes: [] } }));
  await page.route('**/api/v1/memory/search?*', route => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/v1/memory/history?*', route => route.fulfill({ json: { items: [] } }));
  await page.route(`**/api/v1/memory/notes/${note}`, route => route.fulfill({ json: { id: note, title: 'Workshop', body: 'My telescope is Juniper.', revision: 2, enabled: true, kind: 'note' } }));
  await page.goto('http://127.0.0.1:5174');
  await page.getByRole('button', { name: 'My telescope', exact: true }).click();
  await page.getByText('Memory used · 1 sources').click();
  await expect(page.getByText('34 older messages', { exact: false })).toBeVisible();
  await page.getByRole('link', { name: 'Workshop' }).click();
  await expect(page.getByLabel('Memory text', { exact: true })).toHaveValue('My telescope is Juniper.');
});

for (const [searchStatus, label] of [
  ['no_matches', 'No matching memories were supplied for this reply.'],
  ['paused', 'Memory recall was paused for this reply.'],
  ['context_full', 'Matching memories did not fit this reply’s context.'],
] as const) {
  test(`reply explains memory status: ${searchStatus}`, async ({ page }) => {
    await page.route('**/api/v1/session', route => route.fulfill({ json: { id: 'fixture', display_name: 'Tester', roles: ['Member'], permissions: ['conversation.own'], csrf_token: 'fixture' } }));
    await page.route('**/api/v1/capabilities', route => route.fulfill({ json: { items: [] } }));
    await page.route('**/api/v1/side-notes', route => route.fulfill({ json: { items: [] } }));
    await page.route('**/api/v1/chats', route => route.fulfill({ json: { items: [{ id: 'chat', title: 'Recall check', revision: 2 }] } }));
    await page.route('**/api/v1/chats/chat', route => route.fulfill({ json: { id: 'chat', title: 'Recall check', revision: 2, messages: [{ id: 'answer', role: 'assistant', content: 'A local reply.', status: 'completed' }], runs: [{ id: 'run', assistant_message_id: 'answer', status: 'completed', model_id: 'local-model', memory_receipt: { sources: [], older_messages: 0, enabled: searchStatus !== 'paused', search_status: searchStatus } }] } }));
    await page.goto('http://127.0.0.1:5174');
    await page.getByRole('button', { name: 'Recall check', exact: true }).click();
    await expect(page.getByText(label, { exact: true })).toBeVisible();
    await expect(page.getByText('Memory used', { exact: false })).toHaveCount(0);
  });
}

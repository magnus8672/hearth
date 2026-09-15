// UI interaction fixtures only. Real database, transport and identity evidence
// are recorded separately; these routes do not establish server authorization.
import { test, expect, type Page } from '@playwright/test';

async function identity(page: Page) {
  await page.route('**/api/v1/session', route => route.fulfill({ json: { id: 'explicit-ui-fixture', display_name: 'Local tester', roles: ['Owner'], permissions: ['farm.inspect', 'provider.configure', 'conversation.own'], csrf_token: 'explicit-fixture-csrf', admin_origin: 'http://127.0.0.1:5173', user_origin: 'http://127.0.0.1:5174' } }));
  await page.route('**/api/v1/capabilities', route => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/v1/farm', route => route.fulfill({ json: { farm: { name: 'Local test farm' }, members: [] } }));
  await page.route('**/api/v1/capability-routes', route => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/v1/side-notes', route => route.fulfill({ json: { items: [] } }));
}

test('capability assignments persist ordered providers and connection edits require new verification', async ({ page }) => {
  await identity(page);
  const base = { protocol: 'openai.chat.v1', revision: 2, state: 'ready', expired: false, features: ['chat', 'streaming'], reason: null, pool_name: 'Shared local GPU', resource_pool_id: 'pool', execution_state: 'idle', active_run_id: null, lease_until: null, verified_until: null };
  let models = [{ ...base, id: 'first', name: 'Office', base_url: 'http://127.0.0.1:1234/v1', model_id: 'office-model' }, { ...base, id: 'second', name: 'Workshop', base_url: 'https://192.168.1.40:1240/v1', model_id: 'workshop-model' }];
  let saved = { capability_id: 'reason.plan', display_name: 'Planning', revision: 1, profile: { protocol: 'openai.chat.v1', executable: true, scope: 'Text replies. Task quality still needs testing.' }, targets: [] as { target_id: string; priority: number; ready: boolean; reason: string }[] };
  let edits = 0;
  let probes = 0;
  await page.route('**/api/v1/providers', route => route.fulfill({ json: { items: models } }));
  await page.route('**/api/v1/capability-routes', route => route.fulfill({ json: { items: [{ capability_id: 'chat.general', display_name: 'Conversation', revision: 1, profile: saved.profile, targets: [] }, saved] } }));
  await page.route('**/api/v1/capability-routes/reason.plan', async route => {
    const data = route.request().postDataJSON();
    expect(route.request().method()).toBe('PUT');
    expect(data.revision).toBe(saved.revision);
    saved = { ...saved, revision: saved.revision + 1, targets: data.targets.map((item: { target_id: string; priority: number }) => ({ ...item, ready: true, reason: 'Text verified' })) };
    await route.fulfill({ json: saved });
  });
  await page.route('**/api/v1/providers/first', async route => {
    const data = route.request().postDataJSON();
    expect(data.revision).toBe(2);
    expect(data.base_url).toBe('https://192.168.1.60:1240/v1');
    expect(data.local_only).toBe(true);
    edits++;
    models = models.map(item => item.id === 'first' ? { ...item, base_url: data.base_url, revision: 3, state: 'configured', features: [] } : item);
    await route.fulfill({ json: { id: 'first', revision: 3, state: 'configured' } });
  });
  await page.route('**/api/v1/providers/first/probe', async route => {
    expect(route.request().postDataJSON().revision).toBe(3);
    probes++;
    await route.fulfill({ json: { state: 'ready', reason: null } });
  });
  await page.goto('http://127.0.0.1:5173');
  await page.getByRole('button', { name: 'Providers', exact: true }).click();
  await page.getByLabel('Capability', { exact: true }).selectOption('reason.plan');
  await page.getByRole('button', { name: 'Add provider choice' }).click();
  await page.getByLabel('First choice', { exact: true }).selectOption('first');
  await page.getByRole('button', { name: 'Add provider choice' }).click();
  await page.getByLabel('Next choice 2').selectOption('second');
  await page.getByRole('button', { name: 'Move choice 2 earlier' }).click();
  await page.getByRole('button', { name: 'Save assignment' }).click();
  await expect(page.getByText('Route saved. Only verified models will receive requests.')).toBeVisible();
  expect(saved.targets.map(item => item.target_id)).toEqual(['second', 'first']);
  expect(saved.targets.map(item => item.priority)).toEqual([100, 99]);
  expect(probes).toBe(0);
  await page.reload();
  await page.getByLabel('Capability', { exact: true }).selectOption('reason.plan');
  await expect(page.getByLabel('First choice', { exact: true })).toHaveValue('second');
  await page.getByLabel('Appearance').selectOption('dark');
  await page.screenshot({ path: 'evidence/routing/2026-09-13/assignment-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'evidence/routing/2026-09-13/assignment-mobile.png', fullPage: true });
  await page.locator('.target-card').filter({ has: page.getByRole('heading', { name: 'Office', exact: true }) }).getByRole('button', { name: 'Edit connection' }).click();
  await page.getByLabel('Server address').fill('https://192.168.1.60:1240/v1');
  await page.getByLabel('I trust this local server', { exact: false }).check();
  await page.getByRole('button', { name: 'Save & verify model' }).click();
  await expect(page.getByText('Text and streaming verified. Saved capability assignments can use this model.')).toBeVisible();
  expect(edits).toBe(1); expect(probes).toBe(1);
});

test('provider form verifies an existing service and keeps tools unverified', async ({ page }) => {
  await identity(page);
  let registered = false;
  let verified = false;
  const target = { id: 'fixture-target', name: 'LM Studio', base_url: 'http://127.0.0.1:1234/v1', model_id: 'openai/gpt-oss-20b', revision: 1, state: 'configured', expired: false, features: [], reason: null, pool_name: 'Shared local GPU', resource_pool_id: 'fixture-pool', execution_state: 'idle', active_run_id: null, lease_until: null, verified_until: null };
  await page.route('**/api/v1/providers', async route => {
    if (route.request().method() === 'POST') {
      expect(route.request().postDataJSON().local_only).toBe(true);
      expect(route.request().headers()['x-hearth-csrf']).toBe('explicit-fixture-csrf');
      registered = true;
      await route.fulfill({ status: 201, json: target });
    } else await route.fulfill({ json: { items: registered ? [{ ...target, state: verified ? 'ready' : 'configured', features: verified ? ['chat', 'streaming'] : [] }] : [] } });
  });
  await page.route('**/api/v1/providers/fixture-target/probe', async route => { verified = true; await route.fulfill({ json: { state: 'ready', reason: null } }); });
  await page.goto('/');
  await page.getByRole('button', { name: 'Providers', exact: true }).click();
  await page.getByLabel('Connection name').fill('LM Studio');
  await page.getByLabel('Server address').fill('http://127.0.0.1:1234');
  await page.getByLabel('Model identifier').fill('openai/gpt-oss-20b');
  await page.getByLabel('Resource group', { exact: true }).fill('Local GPU');
  await expect(page.getByRole('button', { name: 'Connect & verify chat' })).toBeDisabled();
  await page.getByLabel('I trust this local server', { exact: false }).check();
  await page.getByRole('button', { name: 'Connect & verify chat' }).click();
  await expect(page.getByText('Text and streaming verified.', { exact: false })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Verify tool calling' })).toBeVisible();
  await expect(page.getByText('In development', { exact: true })).toBeVisible();
  await page.getByLabel('Appearance').selectOption('dark');
  await page.screenshot({ path: 'evidence/routing/2026-09-13/providers-ui-fixture.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'evidence/routing/2026-09-13/providers-mobile-ui-fixture.png', fullPage: true });
});

test('chat sends once, shows incremental plain text and restores saved replies', async ({ page }) => {
  await identity(page);
  let sends = 0;
  let created = false;
  let completed = false;
  const reply = 'A small beginning can become something lovely.\n<script>window.modelExecuted = true</script>';
  const conversation = { id: 'fixture-conversation', title: 'A small beginning', revision: 1, messages: [] as { id: string; role: string; content: string; status: string }[], runs: [] as { id: string; status: string; cancel_requested: boolean; reason: null; finish_reason: string | null; model_id: string }[] };
  await page.route('**/api/v1/chats', async route => {
    if (route.request().method() === 'POST') { created = true; await route.fulfill({ status: 201, json: conversation }); }
    else await route.fulfill({ json: { items: created ? [conversation] : [] } });
  });
  await page.route('**/api/v1/chats/fixture-conversation', route => route.fulfill({ json: { ...conversation, messages: conversation.messages.map(item => item.role === 'assistant' ? { ...item, content: completed ? reply : 'A small beginning', status: completed ? 'completed' : 'running' } : item), runs: conversation.runs.map(item => ({ ...item, status: completed ? 'completed' : 'running', finish_reason: completed ? 'stop' : null })) } }));
  await page.route('**/api/v1/chats/fixture-conversation/turns', async route => {
    sends++;
    expect(route.request().headers()['x-hearth-csrf']).toBe('explicit-fixture-csrf');
    conversation.revision++;
    conversation.messages = [{ id: 'user', role: 'user', content: route.request().postDataJSON().content, status: 'completed' }, { id: 'assistant', role: 'assistant', content: '', status: 'running' }];
    conversation.runs = [{ id: route.request().postDataJSON().request_id, status: 'running', cancel_requested: false, reason: null, finish_reason: null, model_id: 'openai/gpt-oss-20b' }];
    await route.fulfill({ status: 202, json: { id: conversation.runs[0].id, status: 'running' } });
  });
  await page.goto('http://127.0.0.1:5174');
  await page.getByLabel('Your message', { exact: true }).fill('Give me a little encouragement for a new side project.');
  await page.getByLabel('Your message', { exact: true }).press('Shift+Enter');
  await expect(page.getByLabel('Your message', { exact: true })).toHaveValue('Give me a little encouragement for a new side project.\n');
  expect(sends).toBe(0);
  await page.getByLabel('Your message', { exact: true }).dispatchEvent('keydown', { key: 'Enter', code: 'Enter', isComposing: true });
  expect(sends).toBe(0);
  await page.getByLabel('Your message', { exact: true }).press('Enter');
  await expect(page.getByRole('button', { name: 'Stop response' })).toBeVisible();
  await expect(page.locator('.chat-message.assistant')).toContainText('A small beginning');
  completed = true;
  await expect(page.locator('.chat-message.assistant')).toContainText(reply, { timeout: 10000 });
  expect(sends).toBe(1);
  expect(await page.evaluate(() => 'modelExecuted' in window)).toBe(false);
  await page.reload();
  await expect(page.locator('.chat-message.assistant')).toContainText(reply);
  await page.getByLabel('Appearance').selectOption('dark');
  await page.screenshot({ path: 'evidence/inference/2026-09-13/chat-ui-fixture.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'evidence/inference/2026-09-13/chat-mobile-ui-fixture.png', fullPage: true });
});

test('private notes stay separate until explicitly used to steer', async ({ page }) => {
  await identity(page);
  let notes: { id: string; content: string; revision: number }[] = [];
  let sends = 0;
  const conversation = { id: 'steer-fixture', title: 'A long thought', revision: 2,
    messages: [{ id: 'u', role: 'user', content: 'Tell me a story', status: 'completed' }, { id: 'a', role: 'assistant', content: 'Once upon a time…', status: 'running' }],
    runs: [{ id: 'running-fixture', status: 'running', cancel_requested: false, reason: null, finish_reason: null, model_id: 'Local model' }],
    pending: [] as { id: string; content: string; state: string; reason: null }[] };
  await page.route('**/api/v1/chats', route => route.fulfill({ json: { items: [conversation] } }));
  await page.route('**/api/v1/chats/steer-fixture', route => route.fulfill({ json: conversation }));
  await page.route('**/api/v1/side-notes', async route => {
    if (route.request().method() === 'POST') {
      notes.push({ ...route.request().postDataJSON(), revision: 1 });
      await route.fulfill({ status: 201, json: notes.at(-1) });
    } else await route.fulfill({ json: { items: notes } });
  });
  await page.route('**/api/v1/side-notes/*/dismiss', async route => { notes = []; await route.fulfill({ json: { dismissed: true } }); });
  await page.route('**/api/v1/chats/steer-fixture/turns', async route => {
    sends++;
    const data = route.request().postDataJSON();
    expect(data.interrupt_run_id).toBe('running-fixture');
    expect(data.note_id).toBe(notes[0].id);
    expect(data.note_revision).toBe(1);
    conversation.runs[0].cancel_requested = true;
    conversation.pending = [{ id: data.request_id, content: data.content, state: 'queued', reason: null }];
    notes = [];
    await route.fulfill({ status: 202, json: { id: data.request_id, status: 'queued' } });
  });
  await page.route('**/api/v1/chats/steer-fixture/pending/*/cancel', async route => { conversation.pending = []; await route.fulfill({ json: { cancelled: true } }); });
  await page.goto('http://127.0.0.1:5174');
  await page.getByRole('button', { name: 'A long thought' }).click();
  await expect(page.getByRole('button', { name: 'Stop response' })).toBeVisible();
  await page.getByLabel('New side note').fill('Make it a space adventure');
  await page.getByLabel('New side note').press('Enter');
  await expect(page.locator('.side-note')).toContainText('Make it a space adventure');
  expect(sends).toBe(0);
  await expect(page.getByLabel('Conversation messages')).not.toContainText('space adventure');
  await page.getByRole('button', { name: 'Steer with this' }).click();
  await expect(page.locator('.queued-message')).toContainText('Make it a space adventure');
  await expect(page.locator('.side-note')).toHaveCount(0);
  expect(sends).toBe(1);
  await expect(page.getByRole('button', { name: 'Stop response' })).toBeDisabled();
  await page.getByLabel('New side note').fill('Another idea while waiting');
  await page.getByLabel('New side note').press('Enter');
  await expect(page.locator('.side-note')).toHaveCount(1);
  await page.getByRole('button', { name: 'Dismiss note:', exact: false }).click();
  await expect(page.locator('.side-note')).toHaveCount(0);
  await page.getByRole('button', { name: 'Return to composer' }).click();
  await expect(page.getByLabel('Your message', { exact: true })).toHaveValue('Make it a space adventure');
  expect(sends).toBe(1);
  await page.getByLabel('Appearance').selectOption('dark');
  await page.screenshot({ path: 'evidence/inference/2026-09-13/steering-ui-fixture.png', fullPage: true });
});

test('capability cards open matching provider configuration and verification', async ({ page }) => {
  await identity(page);
  const base = { description: 'A local capability.', icon: 'image', input_modalities: ['text'], output_modalities: ['image'], reason: 'Fixture readiness' };
  await page.route('**/api/v1/capabilities', route => route.fulfill({ json: { items: [
    { ...base, capability_id: 'chat.general', display_name: 'Conversation', state: 'ready' },
    { ...base, capability_id: 'image.generate', display_name: 'Image generation', state: 'offline' },
    { ...base, capability_id: 'geometry.generate', display_name: '3D generation', state: 'unassigned' },
  ] } }));
  const baseTarget = { revision: 1, state: 'ready', expired: false, features: [], reason: null, pool_name: 'Fixture GPU', resource_pool_id: 'pool', execution_state: 'idle', active_run_id: null, lease_until: null, verified_until: null };
  await page.route('**/api/v1/providers', route => route.fulfill({ json: { items: [
    { ...baseTarget, id: 'text', protocol: 'openai.chat.v1', name: 'Text provider', base_url: 'http://127.0.0.1:1234', model_id: 'fixture-chat' },
    { ...baseTarget, id: 'image', protocol: 'hearth.image.v1', name: 'Image provider', base_url: 'http://127.0.0.1:1235', model_id: 'fixture-image' },
  ] } }));
  let probes = 0;
  await page.route('**/api/v1/providers/image/probe', async route => { probes++; await route.fulfill({ json: { state: 'ready', reason: null } }); });
  await page.goto('/');
  await page.getByRole('button', { name: 'Capabilities', exact: true }).click();
  await page.locator('.capability-card').filter({ has: page.getByRole('heading', { name: 'Image generation', exact: true }) }).getByRole('button', { name: 'Verify provider' }).click();
  await expect(page).toHaveURL(/#providers\/image.generate$/);
  await expect(page.getByLabel('Provider type')).toHaveValue('hearth.image.v1');
  await expect(page.getByRole('heading', { name: 'Image provider', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Text provider', exact: true })).toHaveCount(0);
  expect(probes).toBe(0);
  await page.getByRole('button', { name: 'Verify images', exact: true }).click();
  expect(probes).toBe(1);
  await page.reload();
  await expect(page.getByLabel('Provider type')).toHaveValue('hearth.image.v1');
  await page.screenshot({ path: 'evidence/routing/2026-09-13/capability-provider-ui-fixture.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'evidence/routing/2026-09-13/capability-provider-mobile-ui-fixture.png', fullPage: true });
  await page.getByRole('button', { name: 'Capabilities', exact: true }).click();
  await page.locator('.capability-card').filter({ has: page.getByRole('heading', { name: '3D generation', exact: true }) }).getByRole('button', { name: 'Configure', exact: true }).click();
  await expect(page.getByText('Save an intended assignment above.', { exact: false })).toBeVisible();
  await expect(page.getByLabel('Provider type')).toBeVisible();
  await page.goBack();
  await expect(page.getByRole('heading', { name: 'Room for possibility.' })).toBeVisible();
  await page.locator('.capability-card').filter({ has: page.getByRole('heading', { name: 'Conversation', exact: true }) }).getByRole('button', { name: 'Configure provider' }).click();
  await expect(page.getByLabel('Provider type')).toHaveValue('openai.chat.v1');
  await expect(page.getByRole('heading', { name: 'Text provider', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Image provider', exact: true })).toHaveCount(0);
});

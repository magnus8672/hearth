// UI behavior fixtures. The opt-in Python case records real SDXL/BFF/DB dispatch.
import { test, expect, type Page } from '@playwright/test';
import { resolve } from 'node:path';

const request = { schema_version: 1, id: '00000000-0000-4000-8000-000000000007', model: 'stabilityai/stable-diffusion-xl-base-1.0', prompt: 'a little red fox asleep beside a glowing stone fireplace', negative_prompt: '', shape: 'square', steps: 20, seed: 451 };

async function setup(page: Page) {
  await page.route('**/api/v1/session', route => route.fulfill({ json: { id: 'image-chat-fixture', display_name: 'Local tester', roles: ['Owner'], permissions: ['conversation.own'], csrf_token: 'fixture-csrf', admin_origin: 'http://127.0.0.1:5173', user_origin: 'http://127.0.0.1:5174' } }));
  for (const endpoint of ['capabilities', 'side-notes']) await page.route(`**/api/v1/${endpoint}`, route => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/v1/conversation-images/*/image', route => route.fulfill({ path: resolve('evidence/images/2026-09-13/chat-routing/private-chat.png'), contentType: 'image/png' }));
  await page.goto('http://127.0.0.1:5174');
  await page.getByLabel('Appearance').selectOption('dark');
}

test('chat returns image progress and saved inline PNG, then restores it after reload', async ({ page }) => {
  let sent = false;
  let completed = false;
  let count = 0;
  const result = () => ({ id: 'fox-chat', title: 'A little fox', revision: sent ? 2 : 1,
    messages: sent ? [
      { id: 'human', role: 'user', content: 'Make an image of a little red fox asleep beside a glowing stone fireplace', status: 'completed' },
      { id: 'assistant', role: 'assistant', content: completed ? 'Generated image' : '', status: completed ? 'completed' : 'running', image: { schema_version: 1, request, progress: completed ? 20 : 7, status: completed ? 'completed' : 'running', reason: null, sha256: null } },
    ] : [], runs: sent ? [{ id: request.id, status: completed ? 'completed' : 'running', cancel_requested: false, reason: null, model_id: request.model, protocol: 'hearth.image.v1' }] : [], pending: [] });
  await page.route('**/api/v1/chats', route => route.fulfill({ status: route.request().method() === 'POST' ? 201 : 200, json: route.request().method() === 'POST' ? result() : { items: sent ? [{ id: 'fox-chat', title: 'A little fox', revision: 2 }] : [] } }));
  await page.route('**/api/v1/chats/fox-chat', route => route.fulfill({ json: result() }));
  await page.route('**/api/v1/chats/fox-chat/turns', async route => {
    count++;
    expect(route.request().headers()['x-hearth-csrf']).toBe('fixture-csrf');
    expect(route.request().postDataJSON().content).toContain('Make an image');
    sent = true;
    await route.fulfill({ status: 202, json: { id: request.id, status: 'running' } });
  });
  await setup(page);
  await page.getByLabel('Your message', { exact: true }).fill('Make an image of a little red fox asleep beside a glowing stone fireplace');
  await page.getByLabel('Your message', { exact: true }).press('Enter');
  await expect(page.getByRole('progressbar', { name: 'Image generation progress' })).toHaveAttribute('value', '7');
  await expect(page.getByRole('button', { name: 'Stop response' })).toBeVisible();
  await expect(page.getByText('Making an image. You can stop it or give a new direction below.')).toBeVisible();
  completed = true;
  const picture = page.getByRole('img', { name: request.prompt, exact: true });
  await expect(picture).toBeVisible();
  await expect(page.getByRole('link', { name: 'Save PNG', exact: true })).toBeVisible();
  await expect(page.getByRole('progressbar')).toHaveCount(0);
  await page.getByText('Image details', { exact: true }).click();
  await expect(page.getByText('Seed 451 · 20 detail passes', { exact: false })).toBeVisible();
  await page.getByText('Image details', { exact: true }).click();
  await page.screenshot({ path: 'evidence/images/2026-09-13/chat-routing/private-chat-ui-fixture.png', fullPage: true });
  await page.reload();
  await expect(picture).toBeVisible();
  expect(count).toBe(1);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await picture.scrollIntoViewIfNeeded();
  await page.screenshot({ path: 'evidence/images/2026-09-13/chat-routing/private-chat-mobile-ui-fixture.png', fullPage: true });
});

test('channel image appears inline and only the requesting member sees Stop', async ({ page }) => {
  let sent = false;
  let stopped = false;
  await page.route('**/api/v1/chats', route => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/v1/channels', route => route.fulfill({ json: { items: [{ id: 'image-room', name: 'Image workshop', joined: true }] } }));
  await page.route('**/api/v1/channels/image-room', route => route.fulfill({ json: { id: 'image-room', name: 'Image workshop', revision: 1, messages: [
    { id: 'earlier', role: 'assistant', display_name: 'hearth', content: 'Generated image', status: 'completed', can_stop: false, image: { schema_version: 1, request, status: 'completed', progress: 20, reason: null, sha256: null } },
    ...(sent ? [{ id: 'next', role: 'assistant', display_name: 'hearth', content: '', status: stopped ? 'cancelled' : 'running', request_id: request.id, can_stop: !stopped, image: { schema_version: 1, request, status: stopped ? 'cancelled' : 'running', progress: 3, reason: null, sha256: null } }] : []),
  ] } }));
  await page.route('**/api/v1/channels/image-room/messages', async route => { expect(route.request().postDataJSON().content).toBe('@hearth draw a fox'); sent = true; await route.fulfill({ status: 201, json: { saved: true } }); });
  await page.route('**/api/v1/channels/image-room/runs/*/stop', async route => { expect(route.request().headers()['x-hearth-csrf']).toBe('fixture-csrf'); stopped = true; await route.fulfill({ json: { stopping: true } }); });
  await setup(page);
  await page.getByRole('button', { name: 'Channels', exact: true }).click();
  await page.getByRole('button', { name: '# Image workshop Joined', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Save PNG' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Stop response' })).toHaveCount(0);
  await page.getByLabel('Channel message', { exact: true }).fill('@hearth draw a fox');
  await page.getByLabel('Channel message', { exact: true }).press('Enter');
  await expect(page.getByRole('progressbar')).toHaveAttribute('value', '3');
  await page.getByRole('button', { name: 'Stop response' }).click();
  await expect(page.getByText('Image stopped', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Stop response' })).toHaveCount(0);
  await page.getByRole('img', { name: request.prompt, exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: 'evidence/images/2026-09-13/chat-routing/channel-ui-fixture.png', fullPage: true });
});

test('local planning hands off to an image variation without showing model JSON', async ({ page }) => {
  let phase = 'idle';
  const sourceId = '00000000-0000-4000-8000-000000000006';
  const variant = { schema_version: 1, request: { ...request, prompt: 'A blue Jeep beside a pine forest at sunset' }, status: 'completed', progress: 20, reason: null, sha256: null, variation: true, source_image_id: sourceId, planning_model: 'openai/gpt-oss-20b' };
  const result = () => ({ id: 'plan-chat', title: 'A Jeep in the pines', revision: phase === 'idle' ? 2 : 3, pending: [],
    messages: [
      { id: 'earlier-image', role: 'assistant', content: 'Generated image', status: 'completed', image: { ...variant, request: { ...request, id: sourceId, prompt: 'A red Jeep beside a pine forest at sunset' }, variation: false } },
      ...(phase === 'idle' ? [] : [
        { id: 'new-request', role: 'user', content: 'Make it blue instead', status: 'completed' },
        { id: 'new-picture', role: 'assistant', content: phase === 'planning' ? 'Working out your image from the conversation…' : '', status: phase === 'completed' ? 'completed' : 'running', generation_phase: phase === 'planning' ? 'image_planning' : 'image_rendering', image: phase === 'planning' ? null : { ...variant, status: phase === 'completed' ? 'completed' : 'running', progress: phase === 'completed' ? 20 : 6 } },
      ]),
    ], runs: [{ id: phase === 'idle' ? sourceId : request.id, status: ['idle', 'completed'].includes(phase) ? 'completed' : 'running', cancel_requested: false, reason: null, model_id: phase === 'planning' ? 'openai/gpt-oss-20b' : request.model, protocol: phase === 'planning' ? 'openai.chat.v1' : 'hearth.image.v1' }],
  });
  await page.route('**/api/v1/chats', route => route.fulfill({ json: { items: [{ id: 'plan-chat', title: 'A Jeep in the pines', revision: 2 }] } }));
  await page.route('**/api/v1/chats/plan-chat', route => route.fulfill({ json: result() }));
  await page.route('**/api/v1/chats/plan-chat/turns', async route => { expect(route.request().postDataJSON().content).toBe('Make it blue instead'); phase = 'planning'; await route.fulfill({ status: 202, json: { id: request.id, status: 'running' } }); });
  await setup(page);
  await page.route('**/api/v1/conversation-images/*/image', route => route.fulfill({ path: resolve(`evidence/images/2026-09-13/contextual-planning/${route.request().url().includes(sourceId) ? 'red' : 'blue'}-jeep.png`), contentType: 'image/png' }));
  await page.getByRole('button', { name: 'A Jeep in the pines', exact: true }).click();
  await page.getByLabel('Your message', { exact: true }).fill('Make it blue instead');
  await page.getByLabel('Your message', { exact: true }).press('Enter');
  await expect(page.getByText('Planning your image locally. You can stop it or give a new direction below.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Stop response' })).toBeVisible();
  await expect(page.getByLabel('Conversation messages')).not.toContainText('"action"');
  phase = 'rendering';
  await expect(page.getByRole('progressbar')).toHaveAttribute('value', '6');
  phase = 'completed';
  await expect(page.getByText('Here’s a new variation.', { exact: true })).toBeVisible();
  await expect(page.getByText('New image from the earlier description', { exact: false })).toBeVisible();
  await page.locator('.conversation-image').last().getByText('Image details', { exact: true }).click();
  await expect(page.getByText('This is a new render, not an edit of the earlier pixels.', { exact: false })).toBeVisible();
  await page.screenshot({ path: 'evidence/images/2026-09-13/contextual-planning/variation-ui-fixture.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'evidence/images/2026-09-13/contextual-planning/variation-mobile-ui-fixture.png', fullPage: true });
});

for (const ending of ['completed', 'cancelled'] as const) {
  test(`chat image batch shows each result and ${ending} state after reload`, async ({ page }) => {
    let finished = false;
    const pictures = ['red', 'grey', 'black', 'army-green'].map((color, index) => ({ schema_version: 1, request: { ...request, id: `00000000-0000-4000-8000-00000000000${index + 1}`, prompt: `A ${color} Jeep Gladiator pickup`, seed: index + 10 }, status: 'queued', progress: 0, reason: null, sha256: null, planning_model: 'openai/gpt-oss-20b', batch_index: index + 1, batch_count: 4 }));
    const response = () => ({ id: 'batch-chat', title: 'Four Gladiators', revision: 2, pending: [], messages: [
      { id: 'human', role: 'user', content: 'make 4 different jeep gladiators in red grey black and army-green please', status: 'completed' },
      { id: 'assistant', role: 'assistant', content: '', status: finished ? ending : 'running', generation_phase: 'image_rendering', images: pictures.map((item, i) => ({ ...item, status: i === 0 ? 'completed' : finished ? ending : i === 1 ? 'running' : 'queued', progress: i === 0 || finished ? 20 : i === 1 ? 6 : 0 })) },
    ], runs: [{ id: pictures[0].request.id, status: finished ? ending : 'running', cancel_requested: false, reason: ending === 'cancelled' && finished ? 'The batch stopped. Completed images are saved.' : null, model_id: request.model, protocol: 'hearth.image.v1' }] });
    await page.route('**/api/v1/chats', route => route.fulfill({ json: { items: [{ id: 'batch-chat', title: 'Four Gladiators', revision: 2 }] } }));
    await page.route('**/api/v1/chats/batch-chat', route => route.fulfill({ json: response() }));
    await page.route('**/api/v1/chats/batch-chat/stop', async route => { finished = true; await route.fulfill({ json: { state: 'stopping' } }); });
    await setup(page);
    await page.route('**/api/v1/conversation-images/*/image', route => { const index = route.request().url().split('/').at(-2)!.slice(-1); return route.fulfill({ path: resolve(`evidence/images/2026-09-13/batches/gladiator-${index}.png`), contentType: 'image/png' }); });
    await page.getByRole('button', { name: 'Four Gladiators', exact: true }).click();
    await expect(page.getByText('1 of 4 images ready.', { exact: true })).toBeVisible();
    await expect(page.getByRole('progressbar')).toHaveCount(1);
    await expect(page.getByText('Waiting for the earlier images…', { exact: true })).toHaveCount(2);
    if (ending === 'cancelled') await page.getByRole('button', { name: 'Stop response', exact: true }).click();
    else finished = true;
    await expect(page.getByRole('button', { name: 'Stop response', exact: true })).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'Save PNG', exact: true })).toHaveCount(ending === 'completed' ? 4 : 1);
    await page.reload();
    await expect(page.getByRole('link', { name: 'Save PNG', exact: true })).toHaveCount(ending === 'completed' ? 4 : 1);
    if (ending === 'completed') {
      await page.screenshot({ path: 'evidence/images/2026-09-13/batches/chat-ui-fixture.png', fullPage: true });
      await page.setViewportSize({ width: 390, height: 844 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: 'evidence/images/2026-09-13/batches/chat-mobile-ui-fixture.png', fullPage: true });
    }
  });
}

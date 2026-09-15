import { test, expect, type Page } from '@playwright/test';
import { resolve } from 'node:path';

async function identity(page: Page) {
  await page.route('**/api/v1/session', route => route.fulfill({ json: { id: 'speech-fixture', display_name: 'Tester', roles: ['Owner'], permissions: ['farm.inspect', 'conversation.own', 'provider.configure'], csrf_token: 'fixture-csrf', admin_origin: 'http://127.0.0.1:5173', user_origin: 'http://127.0.0.1:5174' } }));
  for (const name of ['capabilities', 'side-notes', 'capability-routes']) await page.route(`**/api/v1/${name}`, route => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/v1/farm', route => route.fulfill({ json: { farm: { name: 'Fixture farm' }, members: [] } }));
}

for (const cancel of [false, true]) test(cancel ? 'stop generating speech and keep text available' : 'read aloud, play and stop a valid WAV, restore saved audio without another job', async ({ page }) => {
  await identity(page);
  let status = '', polls = 0, generations = 0;
  const speech = () => status ? { id: 'voice-job', status, model_id: 'kokoro-82m-v1.0-onnx', voice: 'af_heart', cancel_requested: false, reason: status === 'cancelled' ? 'Speech generation stopped.' : null, metadata: { frames: 137216, sample_rate: 24000 } } : null;
  const result = () => ({ id: 'chat', title: 'Welcome home', revision: 2, messages: [{ id: 'human', role: 'user', content: 'Hello', status: 'completed' }, { id: 'answer', role: 'assistant', content: 'Welcome home. Your hearth brings your models together.', status: 'completed', speech: speech() }], runs: [{ id: 'text-job', assistant_message_id: 'answer', model_id: 'openai/gpt-oss-20b', status: 'completed', finish_reason: 'stop' }] });
  await page.route('**/api/v1/chats', route => route.fulfill({ json: { items: [result()] } }));
  await page.route('**/api/v1/chats/chat', route => {
    if (status === 'running' && !cancel && ++polls >= 3) status = 'completed';
    return route.fulfill({ json: result() });
  });
  await page.route('**/api/v1/chats/chat/messages/answer/speech', async route => {
    expect(Object.keys(route.request().postDataJSON())).toEqual(['request_id']);
    expect(route.request().headers()['x-hearth-csrf']).toBe('fixture-csrf');
    generations++;
    status = 'running';
    await route.fulfill({ status: 202, json: { id: 'voice-job', status } });
  });
  await page.route('**/api/v1/chats/chat/speech/voice-job/cancel', async route => {
    expect(route.request().headers()['x-hearth-csrf']).toBe('fixture-csrf');
    status = 'cancelled';
    await route.fulfill({ json: { cancel_requested: true } });
  });
  await page.route('**/api/v1/chats/chat/speech/voice-job/audio', route => route.fulfill({ path: resolve('evidence/voice/2026-09-13/hearth-speech-sample.wav'), contentType: 'audio/wav' }));
  await page.goto('http://127.0.0.1:5174');
  await page.getByRole('button', { name: 'Welcome home', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Read aloud', exact: true })).toHaveCount(1);
  await page.getByRole('button', { name: 'Read aloud', exact: true }).click();
  if (cancel) {
    await page.getByRole('button', { name: 'Stop generating speech' }).click();
    await expect(page.getByText('Speech generation stopped.', { exact: true })).toBeVisible();
    await expect(page.locator('audio')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Read aloud', exact: true })).toBeEnabled();
  } else {
    const audio = page.getByLabel('Spoken reply', { exact: true });
    await expect(audio).toBeVisible();
    await audio.evaluate((element: HTMLAudioElement) => element.play());
    await expect.poll(() => audio.evaluate((element: HTMLAudioElement) => element.paused)).toBe(false);
    await expect.poll(() => audio.evaluate((element: HTMLAudioElement) => element.duration)).toBeGreaterThan(0);
    await page.getByRole('button', { name: 'Stop playback' }).click();
    expect(await audio.evaluate((element: HTMLAudioElement) => element.paused && element.currentTime === 0)).toBe(true);
    await page.reload();
    await expect(audio).toBeVisible();
    expect(await audio.evaluate((element: HTMLAudioElement) => element.paused)).toBe(true);
    expect(generations).toBe(1);
    await expect(page.getByRole('link', { name: 'Save WAV' })).toHaveAttribute('href', '/api/v1/chats/chat/speech/voice-job/audio');
    await expect(page.getByText('Voice · kokoro-82m-v1.0-onnx · af_heart')).toBeVisible();
    await page.getByLabel('Appearance').selectOption('dark');
    await page.screenshot({ path: 'evidence/speech/2026-09-13/read-aloud-desktop.png', fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: 'evidence/speech/2026-09-13/read-aloud-mobile.png', fullPage: true });
  }
});

test('register two independent speech servers with their own verification', async ({ page }) => {
  await identity(page);
  const items: Record<string, unknown>[] = [];
  await page.route('**/api/v1/providers', async route => {
    if (route.request().method() === 'POST') {
      const data = route.request().postDataJSON();
      expect(data.protocol).toBe('hearth.speech.v1');
      items.push({ ...data, id: `voice-${items.length}`, revision: 1, state: 'configured', features: [], pool_name: data.resource_pool, execution_state: 'idle' });
      await route.fulfill({ status: 201, json: items.at(-1) });
    } else await route.fulfill({ json: { items } });
  });
  await page.route('**/api/v1/providers/*/probe', async route => {
    expect(route.request().postDataJSON()).toEqual({ revision: 1 });
    const id = route.request().url().split('/').at(-2);
    Object.assign(items.find(item => item.id === id)!, { revision: 2, state: 'ready', features: ['audio.speak', 'audio.jobs'] });
    await route.fulfill({ json: { state: 'ready', reason: null } });
  });
  await page.goto('http://127.0.0.1:5173/#providers');
  for (let number = 1; number <= 2; number++) {
    await page.getByRole('button', { name: 'Add server', exact: true }).click();
    await page.getByLabel('Provider type').selectOption('hearth.speech.v1');
    await page.getByLabel('Connection name').fill(`Speech machine ${number}`);
    await page.getByLabel('Server address').fill(`https://192.168.1.${80+number}:1236`);
    await page.getByLabel('Model identifier').fill('kokoro-82m-v1.0-onnx');
    await page.getByLabel('Resource group', { exact: true }).fill(`Speech CPU ${number}`);
    await page.getByLabel('I trust this local server', { exact: false }).check();
    await page.getByRole('button', { name: 'Connect & verify speech' }).click();
    await expect(page.locator('.target-card')).toHaveCount(number);
    await expect(page.getByText('Speech verified.', { exact: false })).toBeVisible();
  }
  await expect(page.getByRole('button', { name: 'Verify speech', exact: true })).toHaveCount(2);
  await expect(page.getByRole('button', { name: 'Verify vision', exact: true })).toHaveCount(0);
});

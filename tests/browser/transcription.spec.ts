import { test, expect, type Page } from '@playwright/test';
import { resolve } from 'node:path';

test.use({ launchOptions: { args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream', `--use-file-for-fake-audio-capture=${resolve('evidence/voice/2026-09-13/hearth-speech-sample.wav')}`] } });

async function fixture(page: Page, complete = true) {
  let status = '', dismissed = false, uploads = 0, turns = 0;
  const jobs = () => status && !dismissed ? [{ id: 'draft', status, cancel_requested: false, reason: status === 'cancelled' ? 'Transcription stopped.' : null, transcript: status === 'completed' ? 'Turn left at the red gate.' : '', model_id: 'faster-whisper-small.en' }] : [];
  await page.route('**/api/v1/session', route => route.fulfill({ json: { id: 'transcription-fixture', display_name: 'Tester', roles: ['Owner'], permissions: ['farm.inspect', 'conversation.own', 'provider.configure'], csrf_token: 'fixture-csrf', admin_origin: 'http://127.0.0.1:5173', user_origin: 'http://127.0.0.1:5174' } }));
  for (const name of ['capabilities', 'side-notes', 'capability-routes']) await page.route(`**/api/v1/${name}`, route => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/v1/farm', route => route.fulfill({ json: { farm: { name: 'Fixture farm' }, members: [] } }));
  await page.route('**/api/v1/chats', route => route.fulfill({ json: { items: [{ id: 'chat', title: 'Voice test', revision: 1 }, { id: 'other', title: 'Another chat', revision: 1 }] } }));
  for (const id of ['chat', 'other']) await page.route(`**/api/v1/chats/${id}`, route => route.fulfill({ json: { id, title: 'Voice test', revision: 1, messages: [], runs: [] } }));
  await page.route('**/api/v1/chats/*/turns', route => { turns++; return route.fulfill({ status: 202, json: {} }); });
  await page.route('**/api/v1/chats/*/transcriptions?*', route => {
    const body = route.request().postDataBuffer()!;
    expect(body.subarray(0, 4).toString()).toBe('RIFF');
    expect(body.length).toBeGreaterThan(16044);
    expect(route.request().headers()['x-hearth-csrf']).toBe('fixture-csrf');
    uploads++; status = complete ? 'completed' : 'running'; dismissed = false;
    return route.fulfill({ status: 202, json: { id: 'draft', status } });
  });
  await page.route('**/api/v1/chats/*/transcriptions', route => route.fulfill({ json: { items: route.request().url().includes('/other/') ? [] : jobs() } }));
  await page.route('**/api/v1/chats/chat/transcriptions/draft/cancel', route => { status = 'cancelled'; return route.fulfill({ json: { cancel_requested: true } }); });
  await page.route('**/api/v1/chats/chat/transcriptions/draft', route => { expect(route.request().method()).toBe('DELETE'); dismissed = true; return route.fulfill({ json: { dismissed: true } }); });
  await page.addInitScript(() => {
    const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    (window as any).recordedTracks = [];
    navigator.mediaDevices.getUserMedia = async constraints => { const stream = await original(constraints); (window as any).recordedTracks.push(...stream.getTracks()); return stream; };
  });
  await page.goto('http://127.0.0.1:5174');
  await page.getByRole('button', { name: 'Voice test', exact: true }).click();
  return { uploads: () => uploads, turns: () => turns };
}

test('WAV upload review restores, remains editable and never sends automatically', async ({ page }) => {
  const count = await fixture(page);
  await page.getByLabel('Upload WAV recording').setInputFiles(resolve('evidence/voice/2026-09-13/hearth-speech-sample.wav'));
  await expect(page.getByLabel('Recording preview')).toBeVisible();
  expect(count.uploads()).toBe(0);
  await page.getByRole('button', { name: 'Transcribe recording', exact: true }).click();
  await expect(page.getByLabel('Review transcript')).toHaveValue('Turn left at the red gate.');
  await page.reload();
  await expect(page.getByLabel('Review transcript')).toHaveValue('Turn left at the red gate.');
  expect(count.uploads()).toBe(1); expect(count.turns()).toBe(0);
  await page.getByLabel('Review transcript').fill('Turn right at the green gate.');
  await page.getByLabel('Appearance').selectOption('dark');
  await page.screenshot({ path: 'evidence/transcription/2026-09-13/transcript-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'evidence/transcription/2026-09-13/transcript-mobile.png', fullPage: true });
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.getByLabel('Your message', { exact: true }).fill('Directions:');
  await page.getByRole('button', { name: 'Use in message', exact: true }).click();
  await expect(page.getByLabel('Your message', { exact: true })).toHaveValue('Directions:\n\nTurn right at the green gate.');
  expect(count.turns()).toBe(0);
  await expect(page.getByLabel('Review transcript')).toHaveCount(0);
  await page.getByLabel('Appearance').selectOption('dark');
  await page.screenshot({ path: 'evidence/transcription/2026-09-13/review-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'evidence/transcription/2026-09-13/review-mobile.png', fullPage: true });
});

test('real browser audio capture produces WAV, stops tracks and cancels transcription', async ({ page }) => {
  const count = await fixture(page, false);
  await page.getByRole('button', { name: 'Record voice', exact: true }).click();
  await expect(page.getByText(/Recording · [1-9]\d*s/)).toBeVisible();
  await page.getByRole('button', { name: 'Stop recording', exact: true }).click();
  expect(await page.evaluate(() => (window as any).recordedTracks.every((track: MediaStreamTrack) => track.readyState === 'ended'))).toBe(true);
  await expect(page.getByLabel('Recording preview')).toBeVisible();
  expect(count.uploads()).toBe(0);
  await page.getByRole('button', { name: 'Transcribe recording', exact: true }).click();
  await page.getByRole('button', { name: 'Stop transcription', exact: true }).click();
  await expect(page.getByText('Transcription stopped.', { exact: true })).toBeVisible();
  expect(count.turns()).toBe(0);
  await page.getByRole('button', { name: 'Dismiss transcript', exact: true }).click();
  await page.getByRole('button', { name: 'Record voice', exact: true }).click();
  await expect(page.getByText(/Recording ·/)).toBeVisible();
  page.on('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: 'Another chat', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Stop recording', exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => (window as any).recordedTracks.every((track: MediaStreamTrack) => track.readyState === 'ended'))).toBe(true);
});

test('microphone denial leaves WAV upload available', async ({ page }) => {
  await fixture(page);
  await page.evaluate(() => { navigator.mediaDevices.getUserMedia = async () => { throw new DOMException('Denied', 'NotAllowedError'); }; });
  await page.getByRole('button', { name: 'Record voice', exact: true }).click();
  await expect(page.getByText('Microphone permission was denied. Allow access in your browser or upload a WAV file.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Upload WAV', exact: true })).toBeEnabled();
});

test('discarding a pending permission request stops a stream that arrives later', async ({ page }) => {
  await fixture(page);
  await page.evaluate(() => {
    const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia = () => new Promise(resolve => { (window as any).grantLate = async () => resolve(await original({ audio: true })); });
  });
  await page.getByRole('button', { name: 'Record voice', exact: true }).click();
  await expect(page.getByText('Waiting for microphone permission…', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Discard recording', exact: true }).click();
  await page.evaluate(() => (window as any).grantLate());
  await expect.poll(() => page.evaluate(() => (window as any).recordedTracks.length > 0 && (window as any).recordedTracks.every((track: MediaStreamTrack) => track.readyState === 'ended'))).toBe(true);
  await expect(page.getByRole('button', { name: 'Stop recording', exact: true })).toHaveCount(0);
});

test('multiple transcription servers keep independent configuration and verification', async ({ page }) => {
  await fixture(page);
  const items: any[] = [];
  await page.route('**/api/v1/providers', route => {
    if (route.request().method() === 'POST') {
      const value = route.request().postDataJSON(); expect(value.protocol).toBe('hearth.transcription.v1');
      items.push({ ...value, id: 'server-'+items.length, revision: 1, state: 'configured', features: [], pool_name: value.resource_pool, execution_state: 'idle' });
      return route.fulfill({ status: 201, json: items.at(-1) });
    }
    return route.fulfill({ json: { items } });
  });
  await page.route('**/api/v1/providers/*/probe', route => {
    const item = items.find(item => route.request().url().includes(item.id));
    Object.assign(item, { state: 'ready', features: ['audio.transcribe', 'audio.jobs'], revision: 2 });
    return route.fulfill({ json: item });
  });
  await page.goto('http://127.0.0.1:5173');
  await page.getByRole('button', { name: 'Providers', exact: true }).click();
  for (let i = 1; i <= 2; i++) {
    await page.getByRole('button', { name: 'Add server', exact: true }).click();
    await page.getByLabel('Provider type').selectOption('hearth.transcription.v1');
    await page.getByLabel('Connection name').fill('Speech input '+i);
    await page.getByLabel('Server address').fill('https://recognizer'+i+'.test:1237');
    await page.getByLabel('Model identifier').fill('faster-whisper-small.en');
    await page.getByLabel('Resource group', { exact: true }).fill('Independent CPU '+i);
    await page.getByLabel('I trust this local server', { exact: false }).check();
    await page.getByRole('button', { name: 'Connect & verify transcription', exact: true }).click();
    await expect(page.getByText('Transcription verified against a known recording. Saved speech input assignments can use this model.')).toBeVisible();
  }
  expect(items).toHaveLength(2); expect(items[0].resource_pool).not.toBe(items[1].resource_pool);
});

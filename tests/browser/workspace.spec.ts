import { browserOrigins } from './origins';
import { test, expect, type Page } from '@playwright/test';
import path from 'node:path';

const origin = browserOrigins.workspace;
const messages = () => Array.from({ length: 45 }, (_, i) => ({ id: `m${i}`, role: i % 2 ? 'assistant' : 'user', display_name: 'Member', content: `Message ${i}: ` + 'A saved conversation with enough history to scroll. '.repeat(8), status: 'completed', reason: null }));
async function fixture(page: Page) {
  const state = { messages: messages(), runs: [] as Record<string, unknown>[] };
  // Optional predeployment check of compiled assets in the browser, on the VM origin.
  if (process.env.HEARTH_BROWSER_LOCAL_BUILD === '1') await page.route(origin + '/**', async route => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname !== '/' && !pathname.startsWith('/assets/')) return route.fallback();
    const file = path.resolve('apps/user-web/dist', '.' + (pathname === '/' ? '/index.html' : pathname));
    if (!file.startsWith(path.resolve('apps/user-web/dist') + path.sep)) return route.abort();
    await route.fulfill({ path: file });
  });
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url()).pathname;
    if (url === '/api/v1/session') return route.fulfill({ json: { id: 'layout-fixture', display_name: 'Layout reviewer', roles: ['Member'], permissions: ['conversation.own', 'channel.use', 'capability.image.generate', 'capability.geometry.generate'], csrf_token: 'fixture', user_origin: origin, admin_origin: origin + ':8443' } });
    if (url === '/api/v1/chats') return route.fulfill({ json: { items: [{ id: 'first', title: 'Long conversation', revision: 1 }, { id: 'second', title: 'Other conversation', revision: 1 }] } });
    if (/\/chats\/(first|second)$/.test(url)) return route.fulfill({ json: { id: url.split('/').at(-1), title: 'Long conversation', revision: 1, messages: state.messages, runs: state.runs } });
    if (url.endsWith('/channels')) return route.fulfill({ json: { items: [{ id: 'room', name: 'Workshop', joined: true }] } });
    if (url.endsWith('/channels/room')) return route.fulfill({ json: { id: 'room', name: 'Workshop', revision: 1, messages: state.messages } });
    if (/\/geometry\/\d+\/model$/.test(url)) {
      const json = Buffer.from(JSON.stringify({ asset: { version: '2.0' }, scene: 0, scenes: [{ nodes: [] }] }).padEnd(100, ' '));
      const glb = Buffer.alloc(20 + json.length); glb.write('glTF'); glb.writeUInt32LE(2, 4); glb.writeUInt32LE(glb.length, 8); glb.writeUInt32LE(json.length, 12); glb.writeUInt32LE(0x4e4f534a, 16); json.copy(glb, 20);
      return route.fulfill({ contentType: 'model/gltf-binary', body: glb });
    }
    if (url.endsWith('/geometry')) return route.fulfill({ json: { items: Array.from({ length: 6 }, (_, i) => ({ id: String(i), name: `Model ${i}`, has_thumbnail: false, status: 'completed', request: { model: 'trellis2/q8', resolution: 512, seed: i }, metadata: { triangles: 1000, textures: 2, bytes: 1024 } })) } });
    return route.fulfill({ json: { items: [] } });
  });
  return state;
}
async function bottom(page: Page, expected = true) {
  await expect.poll(() => page.locator('.chat-transcript').evaluate(element => element.scrollHeight - element.scrollTop - element.clientHeight < 5)).toBe(expected);
}

for (const scope of ['chat', 'channels']) test(`${scope}: queued GPU work and failures are visible and stoppable`, async ({ page }) => {
  const state = await fixture(page);
  const picture = { request: { id: 'queued-image', model: 'fooocus/fixture', prompt: 'A fox', shape: 'square', steps: 20, seed: 1 }, status: 'queued', progress: 0, reason: 'The GPU queue is paused. Your request is saved.' };
  const message = { ...state.messages[1], id: 'queued-reply', role: 'assistant', content: '', status: 'running', images: [picture], image: picture, can_stop: true, request_id: 'queued-image' };
  state.messages = [message];
  state.runs = [{ id: 'queued-image', assistant_message_id: message.id, status: 'running', protocol: 'hearth.image.v1', capability_id: 'image.generate', cancel_requested: false }];
  await page.goto(origin + '/#' + scope);
  await page.getByRole('button', { name: scope === 'chat' ? 'Long conversation' : '# Workshop' }).click();
  await expect(page.getByText('Waiting in the GPU queue…', { exact: true })).toBeVisible();
  await expect(page.getByText(picture.reason, { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Stop response', exact: true })).toBeVisible();
  picture.reason = 'Preparing the selected GPU service…';
  await expect(page.getByText(picture.reason, { exact: true })).toBeVisible();
  picture.status = 'running'; picture.reason = ''; picture.progress = 5;
  await expect(page.getByRole('progressbar', { name: 'Image generation progress' })).toHaveAttribute('value', '5');
  picture.status = 'failed'; picture.reason = 'The GPU worker needs attention. Check Workers in Administration before retrying.';
  message.status = 'failed'; state.runs[0].status = 'failed';
  await expect(page.getByText('Image needs attention', { exact: true })).toBeVisible();
  await expect(page.getByText(picture.reason, { exact: true })).toBeVisible();
});

for (const route of ['chat', 'channels']) test(`${route}: open at bottom, follow large replies, preserve scrollback and switch`, async ({ page }) => {
  const state = await fixture(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(origin + '/#' + route);
  await page.getByRole('button', { name: route === 'chat' ? 'Long conversation' : '# Workshop' }).click();
  await bottom(page);
  state.messages.push({ ...state.messages[1], id: 'large', content: 'Large incoming reply. '.repeat(1200) });
  await expect(page.locator('.chat-message').last()).toContainText('Large incoming reply');
  await bottom(page);
  await page.locator('.chat-transcript').evaluate(element => { element.scrollTop = 100; });
  await expect(page.getByRole('button', { name: 'Jump to latest' })).toBeVisible();
  state.messages.push({ ...state.messages[0], id: 'new', content: 'Newest arrival' });
  await expect(page.locator('.chat-message').last()).toContainText('Newest arrival');
  await bottom(page, false);
  await page.getByRole('button', { name: 'Jump to latest' }).click();
  await bottom(page);
  if (route === 'chat') {
    await page.locator('.chat-transcript').evaluate(element => { element.scrollTop = 100; });
    await page.getByRole('button', { name: 'Other conversation' }).click();
    await bottom(page);
  }
  const composer = await page.locator('.chat-composer').boundingBox();
  expect(composer!.y + composer!.height).toBeLessThan(1080);
});

test('wide panes resize, collapse, dock and persist without losing notes', async ({ page }) => {
  await fixture(page); await page.setViewportSize({ width: 3840, height: 2050 });
  await page.goto(origin + '/#chat');
  await page.getByRole('button', { name: 'Long conversation' }).click();
  const panes = page.locator('.workspace-panes');
  const bounds = (await panes.boundingBox())!;
  expect(bounds.x + bounds.width).toBeGreaterThan(3700);
  const handle = page.getByRole('separator', { name: 'Resize conversations' });
  await handle.focus(); await page.keyboard.press('ArrowRight');
  await expect(handle).toHaveAttribute('aria-valuenow', '300');
  const position = (await handle.boundingBox())!;
  await page.mouse.move(position.x + 8, position.y + 50); await page.mouse.down();
  await page.mouse.move(bounds.x + 380, position.y + 50); await page.mouse.up();
  await expect(handle).toHaveAttribute('aria-valuenow', '380');
  await page.locator('.side-notes textarea').fill('Keep my unsaved note');
  await page.getByRole('button', { name: 'Hide notes' }).click();
  await page.getByRole('button', { name: 'Show notes' }).click();
  await expect(page.locator('.side-notes textarea')).toHaveValue('Keep my unsaved note');
  await page.getByLabel('Dock notes').selectOption('bottom');
  const note = (await page.locator('.workspace-right').boundingBox())!;
  const chat = (await page.locator('.workspace-center').boundingBox())!;
  expect(note.y).toBeGreaterThanOrEqual(chat.y + chat.height);
  await page.locator('.side-notes textarea').fill('');
  await page.reload();
  await expect(handle).toHaveAttribute('aria-valuenow', '380');
  await expect(page.getByLabel('Dock notes')).toHaveValue('bottom');
  await page.getByRole('button', { name: 'Reset layout' }).click();
  await expect(handle).toHaveAttribute('aria-valuenow', '280');
  await page.screenshot({ path: '.hearth/workspace-wide.png', fullPage: true });
});

for (const width of [390, 768, 1366, 1920, 3840]) test(`layouts at ${width}px have no horizontal overflow`, async ({ page }) => {
  await fixture(page); await page.setViewportSize({ width, height: width > 1920 ? 2050 : 900 });
  for (const route of ['chat', 'channels', 'images', 'geometry']) {
    await page.goto(origin + '/#' + route);
    await expect(page.locator('.workspace-panes')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    if (route === 'geometry' && width === 3840) {
      const cards = page.locator('.geometry-card');
      await expect(cards).toHaveCount(6);
      const first = (await cards.nth(0).boundingBox())!;
      const second = (await cards.nth(1).boundingBox())!;
      expect(second.x).toBeGreaterThan(first.x);
      await page.getByRole('button', { name: 'Preview 3D', exact: true }).first().click();
      const preview = page.locator('.geometry-preview');
      await expect(preview.locator('canvas')).toBeVisible();
      const box = (await preview.boundingBox())!;
      expect(box.width).toBeGreaterThan(2500);
      await page.mouse.move(box.x + box.width - 3, box.y + box.height - 3);
      await page.mouse.down(); await page.mouse.move(box.x + box.width - 3, box.y + box.height - 123); await page.mouse.up();
      await expect.poll(async () => (await preview.boundingBox())!.height).toBeLessThan(box.height - 80);
      await expect.poll(() => preview.locator('canvas').evaluate(canvas => Math.abs((canvas as HTMLCanvasElement).height - canvas.clientHeight) < 3)).toBe(true);
      await page.screenshot({ path: '.hearth/geometry-wide.png', fullPage: true });
    }
  }
});

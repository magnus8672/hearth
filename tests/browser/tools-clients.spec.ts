import { test, expect, type Page } from '@playwright/test';

const caps = ['chat.general', 'code.implement'];
async function base(page: Page, admin = false) {
  await page.route('**/api/v1/session', route => route.fulfill({ json: { id: 'fixture', display_name: 'Tester', roles: [admin ? 'Owner' : 'Member'], permissions: admin ? ['farm.inspect', 'tool.approve', 'provider.configure'] : ['conversation.own', 'api_key.own'], csrf_token: 'fixture', admin_origin: 'http://127.0.0.1:5173', user_origin: 'http://127.0.0.1:5174' } }));
  await page.route('**/api/v1/capabilities', route => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/v1/farm', route => route.fulfill({ json: { farm: { name: 'Test hearth' }, members: [] } }));
}

test('client keys expose capability selection and show the secret once with revocation', async ({ page }) => {
  await base(page);
  const items: { id: string; name: string; capabilities: string[]; allow_tools: boolean; expires_at: string; revoked_at: string | null; last_used_at: null }[] = [];
  await page.route('**/api/v1/client-keys', async route => {
    if (route.request().method() === 'POST') {
      const data = route.request().postDataJSON();
      expect(data.capabilities).toEqual(caps);
      expect(data.allow_tools).toBe(true);
      items.push({ ...data, id: 'test-key', expires_at: '2027-01-01', revoked_at: null, last_used_at: null });
      await route.fulfill({ status: 201, json: { id: 'test-key', key: 'synthetic-test-key-not-a-real-credential' } });
    } else await route.fulfill({ json: { items, capabilities: caps, base_url: 'https://localhost:8444/v1', mcp_url: 'https://localhost:8444/mcp' } });
  });
  await page.route('**/api/v1/client-keys/test-key', async route => { items[0].revoked_at = new Date().toISOString(); await route.fulfill({ json: { revoked: true } }); });
  await page.goto('http://127.0.0.1:5174/#clients');
  await expect(page.getByRole('heading', { name: 'Bring your own agent.' })).toBeVisible();
  await page.getByLabel('Name', { exact: true }).fill('Continue desktop');
  await page.getByRole('button', { name: 'Create API key' }).click();
  await expect(page.getByLabel('New API key')).toHaveValue('synthetic-test-key-not-a-real-credential');
  await page.getByRole('button', { name: 'I saved it' }).click();
  await expect(page.getByLabel('New API key')).toHaveCount(0);
  await page.reload();
  await expect(page.getByLabel('New API key')).toHaveCount(0);
  await page.getByRole('button', { name: 'Revoke Continue desktop' }).click();
  await expect(page.getByText('Revoked', { exact: false }).last()).toBeVisible();
});

test('admin discovers tools, reviews schema, scopes approval and can edit connections', async ({ page }) => {
  await base(page, true);
  const server = { id: 'server', name: 'Workshop', base_url: 'http://192.168.1.20:8096/mcp', revision: 1, enabled: true, reason: null, tls_ca_pem: '', allow_insecure_http: true, requires_credential: false, tools: [{ id: 'add', name: 'add', definition: { description: 'Add two integers.', inputSchema: { type: 'object', properties: { a: { type: 'integer' }, b: { type: 'integer' } } } }, enabled: false, revision: 1, access: 'owner', effect: 'write', capabilities: [] as string[] }] };
  await page.route('**/api/v1/tool-servers', route => route.fulfill({ json: { items: [server], capabilities: caps } }));
  await page.route('**/api/v1/tool-catalog/add', async route => { const data = route.request().postDataJSON(); expect(data.effect).toBe('read'); expect(data.access).toBe('members'); expect(data.capabilities).toEqual(caps); Object.assign(server.tools[0], data, { revision: 2 }); await route.fulfill({ json: { saved: true } }); });
  await page.goto('http://127.0.0.1:5173/#tools');
  await page.getByText('add · Needs review', { exact: false }).click();
  await page.getByText('Full tool schema', { exact: true }).click();
  await expect(page.locator('pre')).toContainText('integer');
  await page.getByLabel('Available to').selectOption('members');
  await page.getByLabel('Action type').selectOption('read');
  await page.getByRole('button', { name: 'Approve this schema' }).click();
  await expect(page.getByText('add · Approved', { exact: false })).toBeVisible();
  await page.getByLabel('Appearance').selectOption('dark');
  await page.screenshot({ path: 'evidence/tools/2026-09-14/tools-admin-dark.png', fullPage: true });
  await page.getByRole('button', { name: 'Edit connection', exact: true }).click();
  await expect(page.getByLabel('MCP endpoint')).toHaveValue(server.base_url);
  await expect(page.getByRole('button', { name: 'Save and rediscover' })).toBeVisible();
});

test('tool approval renders exact arguments as text and never lets API content inject HTML', async ({ page }) => {
  await base(page);
  const invocation = { id: 'invocation', name: 'change_note', server_name: 'Workshop', state: 'awaiting_approval', arguments: { text: '<img src=x onerror="window.injected=true">' } };
  await page.route('**/api/v1/my-tools', route => route.fulfill({ json: { tools: [{ name: 'change_note', server: 'Workshop', effect: 'write' }], servers: [], invocations: [invocation] } }));
  await page.route('**/api/v1/tool-invocations/invocation/decision', async route => { expect(route.request().postDataJSON()).toEqual({ approve: true }); expect(route.request().headers()['x-hearth-csrf']).toBe('fixture'); invocation.state = 'approved'; await route.fulfill({ json: { state: 'approved' } }); });
  await page.goto('http://127.0.0.1:5174/#tools');
  await page.locator('.tool-activity summary').click();
  await expect(page.locator('.tool-activity pre')).toContainText('<img');
  await expect(page.locator('.tool-activity img')).toHaveCount(0);
  await page.getByRole('button', { name: 'Approve once' }).click();
  await expect(page.getByRole('button', { name: 'Approve once' })).toHaveCount(0);
  await expect(page.getByText('Approved for this invocation only.', { exact: false })).toBeVisible();
});

test('connections and shared tools fit mobile and desktop screens', async ({ page }) => {
  await base(page);
  await page.route('**/api/v1/client-keys', route => route.fulfill({ json: { items: [], capabilities: caps, base_url: 'https://localhost:8444/v1', mcp_url: 'https://localhost:8444/mcp' } }));
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto('http://127.0.0.1:5174/#clients');
  await expect(page.getByRole('heading', { name: 'Add a client' })).toBeVisible();
  await page.screenshot({ path: 'evidence/tools/2026-09-14/clients-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: 'evidence/tools/2026-09-14/clients-mobile.png', fullPage: true });
});

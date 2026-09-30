import { browserOrigins } from './origins';
import { test, expect, type Page } from '@playwright/test';

const origin = browserOrigins.workspace;
const adminOrigin = browserOrigins.admin;
async function session(page: Page, permissions: string[], state = 'active', admin = false) {
  await page.route('**/api/v1/session', route => route.fulfill({ json: { id: 'owner', display_name: 'Test person', state, roles: admin ? ['Owner'] : state === 'pending' ? [] : ['Member'], permissions, csrf_token: 'access-fixture', user_origin: origin, admin_origin: adminOrigin } }));
  await page.route('**/api/v1/capabilities', route => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/v1/farm', route => route.fulfill({ json: { farm: { name: 'Test hearth' }, members: [] } }));
}

test('pending workspace makes no capability calls, including a forced deep link', async ({ page }) => {
  await session(page, [], 'pending');
  const requests: string[] = [];
  page.on('request', request => { if (request.url().includes('/api/v1/')) requests.push(new URL(request.url()).pathname); });
  await page.goto(origin+'/#geometry');
  await expect(page.getByRole('heading', { name: 'Waiting for access' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Check access' })).toHaveAttribute('href', '/auth/login');
  await expect(page.getByRole('button', { name: '3D models', exact: true })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Administration' })).toHaveCount(0);
  expect(requests).toEqual(['/api/v1/session']);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('chat-only grants hide image, model, tools, speech and vision controls', async ({ page }) => {
  await session(page, ['conversation.own', 'capability.chat.general']);
  for (const path of ['chats','side-notes']) await page.route(`**/api/v1/${path}`, route => route.fulfill({ json: { items: [] } }));
  await page.goto(origin+'/#images');
  await expect(page.getByRole('heading', { name: 'Let’s think together.' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Images', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Attach image', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Record voice', exact: true })).toHaveCount(0);
  await expect(page.locator('.specialist-choice option')).toHaveCount(2);
});

test('People approves selected capabilities and handles concurrent edits', async ({ page }) => {
  await session(page, ['farm.inspect', 'role.grant'], 'active', true);
  const pending = { id: 'pending', display_name: 'New neighbour', state: 'pending', roles: [], permissions: [], revision: 1 };
  let items = [pending]; let conflict = false;
  await page.route('**/api/v1/accounts', route => route.fulfill({ json: { items, capabilities: [{ permission: 'capability.chat.general', name: 'Conversation' }, { permission: 'capability.geometry.generate', name: '3D generation' }] } }));
  await page.route('**/api/v1/accounts/pending/access', async route => {
    expect(route.request().headers()['x-hearth-csrf']).toBe('access-fixture');
    const data = route.request().postDataJSON();
    if (conflict) return route.fulfill({ status: 409, json: { error: { message: 'This account changed in another tab. Reload before saving.' } } });
    expect(data).toEqual({ state: 'active', role: 'Member', revision: 1, permissions: ['conversation.own', 'capability.chat.general'] });
    items = [{ ...pending, ...data, revision: 2, roles: ['Member'] }];
    return route.fulfill({ json: { revision: 2, state: 'active' } });
  });
  await page.goto(adminOrigin+'/#people');
  await page.getByRole('button', { name: 'Review access' }).click();
  await expect(page.getByRole('checkbox', { name: '3D generation' })).not.toBeChecked();
  await page.screenshot({ path: '.hearth/test-results/accounts/people.png', fullPage: true });
  await page.getByRole('button', { name: 'Chat only', exact: true }).click();
  await page.getByRole('button', { name: 'Enable account' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Access saved' })).toBeVisible();
  conflict = true;
  await page.getByRole('button', { name: 'Edit access' }).click();
  await page.getByRole('checkbox', { name: '3D generation' }).check();
  await page.getByRole('button', { name: 'Save access' }).click();
  await expect(page.getByRole('alert')).toContainText('changed in another tab');
  await expect(page.getByRole('checkbox', { name: '3D generation' })).toBeChecked();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: '.hearth/test-results/accounts/people-mobile.png', fullPage: true });
});

test('HTTP welcome offers current public installer and confirmation before HTTPS signup', async ({ page }) => {
  await page.goto(browserOrigins.welcome);
  await expect(page.getByRole('link', { name: 'Install certificate on Windows' })).toHaveAttribute('href', '/install-hearth-certificate.cmd');
  const register = page.getByRole('button', { name: 'Continue to secure registration' });
  await expect(register).toBeDisabled();
  await page.getByRole('checkbox').check();
  await expect(register).toBeEnabled();
  await register.click();
  await expect(page.getByRole('textbox', { name: 'Username', exact: true })).toBeVisible();
  expect(new URL(page.url()).origin).toBe(browserOrigins.identity);
  await expect(page.locator('input[name="password"]')).toBeVisible();
  await page.screenshot({ path: '.hearth/test-results/accounts/registration.png', fullPage: true });
});

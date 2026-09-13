// Native setup UI fixtures. Real TLS is exercised separately inside the appliance.
import { test, expect, type Page } from '@playwright/test';
import { readFile } from 'node:fs/promises';

async function setupPage(page: Page, options: { trusted?: boolean; owner?: boolean; blocked?: boolean; firstFailure?: boolean } = {}) {
  let trustCalls = 0;
  let adminAttempts = 0;
  await page.route('http://127.0.0.1:5173/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api') {
      const body = route.request().postDataJSON();
      if (body.action === 'trust') trustCalls++;
      await route.fulfill({ json: { trusted: options.trusted !== false || trustCalls > 0, owner_created: options.owner !== false, fingerprint: 'FIXTURE PUBLIC CERTIFICATE FINGERPRINT' } });
      return;
    }
    const file = path === '/' ? 'setup.html' : path.slice(1);
    const types: Record<string, string> = { 'setup.html': 'text/html', 'setup.js': 'text/javascript', 'setup.css': 'text/css', 'hearth-lockup-light.svg': 'image/svg+xml' };
    if (!types[file]) return route.abort();
    await route.fulfill({ body: await readFile('worker/cmd/hearth-setup/' + file), contentType: types[file] });
  });
  await page.route('https://localhost:*/health/browser', async route => {
    const port = new URL(route.request().url()).port;
    if (port === '8443') adminAttempts++;
    if ((port === '8445' && options.blocked) || (port === '8443' && options.firstFailure && adminAttempts === 1)) return route.abort('failed');
    await route.fulfill({ headers: { 'Access-Control-Allow-Origin': '*' }, json: { service: { '8443': 'hearth-admin', '8444': 'hearth-user', '8445': 'hearth-identity' }[port], status: 'ok' } });
  });
  await page.goto('/#explicit-ui-fixture-proof');
  return () => adminAttempts;
}

test('installed Windows certificate does not expose app links while browser identity connection fails', async ({ page }) => {
  await setupPage(page, { blocked: true });
  await expect(page.getByText('Sign-in · Connection not verified')).toBeVisible();
  await expect(page.locator('#complete')).toBeHidden();
  await expect(page.locator('#owner-form')).toBeHidden();
  await expect(page.locator('#browser-help')).toHaveAttribute('open', '');
  await expect(page.getByRole('button', { name: 'Check browser connections' })).toBeEnabled();
});

test('a first failed browser connection is retried before the links become available', async ({ page }) => {
  const attempts = await setupPage(page, { firstFailure: true });
  await expect(page.getByRole('link', { name: 'Open Administration' })).toBeVisible();
  expect(attempts()).toBe(2);
  await expect(page).toHaveURL('http://127.0.0.1:5173/');
  await expect(page.locator('#owner-form')).toBeHidden();
});

test('new Owner form requires explicit Windows trust and successful browser probes', async ({ page }) => {
  await setupPage(page, { trusted: false, owner: false });
  await expect(page.getByText('This browser can securely reach every Hearth address.')).toBeVisible();
  await expect(page.locator('#owner-form')).toBeHidden();
  await page.getByRole('button', { name: 'Trust this Hearth certificate' }).click();
  await expect(page.getByLabel('Hearth name')).toBeVisible();
  await expect(page.locator('#complete')).toBeHidden();
});

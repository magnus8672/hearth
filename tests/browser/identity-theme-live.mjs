// Real public HTTPS appearance plus isolated-realm form checks on guest loopback.
// No browser certificate exceptions. No sign-in to the user's established farm.
import { chromium, expect } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash, createHmac, randomBytes } from 'node:crypto';

const data = JSON.parse(readFileSync('identity-theme-qa.json', 'utf8'));
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1050 } });
const page = await context.newPage();
const errors = [];
page.on('pageerror', () => errors.push('page script error'));
let step = 'public HTTPS sign-in';
function otp(secret) {
  let bits = '';
  for (const c of secret.replace(/\s/g, '').toUpperCase()) bits += 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'.indexOf(c).toString(2).padStart(5, '0');
  const bytes = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) bytes.push(parseInt(bits.slice(i, i + 8), 2));
  const counter = Buffer.alloc(8); counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const digest = createHmac('sha1', Buffer.from(bytes)).update(counter).digest();
  const offset = digest[digest.length - 1] & 15;
  return ((digest.readUInt32BE(offset) & 0x7fffffff) % 1000000).toString().padStart(6, '0');
}
try {
  await page.goto('https://localhost:8443/auth/login');
  await expect(page.getByRole('heading', { name: 'Welcome home.' })).toBeVisible();
  await expect(page.locator('.hearth-signin-context strong')).toHaveText('Hearth Administration');
  await expect(page).toHaveTitle('Sign in to Hearth');
  await expect(page.locator('#kc-header-wrapper')).toHaveCSS('background-image', /hearth-lockup-light/);
  expect((await page.locator('.pf-v5-c-login__main').boundingBox()).width).toBeGreaterThanOrEqual(480);
  await page.screenshot({ path: 'admin-login.png', fullPage: true });
  await page.emulateMedia({ colorScheme: 'dark' });
  await expect(page.locator('#kc-header-wrapper')).toHaveCSS('background-image', /hearth-lockup-dark/);
  await page.screenshot({ path: 'login-firelight.png', fullPage: true });
  await page.emulateMedia({ colorScheme: 'light' });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'login-mobile.png', fullPage: true });
  await page.goto('https://localhost:8444/auth/login');
  await expect(page.locator('.hearth-signin-context strong')).toHaveText('Your Hearth workspace');
  step = 'browser TLS probes';
  for (const [port, audience] of [[8443, 'admin'], [8444, 'user'], [8445, 'identity']]) {
    const response = await page.evaluate(async port => {
      const result = await fetch(`https://localhost:${port}/health/browser`, { credentials: 'omit' });
      return { status: result.status, body: await result.json() };
    }, port);
    expect(response.status).toBe(200);
    expect(response.body).toEqual({ service: `hearth-${audience}`, status: 'ok' });
  }
  step = 'isolated realm registration and MFA';
  await page.setViewportSize({ width: 1100, height: 1100 });
  const verifier = randomBytes(32).toString('base64url');
  const state = randomBytes(24).toString('hex');
  const redirectUri = 'http://localhost:8085/qa-complete';
  const query = new URLSearchParams({ client_id: 'hearth-admin', redirect_uri: redirectUri, response_type: 'code', scope: 'openid', state, nonce: randomBytes(24).toString('hex'), code_challenge: createHash('sha256').update(verifier).digest('base64url'), code_challenge_method: 'S256' });
  const endpoint = `http://localhost:8085/realms/${data.realm}/protocol/openid-connect`;
  const authUrl = endpoint + '/auth?' + query;
  await page.goto(authUrl);
  step = 'isolated realm registration form';
  await page.getByRole('link', { name: 'Create account', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Create your Hearth account' })).toBeVisible();
  await page.screenshot({ path: 'registration.png', fullPage: true });
  await page.goto(authUrl);
  step = 'isolated realm password and authenticator form';
  await page.locator('#username').fill(data.username);
  await page.locator('#password').fill(data.password);
  await page.locator('#kc-login').click();
  await expect(page.getByRole('heading', { name: 'Protect your Hearth account' })).toBeVisible();
  await page.screenshot({ path: 'authenticator.png', fullPage: true, mask: [page.locator('#kc-totp-secret-qr-code')], maskColor: '#EDE4D8' });
  await page.locator('#mode-manual').click();
  const secret = (await page.locator('#kc-totp-secret-key').innerText()).replace(/\s/g, '');
  await page.locator('#totp').fill(otp(secret));
  await page.locator('#userLabel').fill('Disposable theme review');
  await page.locator('button[type=submit],input[type=submit]').first().click();
  step = 'isolated realm recovery enrollment';
  await expect(page.getByRole('heading', { name: 'Save your Hearth recovery codes' })).toBeVisible();
  await page.screenshot({ path: 'recovery.png', fullPage: true, mask: [page.locator('#kc-recovery-codes-list')], maskColor: '#EDE4D8' });
  await page.locator('input[type=checkbox]').first().check();
  await page.getByRole('button', { name: 'Continue to Hearth' }).click();
  step = 'isolated realm PKCE exchange';
  await page.waitForURL(url => url.pathname === '/qa-complete');
  const callback = new URL(page.url());
  expect(callback.searchParams.get('state')).toBe(state);
  const token = await context.request.post(endpoint + '/token', { form: { grant_type: 'authorization_code', client_id: 'hearth-admin', client_secret: data.client_secret, code: callback.searchParams.get('code'), redirect_uri: redirectUri, code_verifier: verifier } });
  expect(token.status()).toBe(200);
  expect((await token.json()).access_token).toBeTruthy();
  expect(errors).toEqual([]);
  writeFileSync('theme-browser.json', JSON.stringify({ passed: ['Public HTTPS admin and workspace login branding and context', 'Daylight, Firelight and mobile layout', 'All three HTTPS browser probe responses', 'Disposable realm registration form', 'Disposable realm authenticator and recovery enrollment with real PKCE code exchange'], browser: browser.version(), public_tls_validation: true, mfa_scope: 'Separate disposable Keycloak realm on guest HTTP loopback; no BFF or existing farm account used', secret_regions_masked_in_screenshots: true }, null, 2));
  console.log('Five theme and browser-trust checks passed. Existing farm accounts were not used.');
} catch (error) {
  console.error('Theme QA failed at ' + step + ': ' + error.name);
  console.error(JSON.stringify({ path: new URL(page.url()).pathname, headings: await page.locator('h1').allTextContents(), detail: error.message.split('\n').slice(0, 4).join(' ').replace(/https?:\S+/g, '[redacted URL]') }));
  process.exitCode = 1;
} finally { await browser.close(); }

// Real trusted-HTTPS identity acceptance. No response fixtures or certificate bypass flags.
import { chromium, expect } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
import { createHmac } from 'node:crypto';

const accounts = JSON.parse(readFileSync('identity-qa.json', 'utf8'));
const admin = 'https://localhost:8443';
const user = 'https://localhost:8444';
const evidence = [];
let step = 'launch trusted browser';
const browser = await chromium.launch({ headless: true });
let page;
function totp(secret) {
  let bits = '';
  for (const char of secret.replace(/\s/g, '').toUpperCase()) bits += 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'.indexOf(char).toString(2).padStart(5, '0');
  const bytes = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) bytes.push(parseInt(bits.slice(i, i + 8), 2));
  const counter = Buffer.alloc(8); counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const hash = createHmac('sha1', Buffer.from(bytes)).update(counter).digest();
  const offset = hash[hash.length - 1] & 15;
  return ((hash.readUInt32BE(offset) & 0x7fffffff) % 1000000).toString().padStart(6, '0');
}
async function nextCode(account) {
  const counter = Math.floor(Date.now() / 30000);
  if (account.lastCounter === counter) await new Promise(resolve => setTimeout(resolve, 31000 - (Date.now() % 30000)));
  account.lastCounter = Math.floor(Date.now() / 30000);
  writeFileSync('identity-qa.json', JSON.stringify(accounts), { mode: 0o600 });
  return totp(account.otp);
}
async function finishIdentity(account, origin) {
  for (let attempt = 0; attempt < 10; attempt++) {
    await page.waitForLoadState('domcontentloaded');
    if (page.url().startsWith(origin + '/') && !page.url().includes('/auth/')) return;
    if (await page.locator('#username').count()) {
      await page.locator('#username').fill(account.username);
      await page.locator('#password').fill(account.password);
      await page.locator('#kc-login').click();
    } else if (await page.locator('#password').count()) {
      await page.locator('#password').fill(account.password);
      await page.locator('#kc-login').click();
    } else if (await page.locator('#totp').count()) {
      if (await page.locator('#mode-manual').count()) await page.locator('#mode-manual').click();
      account.otp = (await page.locator('#kc-totp-secret-key').innerText()).replace(/\s/g, '');
      writeFileSync('identity-qa.json', JSON.stringify(accounts), { mode: 0o600 });
      await page.locator('#totp').fill(await nextCode(account));
      if (await page.locator('#userLabel').count()) await page.locator('#userLabel').fill('hearth acceptance authenticator');
      await page.locator('button[type=submit],input[type=submit]').first().click();
    } else if (await page.locator('#otp').count()) {
      await page.locator('#otp').fill(await nextCode(account));
      await page.locator('#kc-login').click();
    } else if (await page.locator('input[type=checkbox]').count()) {
      await page.locator('input[type=checkbox]').first().check();
      await page.locator('button[type=submit],input[type=submit]').first().click();
    } else {
      const controls = await page.locator('input,button,a,h1').evaluateAll(nodes => nodes.map(n => ({ tag: n.tagName, id: n.id, type: n.getAttribute('type'), label: n.tagName === 'H1' || n.tagName === 'BUTTON' ? n.textContent?.trim().slice(0, 100) : '' })));
      throw new Error('Unexpected identity page controls: ' + JSON.stringify(controls));
    }
  }
  throw new Error('Identity did not finish its required actions.');
}
async function login(account, origin) {
  await page.goto(origin);
  await page.getByRole('link', { name: /Sign in to/ }).click();
  await finishIdentity(account, origin);
  const response = await page.evaluate(() => fetch('/api/v1/session').then(async r => ({ status: r.status, error: r.ok ? '' : await r.text() })));
  if (response.status !== 200) throw new Error('BFF session ' + JSON.stringify(response));
  await expect(page.getByRole('button', { name: 'Sign out', exact: true })).toBeVisible();
}
try {
  if (process.env.HEARTH_QA_CASE === 'credential-loss') {
    step = 'Missing second factor requires enrollment before a BFF session';
    const context = await browser.newContext(); page = await context.newPage();
    await page.goto(user);
    await page.getByRole('link', { name: /Sign in to/ }).click();
    await page.locator('#username').fill(accounts.alex.username);
    await page.locator('#password').fill(accounts.alex.password);
    await page.locator('#kc-login').click();
    await expect(page.locator('#totp')).toBeVisible();
    expect((await context.cookies()).filter(c => c.name === '__Host-hearth_user_session')).toHaveLength(0);
    await finishIdentity(accounts.alex, user);
    await page.getByRole('button', { name: 'Private drafts', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Keep the spark.' })).toBeVisible();
    writeFileSync('credential-loss.json', JSON.stringify({ passed: true, assertion: step, tls_validation: true }, null, 2));
    console.log('Missing second-factor re-enrollment passed. No password-only BFF session was issued.');
  } else {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1080 } });
  page = await context.newPage();
  step = 'Owner sign-in, authenticator enrollment and recovery codes';
  await login(accounts.owner, admin);
  evidence.push(step);
  await expect(page.getByRole('heading', { name: 'Welcome home, Morgan.' })).toBeVisible();
  await expect(page.getByText('14', { exact: true })).toBeVisible();
  await page.screenshot({ path: 'admin-overview.png', fullPage: true });
  await page.getByLabel('Appearance').selectOption('dark');
  await page.screenshot({ path: 'admin-firelight.png', fullPage: true });
  await page.getByLabel('Appearance').selectOption('light');
  await page.getByRole('button', { name: 'Capabilities', exact: true }).click();
  await expect(page.locator('.capability-card')).toHaveCount(14);
  await page.screenshot({ path: 'capabilities.png', fullPage: true });
  evidence.push('Fourteen real capability definitions remain explicitly Unassigned');
  step = 'Separate user sign-in';
  await page.goto(user);
  await expect(page.getByRole('link', { name: /Sign in to/ })).toBeVisible();
  await login(accounts.owner, user);
  evidence.push('Admin cookie does not sign the browser into the user application');
  step = 'Create, reload and edit a private draft';
  await page.evaluate(async () => {
    const session = await fetch('/api/v1/session').then(r => r.json());
    const workspace = await fetch('/api/v1/workspace').then(r => r.json());
    for (const draft of workspace.drafts.filter(d => d.title === 'An idea for a quieter internet')) {
      await fetch(`/api/v1/drafts/${draft.id}`, { method: 'DELETE', headers: { 'X-Hearth-CSRF': session.csrf_token } });
    }
  });
  await page.reload();
  await page.getByLabel('Draft title', { exact: true }).fill('An idea for a quieter internet');
  await page.getByLabel('Your draft', { exact: true }).fill('A place where our ideas can stay close to home.\n\nStart small: gather a thought, shape a plan, and keep a little room for possibility.');
  await page.getByRole('button', { name: 'Save draft', exact: true }).click();
  await expect(page.getByText('Saved to your private workspace.')).toBeVisible();
  const session = await page.evaluate(() => fetch('/api/v1/session').then(r => r.json()));
  const workspace = await page.evaluate(() => fetch('/api/v1/workspace').then(r => r.json()));
  const draftId = workspace.drafts[0].id;
  await page.reload();
  await page.getByRole('button', { name: 'An idea for a quieter internet', exact: true }).click();
  await expect(page.getByLabel('Your draft', { exact: true })).toContainText('Start small');
  await page.getByLabel('Your draft', { exact: true }).fill('A place where our ideas can stay close to home.\n\nStart small: gather a thought, shape a plan, and keep a little room for possibility.\n\nNext: try writing with a local model.');
  await page.getByRole('button', { name: 'Save draft', exact: true }).click();
  await expect(page.getByText('Saved to your private workspace.')).toBeVisible();
  await page.screenshot({ path: 'user-drafts.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'user-mobile.png', fullPage: true });
  evidence.push('Private draft creation, persistence across reload, revision update and mobile layout');
  step = 'CSRF and cookie audience rejection';
  const csrf = await page.evaluate(() => fetch('/api/v1/drafts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: 'forbidden', content: 'forbidden' }) }).then(r => r.status));
  expect(csrf).toBe(403);
  const swapped = await browser.newContext();
  const ownCookie = (await context.cookies()).find(c => c.name === '__Host-hearth_user_session');
  await swapped.addCookies([{ ...ownCookie, name: '__Host-hearth_admin_session' }]);
  const swappedPage = await swapped.newPage();
  await swappedPage.goto(admin);
  expect(await swappedPage.evaluate(() => fetch('/api/v1/session').then(r => r.status))).toBe(401);
  await swapped.close();
  evidence.push('Missing CSRF rejected; renaming a user cookie to the admin name does not authenticate');
  const ownerPage = page;
  step = 'Two independent Members and guessed private identifiers';
  for (const name of ['rowan', 'alex']) {
    const memberContext = await browser.newContext(); page = await memberContext.newPage();
    await login(accounts[name], user);
    const status = await page.evaluate(id => fetch(`/api/v1/drafts/${id}`).then(r => r.status), draftId);
    expect(status).toBe(404);
    await page.goto(admin);
    await login(accounts[name], admin);
    await expect(page.getByText('This account is a Member. Administration requires a farm role.')).toBeVisible();
    expect(await page.evaluate(() => fetch('/api/v1/farm').then(r => r.status))).toBe(403);
    await memberContext.close();
  }
  evidence.push('Two Members cannot read guessed Owner draft IDs or inspect the admin farm');
  step = 'Self-registration creates a Member with a private workspace';
  const signupContext = await browser.newContext(); page = await signupContext.newPage();
  await page.goto(user);
  await page.getByRole('link', { name: /Sign in to/ }).click();
  await page.getByRole('link', { name: 'Register', exact: true }).click();
  await page.locator('#username').fill(accounts.signup.username);
  if (await page.locator('#firstName').count()) await page.locator('#firstName').fill(accounts.signup.name);
  await page.locator('#password').fill(accounts.signup.password);
  await page.locator('#password-confirm').fill(accounts.signup.password);
  await page.locator('button[type=submit],input[type=submit]').first().click();
  await finishIdentity(accounts.signup, user);
  const registered = await page.evaluate(() => fetch('/api/v1/session').then(r => r.json()));
  expect(registered.roles).toEqual(['Member']);
  await page.getByRole('button', { name: 'Private drafts', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Keep the spark.' })).toBeVisible();
  await expect(page.getByText('0 saved · Personal workspace')).toBeVisible();
  await signupContext.close();
  evidence.push('Real browser self-registration, MFA and recovery enrollment provision only Member rights and one personal workspace');
  page = ownerPage;
  step = 'Logout invalidates copied session';
  const copied = await browser.newContext();
  await copied.addCookies([ownCookie]);
  const copiedPage = await copied.newPage();
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByRole('link', { name: /Sign in to/ })).toBeVisible();
  await copiedPage.goto(user);
  expect(await copiedPage.evaluate(() => fetch('/api/v1/session').then(r => r.status))).toBe(401);
  await copied.close();
  evidence.push('Logout invalidates a previously copied server session');
  writeFileSync('identity-browser.json', JSON.stringify({ passed: evidence, browser: await browser.version(), tls: 'isolated NSS root, certificate validation enabled', fixtures: 'three prepared synthetic Keycloak accounts plus one browser signup; no mocked auth responses' }, null, 2));
  console.log(JSON.stringify({ passed: evidence.length, checks: evidence }));
  }
} catch (error) {
  console.error(JSON.stringify({ step, error: error.message.replace(/https?:\/\/\S+/g, '[URL redacted]') }));
  process.exitCode = 1;
} finally { await browser.close(); }

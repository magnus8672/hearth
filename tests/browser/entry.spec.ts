import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/session', route => route.fulfill({ status: 401, json: { error: { message: 'Sign in to hearth to continue.' } } }));
  await page.route('**/api/v1/setup', route => route.fulfill({ status: 200, json: { owner_created: false } }));
});

test('an unavailable service can recover without inventing sign-in readiness', async ({ page }) => {
  let ready = false;
  await page.route('**/health/ready', route => route.fulfill({ status: ready ? 200 : 503, json: ready ? { status: 'ready' } : { error: 'fixture_unavailable' } }));
  await page.goto('/');
  await expect(page.getByText('Connection unavailable', { exact: true })).toBeVisible();
  ready = true;
  await page.getByRole('button', { name: 'Check connection', exact: true }).click();
  await expect(page.getByText('Database connected', { exact: true })).toBeVisible();
  await expect(page.getByText('Open the local hearth setup tool to create the Owner account and prepare browser trust.')).toBeVisible();
  await expect(page.getByRole('link', { name: /Sign in to/ })).toHaveCount(0);
});

test('theme choice restores on reload and system mode follows the browser', async ({ page }) => {
  await page.route('**/health/ready', route => route.fulfill({ status: 503, json: {} }));
  await page.emulateMedia({ colorScheme: 'light' });
  await page.goto('/');
  await page.getByLabel('Appearance').selectOption('dark');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.reload();
  await expect(page.getByLabel('Appearance')).toHaveValue('dark');
  await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(23, 20, 18)');
  await page.getByLabel('Appearance').selectOption('system');
  await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(245, 240, 232)');
  await page.emulateMedia({ colorScheme: 'dark' });
  await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(23, 20, 18)');
});

test('both bundles fit mobile width with accessible connection controls', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await page.route('**/health/ready', route => route.fulfill({ status: 503, json: {} }));
  for (const origin of ['http://127.0.0.1:5173', 'http://127.0.0.1:5174']) {
    await page.goto(origin);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await expect(page.getByText('Connection unavailable', { exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    const button = await page.getByRole('button', { name: 'Check connection', exact: true }).boundingBox();
    expect(button!.height).toBeGreaterThanOrEqual(44);
    await page.keyboard.press('Tab');
    await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused();
  }
});

test('live appliance readiness is visible in the real application', async ({ page }) => {
  test.skip(process.env.HEARTH_LIVE_UI !== '1', 'Enable only with the real development appliance running.');
  await page.goto('/');
  await expect(page.getByText('Database connected', { exact: true })).toBeVisible({ timeout: 15000 });
  await page.getByLabel('Appearance').selectOption('light');
  await page.screenshot({ path: '.hearth/test-results/welcome-daylight.png', fullPage: true });
  await page.getByLabel('Appearance').selectOption('dark');
  await page.screenshot({ path: '.hearth/test-results/welcome-firelight.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('http://127.0.0.1:5174');
  await expect(page.getByText('Database connected', { exact: true })).toBeVisible();
  await page.screenshot({ path: '.hearth/test-results/welcome-mobile.png', fullPage: true });
});

import { defineConfig } from '@playwright/test';

// Browser client only: never start a head or dev server implicitly.
const baseURL = process.env.HEARTH_BROWSER_ORIGIN;
if (!baseURL) throw new Error('Set HEARTH_BROWSER_ORIGIN to the authorized deployment before VM browser tests.');
export default defineConfig({
  testDir: './tests/browser', timeout: 30_000, workers: 1,
  outputDir: '.hearth/browser-results',
  use: { baseURL, browserName: 'chromium', colorScheme: 'dark', trace: 'retain-on-failure' },
});

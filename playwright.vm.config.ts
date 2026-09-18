import { defineConfig } from '@playwright/test';

// Browser client only: never start the retired workstation head/dev servers.
export default defineConfig({
  testDir: './tests/browser', timeout: 30_000, workers: 1,
  outputDir: '.hearth/browser-results',
  use: { baseURL: process.env.HEARTH_BROWSER_ORIGIN || 'https://hearth.example.invalid', browserName: 'chromium', colorScheme: 'dark', trace: 'retain-on-failure' },
});

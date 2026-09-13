import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/browser',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['json', { outputFile: '.hearth/test-results/browser.json' }]],
  outputDir: '.hearth/test-results/browser',
  use: { baseURL: 'http://127.0.0.1:5173', trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    { command: 'pnpm dev:admin', url: 'http://127.0.0.1:5173', reuseExistingServer: !process.env.CI },
    { command: 'pnpm dev:user', url: 'http://127.0.0.1:5174', reuseExistingServer: !process.env.CI },
  ],
});

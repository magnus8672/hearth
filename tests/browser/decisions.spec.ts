import { test, expect } from '@playwright/test';
import { browserOrigins } from './origins';

test('private Decisions supports typed questions, explicit comparisons, export and deletion', async ({ page }) => {
  const requests: Record<string, unknown>[] = [];
  let items: Record<string, unknown>[] = [];
  const target = '00000000-0000-4000-8000-000000000001';
  await page.route('**/api/v1/session', route => route.fulfill({ json: { id: 'fixture', display_name: 'Tester', roles: ['Member'], permissions: ['capability.decision.evaluate'], csrf_token: 'fixture' } }));
  await page.route('**/api/v1/capabilities', route => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/v1/decisions', async route => {
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON(); requests.push(body);
      const q = body.questions[0];
      items = [{ id: body.id, state: 'completed', request: body, receipt: { source: body.target_id ? 'dedicated' : 'builtin' }, result: { model: body.target_id ? 'Dedicated fixture' : 'Built-in fixture', model_revision: 'reviewed', elapsed_ms: 24, input_tokens: 30, answers: [{ id: q.id, kind: q.kind, choice: q.kind === 'choice' ? 'yes' : null, score: q.kind === 'score' ? 1.25 : null, probability_true: q.kind === 'boolean' ? .8 : null, probabilities: q.kind === 'choice' ? { yes: .9, no: .1 } : null, provider_confidence: .6, answer_confidence: .9, abstained: false }] } }];
      await route.fulfill({ status: 202, json: items[0] });
    } else await route.fulfill({ json: { builtin: { ready: true, model: 'Built-in fixture' }, targets: [{ id: target, name: 'Dedicated fixture', model: 'typed', ready: true }], items } });
  });
  await page.route('**/api/v1/decisions/*', async route => { items = []; await route.fulfill({ json: { deleted: true } }); });
  await page.goto(browserOrigins.workspace+'/#decisions');
  await page.getByLabel('State or source text').fill('The parcel arrived on Monday.');
  await page.getByLabel('Question', { exact: true }).fill('Was the parcel delivered?');
  await page.getByRole('button', { name: 'Evaluate decision' }).click();
  await expect(page.locator('.decision-result')).toContainText('yes: Fits the requirement');
  await expect(page.locator('meter')).toHaveCount(2);
  await expect(page.getByLabel('State or source text')).toHaveValue('The parcel arrived on Monday.');
  await page.getByLabel('Decision provider').selectOption(target);
  await page.getByLabel('Question type').selectOption('boolean');
  await page.getByRole('button', { name: 'Evaluate decision' }).click();
  await expect(page.locator('.decision-result')).toContainText('Probability of true: 80.0%');
  expect(requests[1].target_id).toBe(target);
  const downloaded = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Save JSON' }).click();
  expect((await downloaded).suggestedFilename()).toMatch(/hearth-decision-.*json/);
  await page.getByLabel('Question type').selectOption('score');
  await page.getByRole('button', { name: 'Evaluate decision' }).click();
  await expect(page.locator('.decision-result')).toContainText('Expected rubric index: 1.25 / 2');
  await page.getByLabel('Appearance').selectOption('dark');
  await page.screenshot({ path: '.hearth/p5a/decisions-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(await page.getByLabel('State or source text').evaluate(element => element.getBoundingClientRect().right <= element.closest('form')!.getBoundingClientRect().right - 10)).toBe(true);
  await page.screenshot({ path: '.hearth/p5a/decisions-mobile.png', fullPage: true });
  await page.getByRole('button', { name: 'Delete', exact: true }).click();
  await expect(page.locator('.decision-result')).toHaveCount(0);
});

test('admin can change internal source without submitting member assignments', async ({ page }) => {
  const source = { revision: 1, mode: 'legacy', source: 'builtin', target_id: null as string|null, fallback_builtin: true, member_builtin: true, threshold: .85, deadline_ms: 1500, shadow_sample: 0 };
  let config = source;
  const writes: string[] = [];
  await page.route('**/api/v1/**', route => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/v1/farm', route => route.fulfill({ json: { farm: { name: 'Fixture hearth' }, members: [] } }));
  await page.route('**/api/v1/session', route => route.fulfill({ json: { id: 'fixture', display_name: 'Tester', roles: ['Owner'], permissions: ['farm.inspect', 'provider.configure'], csrf_token: 'fixture' } }));
  await page.route('**/api/v1/decision-settings', async route => {
    if (route.request().method() === 'PUT') { writes.push(route.request().url()); config = { ...route.request().postDataJSON(), revision: 2 }; await route.fulfill({ json: config }); }
    else await route.fulfill({ json: { settings: config, builtin: { ready: true, model: 'fixture-laya' }, targets: [{ id: '00000000-0000-4000-8000-000000000001', name: 'Dedicated', model: 'fixture', ready: true }] } });
  });
  await page.goto(browserOrigins.admin+'/#settings');
  await page.getByLabel('Automatic routing').selectOption('semantic');
  await page.getByLabel('Internal decision source').selectOption('dedicated');
  await page.getByLabel('Dedicated target').selectOption('00000000-0000-4000-8000-000000000001');
  await page.getByRole('button', { name: 'Save decision settings' }).click();
  await expect(page.getByRole('status')).toContainText('Saved for new requests');
  expect(config.source).toBe('dedicated'); expect(config.fallback_builtin).toBe(true);
  expect(writes.length).toBe(1);
  await page.getByLabel('Automatic routing').selectOption('legacy');
  await page.getByRole('button', { name: 'Save decision settings' }).click();
  await expect.poll(() => config.mode).toBe('legacy');
});

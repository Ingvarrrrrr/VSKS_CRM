import { test, expect } from '@playwright/test';
import { login } from './helpers';
import { dismissOrgPicker } from './helpers';

const ids = [774, 776, 784, 909, 910];

test('advance purchases open without JS errors or error dialog', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(`[${page.url()}] pageerror: ${e.message}`));

  await login(page);
  await dismissOrgPicker(page);

  for (const id of ids) {
    await page.goto(`/orders/${id}`);
    await page.waitForLoadState('networkidle', { timeout: 20_000 }).catch(() => {});
    await page.waitForTimeout(1000);
    const errDialog = page.locator('.v-overlay-container').filter({ hasText: 'Код:' });
    const dialogVisible = await errDialog.first().isVisible({ timeout: 500 }).catch(() => false);
    if (dialogVisible) {
      const text = await errDialog.first().innerText().catch(() => '');
      errors.push(`[order ${id}] ERROR DIALOG SHOWN: ${text}`);
    }
  }

  if (errors.length) {
    console.log('ERRORS FOUND:\n' + errors.join('\n'));
  }
  expect(errors, errors.join('\n')).toEqual([]);
});
